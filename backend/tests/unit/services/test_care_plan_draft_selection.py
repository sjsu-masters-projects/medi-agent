"""Safety tests for the evidence-constrained automatic draft selector."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.models.clinical_fact import SourceArtifactType
from app.models.generation import (
    GenerationErrorCode,
    GenerationProviderError,
    GenerationResponse,
    GenerationTelemetry,
)
from app.services import care_plan_classification, care_plan_service
from app.services.care_plan_service import CarePlanService

MEDICATION_FACT_ID = UUID("00000000-0000-0000-0000-000000000101")
MONITORING_FACT_ID = UUID("00000000-0000-0000-0000-000000000102")


def _facts() -> list[dict[str, object]]:
    return [
        {
            "id": str(MEDICATION_FACT_ID),
            "fact_type": "medication",
            "value": {
                "name": "Metformin",
                "dosage": "500 mg",
                "frequency": "twice daily",
                "route": "oral",
                "instructions": "Take one tablet by mouth twice daily with meals.",
            },
            "confidence_score": 0.92,
            "uncertainty": [],
        },
        {
            "id": str(MONITORING_FACT_ID),
            "fact_type": "obligation",
            "value": {
                "description": "Check fasting blood glucose before breakfast each day.",
                "frequency": "daily",
                "obligation_type": "monitoring",
            },
            "confidence_score": 0.91,
            "uncertainty": [],
        },
    ]


def _response(response: dict[str, object]) -> GenerationResponse:
    return GenerationResponse(
        text=json.dumps(response),
        telemetry=GenerationTelemetry(provider="flash", model="gemini-test", latency_ms=1),
    )


def _service_with_claim() -> CarePlanService:
    db = MagicMock()
    db.rpc.return_value.execute.return_value.data = [
        {
            "request_id": "00000000-0000-0000-0000-000000000301",
            "patient_id": "00000000-0000-0000-0000-000000000302",
            "attempt": 1,
        }
    ]
    return CarePlanService(db)


@pytest.mark.asyncio
async def test_draft_selector_accepts_only_complete_fixed_fact_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _response(
        {
            "items": [
                {"source_fact_id": str(MEDICATION_FACT_ID), "category": "medication"},
                {"source_fact_id": str(MONITORING_FACT_ID), "category": "monitoring"},
            ]
        }
    )
    generate = AsyncMock(return_value=response)
    monkeypatch.setattr(care_plan_classification, "generate_for_workload", generate)

    selected = await CarePlanService(MagicMock())._select_categories(_facts())

    assert selected == {
        str(MEDICATION_FACT_ID): "medication",
        str(MONITORING_FACT_ID): "monitoring",
    }
    prompt = generate.await_args.kwargs["prompt"]
    assert "Metformin" in prompt
    assert "source_fact_id" in prompt
    assert generate.await_args.kwargs["response_schema"]["type"] == "object"


@pytest.mark.asyncio
async def test_draft_selector_rejects_an_invented_or_missing_fact_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _response(
        {
            "items": [
                {"source_fact_id": str(MEDICATION_FACT_ID), "category": "medication"},
                {
                    "source_fact_id": "00000000-0000-0000-0000-000000000999",
                    "category": "monitoring",
                },
            ]
        }
    )
    generate = AsyncMock(return_value=response)
    monkeypatch.setattr(care_plan_classification, "generate_for_workload", generate)

    with pytest.raises(ValueError, match="fact_selection_mismatch"):
        await CarePlanService(MagicMock())._select_categories(_facts())

    assert generate.await_count == 2


@pytest.mark.asyncio
async def test_draft_selector_repairs_one_semantic_contract_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generate = AsyncMock(
        side_effect=[
            _response(
                {"items": [{"source_fact_id": str(MEDICATION_FACT_ID), "category": "medication"}]}
            ),
            _response(
                {
                    "items": [
                        {"source_fact_id": str(MEDICATION_FACT_ID), "category": "medication"},
                        {"source_fact_id": str(MONITORING_FACT_ID), "category": "monitoring"},
                    ]
                }
            ),
        ]
    )
    monkeypatch.setattr(care_plan_classification, "generate_for_workload", generate)

    assert await CarePlanService(MagicMock())._select_categories(_facts()) == {
        str(MEDICATION_FACT_ID): "medication",
        str(MONITORING_FACT_ID): "monitoring",
    }
    assert "final schema-repair attempt" in generate.await_args.kwargs["prompt"]


@pytest.mark.asyncio
async def test_transient_provider_failure_is_scheduled_for_retry() -> None:
    service = _service_with_claim()
    service._generate = AsyncMock(
        side_effect=GenerationProviderError(GenerationErrorCode.TIMEOUT, "safe test failure")
    )
    service._retry = MagicMock(return_value=False)

    counts = await service.process_pending(limit=1)

    assert counts == {
        "care_plans_claimed": 1,
        "care_plans_ready": 0,
        "care_plans_retry": 1,
        "care_plans_failed": 0,
    }
    service._retry.assert_called_once_with(
        {
            "request_id": "00000000-0000-0000-0000-000000000301",
            "patient_id": "00000000-0000-0000-0000-000000000302",
            "attempt": 1,
        },
        failure="provider_timeout",
    )


@pytest.mark.asyncio
async def test_invalid_model_response_fails_without_a_retry() -> None:
    service = _service_with_claim()
    service._generate = AsyncMock(side_effect=ValueError("safe test failure"))
    service._finish_request = MagicMock()

    counts = await service.process_pending(limit=1)

    assert counts == {
        "care_plans_claimed": 1,
        "care_plans_ready": 0,
        "care_plans_retry": 0,
        "care_plans_failed": 1,
    }
    service._finish_request.assert_called_once_with(
        {
            "request_id": "00000000-0000-0000-0000-000000000301",
            "patient_id": "00000000-0000-0000-0000-000000000302",
            "attempt": 1,
        },
        status="failed",
        plan_id=None,
        failure="invalid_model_response",
    )


@pytest.mark.asyncio
async def test_terminal_generation_failure_logs_only_safe_operational_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = _service_with_claim()
    service._generate = AsyncMock(side_effect=ValueError("private source text must not be logged"))
    service._finish_request = MagicMock()

    with caplog.at_level("WARNING", logger=care_plan_service.__name__):
        await service.process_pending(limit=1)

    events = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.getMessage().startswith("{")
    ]
    assert events == [
        {
            "attempt": 1,
            "event": "care_plan_generation_outcome",
            "failure_code": "invalid_model_response",
            "outcome": "care_plans_failed",
            "request_id": "00000000-0000-0000-0000-000000000301",
        }
    ]
    assert "private source text" not in caplog.text
    assert "00000000-0000-0000-0000-000000000302" not in caplog.text


@pytest.mark.asyncio
async def test_invalid_contract_logs_only_safe_validation_counts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = _service_with_claim()
    service._generate = AsyncMock(
        side_effect=care_plan_service.CarePlanClassificationError(
            "fact_selection_mismatch",
            {"missing_fact_count": 1, "returned_item_count": 1, "repair_attempted": 1},
        )
    )
    service._finish_request = MagicMock()

    with caplog.at_level("WARNING", logger=care_plan_service.__name__):
        await service.process_pending(limit=1)

    event = next(
        json.loads(record.getMessage())
        for record in caplog.records
        if record.getMessage().startswith("{")
    )
    assert event["failure_code"] == "invalid_model_response"
    assert event["missing_fact_count"] == 1
    assert event["repair_attempted"] == 1


@pytest.mark.asyncio
async def test_non_transient_provider_failure_fails_without_a_retry() -> None:
    service = _service_with_claim()
    service._generate = AsyncMock(
        side_effect=GenerationProviderError(GenerationErrorCode.CONFIGURATION, "safe test failure")
    )
    service._finish_request = MagicMock()

    counts = await service.process_pending(limit=1)

    assert counts["care_plans_failed"] == 1
    assert counts["care_plans_retry"] == 0
    service._finish_request.assert_called_once_with(
        {
            "request_id": "00000000-0000-0000-0000-000000000301",
            "patient_id": "00000000-0000-0000-0000-000000000302",
            "attempt": 1,
        },
        status="failed",
        plan_id=None,
        failure="provider_configuration",
    )


def test_conflicting_medication_sources_block_every_candidate() -> None:
    facts = [
        _facts()[0],
        {
            "id": "00000000-0000-0000-0000-000000000103",
            "fact_type": "medication",
            "value": {
                "name": "Metformin",
                "dosage": "1000 mg",
                "frequency": "once daily",
                "route": "oral",
                "instructions": "Take one tablet by mouth once daily with the evening meal.",
            },
        },
    ]

    conflicts = CarePlanService._medication_conflicts(facts)

    assert set(conflicts) == {str(MEDICATION_FACT_ID), "00000000-0000-0000-0000-000000000103"}
    item = CarePlanService(MagicMock())._item_from_fact(
        facts[0], category="medication", conflict=conflicts[str(MEDICATION_FACT_ID)]
    )
    assert item["instructions"] == "Take one tablet by mouth twice daily with meals."
    assert item["blocker_reason"] == "Resolve conflicting medication instructions before approval."


def test_legacy_obligation_payload_stages_a_provenance_backed_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clinician_id = UUID("00000000-0000-0000-0000-000000000201")
    patient_id = UUID("00000000-0000-0000-0000-000000000202")
    fact_id = UUID("00000000-0000-0000-0000-000000000203")
    created_candidates = []

    class FakeFactService:
        def __init__(self, _db: MagicMock) -> None:
            pass

        def create_candidate(self, candidate: object, *, actor_id: UUID) -> dict[str, str]:
            created_candidates.append((candidate, actor_id))
            return {"id": str(fact_id)}

    db = MagicMock()
    service = CarePlanService(db)
    monkeypatch.setattr(care_plan_service, "ClinicalFactService", FakeFactService)
    monkeypatch.setattr(service, "_require_assignment", lambda *_args: None)
    monkeypatch.setattr(service, "_open_draft", lambda *_args: {"id": str(UUID(int=204))})
    monkeypatch.setattr(
        service, "_hydrate_plan", lambda plan: {"id": plan["id"], "status": "draft"}
    )

    result = service.add_clinician_authored_obligation(
        clinician_id,
        patient_id,
        {
            "obligation_type": "exercise",
            "description": "Walk for 20 minutes.",
            "frequency": "3x per week",
            "notes": "Stop if you feel unwell.",
        },
    )

    assert result["status"] == "draft"
    candidate, actor_id = created_candidates[0]
    assert actor_id == clinician_id
    assert candidate.provenance.artifact_type is SourceArtifactType.CLINICIAN_ENTRY
    assert candidate.value == {
        "description": "Walk for 20 minutes.",
        "frequency": "3x per week",
        "obligation_type": "exercise",
        "instructions": "Stop if you feel unwell.",
    }
    assert candidate.citations[0].excerpt.startswith("Walk for 20 minutes.")

    item_chain = db.table.return_value
    item_chain.insert.assert_any_call(
        {
            "plan_version_id": str(UUID(int=204)),
            "source_fact_id": str(fact_id),
            "category": "movement",
            "title": "Walk for 20 minutes.",
            "instructions": "Stop if you feel unwell.",
            "frequency": "3x per week",
            "confidence_score": 1.0,
            "uncertainty": [],
            "conflict": {},
            "blocker_reason": None,
        }
    )
