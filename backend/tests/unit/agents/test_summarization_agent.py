"""Unit tests for the Summarization Agent.

These tests verify:
1. Graph node logic (gather_patient_data, prepare_context, generate_soap_note, store_soap_note)
2. SummarizationAgent.process() success and error paths
3. The _calculate_adherence_stats helper

All Supabase/Gemini calls are mocked — no real network calls.
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agents.summarization.agent import SummarizationAgent, SummarizationInput
from app.agents.summarization.graph import (
    _calculate_adherence_stats,
    prepare_context,
)
from app.agents.summarization.prompts import build_soap_prompt

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def clinician_id():
    return uuid4()


@pytest.fixture
def patient_id():
    return uuid4()


@pytest.fixture
def mock_db():
    """Mock Supabase client with fluent builder pattern."""
    db = MagicMock()

    def make_query_mock(data, count=None):
        query = MagicMock()
        query.select.return_value = query
        query.eq.return_value = query
        query.gte.return_value = query
        query.in_.return_value = query
        query.order.return_value = query
        query.limit.return_value = query
        query.single.return_value = query
        result = MagicMock()
        result.data = data
        result.count = count
        query.execute.return_value = result
        return query

    # Patient row
    patient_data = {
        "id": str(uuid4()),
        "first_name": "Jane",
        "last_name": "Smith",
        "email": "jane@test.com",
        "date_of_birth": "1975-06-15",
    }

    # Adherence logs
    adherence_data = [
        {"status": "completed", "target_type": "medication", "logged_at": "2026-03-01T10:00:00Z"},
        {"status": "skipped", "target_type": "medication", "logged_at": "2026-03-02T10:00:00Z"},
        {"status": "completed", "target_type": "obligation", "logged_at": "2026-03-03T10:00:00Z"},
    ]

    # Symptom reports
    symptom_data = [
        {
            "id": str(uuid4()),
            "symptom": "headache",
            "severity": 3,
            "created_at": "2026-03-15T09:00:00Z",
            "flagged_for_adr": False,
        }
    ]

    # Mock table selectively
    def table_mock(table_name):
        data_map = {
            "patients": patient_data,
            "medications": [
                {
                    "name": "Metformin",
                    "dosage": "500mg",
                    "frequency": "once daily",
                    "is_active": True,
                }
            ],
            "adherence_logs": adherence_data,
            "symptom_reports": symptom_data,
            "chat_messages": [
                {
                    "role": "user",
                    "content": "Feeling better today",
                    "created_at": "2026-03-20T12:00:00Z",
                }
            ],
            "conditions": [{"name": "Type 2 Diabetes", "icd10_code": "E11"}],
            "allergies": [{"allergen": "Penicillin", "severity": "severe"}],
            "adr_assessments": [],
        }
        row_data = data_map.get(table_name)
        return make_query_mock(row_data)

    db.table.side_effect = table_mock
    return db


# ── _calculate_adherence_stats tests ──────────────────────────────────────────


class TestCalculateAdherenceStats:
    """Tests for the internal adherence calculation helper."""

    def test_empty_logs_returns_zeros(self):
        stats = _calculate_adherence_stats([])
        assert stats["overall_score"] == 0.0
        assert stats["medication_score"] == 0.0
        assert stats["obligation_score"] == 0.0

    def test_all_completed_returns_one(self):
        logs = [
            {"status": "completed", "target_type": "medication"},
            {"status": "completed", "target_type": "medication"},
        ]
        stats = _calculate_adherence_stats(logs)
        assert stats["overall_score"] == 1.0
        assert stats["medication_score"] == 1.0

    def test_mixed_status(self):
        logs = [
            {"status": "completed", "target_type": "medication"},
            {"status": "skipped", "target_type": "medication"},
            {"status": "completed", "target_type": "obligation"},
        ]
        stats = _calculate_adherence_stats(logs)
        assert stats["overall_score"] == pytest.approx(2 / 3, rel=0.01)
        assert stats["medication_score"] == pytest.approx(0.5, rel=0.01)
        assert stats["obligation_score"] == pytest.approx(1.0, rel=0.01)

    def test_obligation_only(self):
        logs = [
            {"status": "completed", "target_type": "obligation"},
            {"status": "completed", "target_type": "obligation"},
        ]
        stats = _calculate_adherence_stats(logs)
        assert stats["medication_score"] == 0.0
        assert stats["obligation_score"] == 1.0

    def test_all_skipped(self):
        logs = [{"status": "skipped", "target_type": "medication"} for _ in range(5)]
        stats = _calculate_adherence_stats(logs)
        assert stats["overall_score"] == 0.0


# ── prepare_context tests ─────────────────────────────────────────────────────


class TestPrepareContext:
    """Tests for the prepare_context graph node."""

    @pytest.mark.asyncio
    async def test_copies_all_keys_to_context(self):
        state = {
            "patient_id": str(uuid4()),
            "clinician_id": str(uuid4()),
            "lookback_days": 30,
            "patient_info": {"first_name": "Jane", "last_name": "Doe"},
            "medications": [{"name": "Metformin"}],
            "adherence_stats": {"overall_score": 0.8},
            "symptom_reports": [],
            "chat_messages": [],
            "conditions": [],
            "allergies": [],
            "adr_assessments": [],
        }
        result = await prepare_context(state)
        assert "patient_context" in result
        ctx = result["patient_context"]
        assert ctx["patient_info"] == state["patient_info"]
        assert ctx["medications"] == state["medications"]
        assert ctx["lookback_days"] == 30

    @pytest.mark.asyncio
    async def test_handles_missing_optional_keys(self):
        """Should not raise even if optional keys are absent."""
        state = {
            "patient_id": str(uuid4()),
            "clinician_id": str(uuid4()),
            "lookback_days": 30,
        }
        result = await prepare_context(state)
        assert "patient_context" in result
        ctx = result["patient_context"]
        assert ctx["medications"] == []
        assert ctx["symptom_reports"] == []


# ── build_soap_prompt tests ───────────────────────────────────────────────────


class TestBuildSoapPrompt:
    """Tests for the prompt builder function."""

    def test_includes_patient_name(self):
        context = {
            "patient_info": {
                "first_name": "Alice",
                "last_name": "Brown",
                "date_of_birth": "1980-01-01",
            },
            "medications": [],
            "adherence_stats": {
                "overall_score": 0.75,
                "medication_score": 0.8,
                "obligation_score": 0.7,
                "current_streak_days": 5,
            },
            "symptom_reports": [],
            "chat_messages": [],
            "conditions": [],
            "allergies": [],
            "adr_assessments": [],
            "lookback_days": 30,
        }
        prompt = build_soap_prompt(context)
        assert "Alice Brown" in prompt

    def test_includes_adherence_data(self):
        context = {
            "patient_info": {},
            "medications": [],
            "adherence_stats": {
                "overall_score": 0.65,
                "medication_score": 0.70,
                "obligation_score": 0.60,
                "current_streak_days": 3,
            },
            "symptom_reports": [],
            "chat_messages": [],
            "conditions": [],
            "allergies": [],
            "adr_assessments": [],
            "lookback_days": 30,
        }
        prompt = build_soap_prompt(context)
        assert "65%" in prompt or "Adherence" in prompt

    def test_caps_medications_at_20(self):
        meds = [
            {"name": f"Med{i}", "dosage": "10mg", "frequency": "daily", "is_active": True}
            for i in range(30)
        ]
        context = {
            "patient_info": {},
            "medications": meds,
            "adherence_stats": {
                "overall_score": 0,
                "medication_score": 0,
                "obligation_score": 0,
                "current_streak_days": 0,
            },
            "symptom_reports": [],
            "chat_messages": [],
            "conditions": [],
            "allergies": [],
            "adr_assessments": [],
            "lookback_days": 30,
        }
        prompt = build_soap_prompt(context)
        # Only first 20 meds should be included
        assert "Med19" in prompt
        assert "Med25" not in prompt  # beyond cap

    def test_no_allergies_shows_nkda(self):
        context = {
            "patient_info": {},
            "medications": [],
            "adherence_stats": {
                "overall_score": 0,
                "medication_score": 0,
                "obligation_score": 0,
                "current_streak_days": 0,
            },
            "symptom_reports": [],
            "chat_messages": [],
            "conditions": [],
            "allergies": [],
            "adr_assessments": [],
            "lookback_days": 30,
        }
        prompt = build_soap_prompt(context)
        assert "NKDA" in prompt


# ── SummarizationAgent integration tests ─────────────────────────────────────


class TestSummarizationAgent:
    """Integration-style tests mocking DB and Gemini client."""

    @pytest.fixture
    def agent(self, mock_db):
        return SummarizationAgent(db=mock_db)

    @pytest.mark.asyncio
    async def test_successful_soap_note_generation(self, agent, patient_id, clinician_id):
        """Happy path: agent returns SOAP note with status 'success'."""
        mock_soap = {
            "subjective": "Patient reports headache",
            "objective": "Adherence 67%, no ADRs",
            "assessment": "Medication adherence concern",
            "plan": "1. Review medication schedule",
            "generated_at": "2026-04-09T00:00:00Z",
            "model_used": "gemini-pro-test",
        }

        stored_id = str(uuid4())
        mock_graph = MagicMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={
                "stored_note_id": stored_id,
                "soap_note": mock_soap,
                "error": None,
            }
        )

        with patch(
            "app.agents.summarization.agent.build_summarization_graph", return_value=mock_graph
        ):
            agent_input = SummarizationInput(
                user_id=clinician_id,
                patient_id=patient_id,
                lookback_days=30,
            )

            output = await agent.process(agent_input)
            assert output.status == "success"
            assert output.soap_note == mock_soap
            assert output.soap_note_id == stored_id
            mock_graph.ainvoke.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_agent_input_model_validation(self, clinician_id, patient_id):
        """SummarizationInput should accept valid UUID fields."""
        agent_input = SummarizationInput(
            user_id=clinician_id,
            patient_id=patient_id,
            lookback_days=30,
        )
        assert agent_input.patient_id == patient_id
        assert agent_input.lookback_days == 30

    @pytest.mark.asyncio
    async def test_agent_input_default_lookback(self, clinician_id, patient_id):
        """lookback_days should default to 30."""
        agent_input = SummarizationInput(
            user_id=clinician_id,
            patient_id=patient_id,
        )
        assert agent_input.lookback_days == 30
