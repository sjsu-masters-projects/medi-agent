"""Unit tests for RiskScoreService.calculate_risk_level — pure function tests.

Tests the risk classification algorithm with all boundary conditions.
No DB required — these tests exercise the pure calculate_risk_level() method.
"""

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.risk_score_service import RiskScoreService, _humanize_delta


def _response(*, data=None, count=None):
    return SimpleNamespace(data=data, count=count)


class TestCalculateRiskLevel:
    """Tests for the pure risk level calculation function."""

    # Mock DB — not needed for calculate_risk_level (pure function)
    @pytest.fixture
    def service(self):
        return RiskScoreService(db=None)  # type: ignore[arg-type]

    # ── HIGH risk ──────────────────────────────────────────────────────

    def test_high_risk_when_adherence_below_60(self, service):
        result = service.calculate_risk_level(
            adherence_score=0.55, open_adr_count=0, recent_symptom_severity=0
        )
        assert result == "high"

    def test_high_risk_exactly_at_60_threshold(self, service):
        """Adherence = exactly 0.60 should be MEDIUM, not HIGH."""
        result = service.calculate_risk_level(
            adherence_score=0.60, open_adr_count=0, recent_symptom_severity=0
        )
        assert result == "medium"

    def test_high_risk_below_threshold(self, service):
        result = service.calculate_risk_level(
            adherence_score=0.59, open_adr_count=0, recent_symptom_severity=0
        )
        assert result == "high"

    def test_high_risk_from_open_adr(self, service):
        result = service.calculate_risk_level(
            adherence_score=0.95, open_adr_count=1, recent_symptom_severity=0
        )
        assert result == "high"

    def test_high_risk_from_multiple_adrs(self, service):
        result = service.calculate_risk_level(
            adherence_score=0.90, open_adr_count=3, recent_symptom_severity=0
        )
        assert result == "high"

    def test_high_risk_from_severe_symptoms(self, service):
        result = service.calculate_risk_level(
            adherence_score=0.85, open_adr_count=0, recent_symptom_severity=8
        )
        assert result == "high"

    def test_high_risk_severity_exactly_8(self, service):
        """Severity of 8 exactly triggers HIGH risk."""
        result = service.calculate_risk_level(
            adherence_score=0.90, open_adr_count=0, recent_symptom_severity=8
        )
        assert result == "high"

    def test_high_risk_severity_10(self, service):
        result = service.calculate_risk_level(
            adherence_score=0.90, open_adr_count=0, recent_symptom_severity=10
        )
        assert result == "high"

    def test_high_risk_all_signals_high(self, service):
        result = service.calculate_risk_level(
            adherence_score=0.40, open_adr_count=2, recent_symptom_severity=9
        )
        assert result == "high"

    # ── MEDIUM risk ────────────────────────────────────────────────────

    def test_medium_risk_borderline_adherence(self, service):
        result = service.calculate_risk_level(
            adherence_score=0.70, open_adr_count=0, recent_symptom_severity=0
        )
        assert result == "medium"

    def test_medium_risk_from_moderate_severity(self, service):
        result = service.calculate_risk_level(
            adherence_score=0.85, open_adr_count=0, recent_symptom_severity=5
        )
        assert result == "medium"

    def test_medium_risk_severity_7(self, service):
        result = service.calculate_risk_level(
            adherence_score=0.90, open_adr_count=0, recent_symptom_severity=7
        )
        assert result == "medium"

    def test_medium_risk_low_adherence_no_adr(self, service):
        result = service.calculate_risk_level(
            adherence_score=0.65, open_adr_count=0, recent_symptom_severity=2
        )
        assert result == "medium"

    # ── LOW risk ───────────────────────────────────────────────────────

    def test_low_risk_all_clear(self, service):
        result = service.calculate_risk_level(
            adherence_score=0.90, open_adr_count=0, recent_symptom_severity=0
        )
        assert result == "low"

    def test_low_risk_perfect_adherence(self, service):
        result = service.calculate_risk_level(
            adherence_score=1.0, open_adr_count=0, recent_symptom_severity=0
        )
        assert result == "low"

    def test_low_risk_exactly_80_percent(self, service):
        """Adherence = 0.80 with no ADR/severity should be LOW."""
        result = service.calculate_risk_level(
            adherence_score=0.80, open_adr_count=0, recent_symptom_severity=0
        )
        assert result == "low"

    def test_low_risk_mild_symptoms_ok(self, service):
        """Severity 4 (below medium threshold of 5) should be LOW."""
        result = service.calculate_risk_level(
            adherence_score=0.85, open_adr_count=0, recent_symptom_severity=4
        )
        assert result == "low"

    def test_zero_values(self, service):
        result = service.calculate_risk_level(
            adherence_score=0.0, open_adr_count=0, recent_symptom_severity=0
        )
        # adherence=0.0 is below 0.60 → HIGH
        assert result == "high"

    # ── Return type ────────────────────────────────────────────────────

    def test_return_values_are_valid_literals(self, service):
        """Ensure only valid RiskLevel strings are returned."""
        valid = {"low", "medium", "high"}
        test_cases = [
            (0.0, 0, 0),
            (0.50, 0, 0),
            (0.70, 0, 0),
            (0.85, 0, 3),
            (0.95, 1, 0),
            (0.99, 0, 9),
        ]
        for adherence, adrs, severity in test_cases:
            result = service.calculate_risk_level(adherence, adrs, severity)
            assert result in valid, (
                f"Unexpected result '{result}' for inputs: {adherence}, {adrs}, {severity}"
            )

    def test_unknown_when_no_adherence_and_no_medium_or_high_signals(self, service):
        result = service.calculate_risk_level(
            adherence_score=None,
            open_adr_count=0,
            recent_symptom_severity=4,
        )
        assert result == "unknown"

    def test_medium_when_no_adherence_but_symptoms_are_moderate(self, service):
        result = service.calculate_risk_level(
            adherence_score=None,
            open_adr_count=0,
            recent_symptom_severity=5,
        )
        assert result == "medium"


class TestRiskSignalFetching:
    @pytest.fixture
    def service(self):
        db = MagicMock()
        chain = MagicMock()
        for method in ("select", "eq", "gte", "in_", "order", "limit", "single"):
            getattr(chain, method).return_value = chain
        db.table.return_value = chain
        return RiskScoreService(db=db)

    @pytest.mark.asyncio
    async def test_fetch_adherence_score_returns_completion_ratio(self, service):
        service._execute = AsyncMock(  # type: ignore[method-assign]
            return_value=_response(
                data=[
                    {"status": "completed"},
                    {"status": "completed"},
                    {"status": "skipped"},
                ]
            )
        )

        score = await service._fetch_adherence_score(uuid4())

        assert score == pytest.approx(2 / 3)

    @pytest.mark.asyncio
    async def test_fetch_recent_symptom_severity_uses_max_and_defaults_missing_values(self, service):
        service._execute = AsyncMock(  # type: ignore[method-assign]
            return_value=_response(
                data=[
                    {"severity": 4},
                    {"severity": "9"},
                    {},
                ]
            )
        )

        severity = await service._fetch_recent_symptom_severity(uuid4())

        assert severity == 9

    @pytest.mark.asyncio
    async def test_fetch_last_activity_prefers_newer_symptom_report(self, service, monkeypatch):
        service._execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                _response(
                    data=[
                        {
                            "logged_at": "2026-04-08T10:00:00Z",
                            "status": "completed",
                            "target_type": "medication",
                        }
                    ]
                ),
                _response(data=[{"created_at": "2026-04-08T11:00:00Z", "symptom": "cough"}]),
            ]
        )
        monkeypatch.setattr("app.services.risk_score_service._humanize_delta", lambda _: "2h ago")

        activity = await service._fetch_last_activity(uuid4())

        assert activity == "Reported 'cough' 2h ago"

    @pytest.mark.asyncio
    async def test_fetch_last_activity_falls_back_to_log_when_symptom_timestamp_is_invalid(
        self, service, monkeypatch
    ):
        service._execute = AsyncMock(  # type: ignore[method-assign]
            side_effect=[
                _response(
                    data=[
                        {
                            "logged_at": "2026-04-08T10:00:00Z",
                            "status": "completed",
                            "target_type": "obligation",
                        }
                    ]
                ),
                _response(data=[{"created_at": "not-a-date", "symptom": "cough"}]),
            ]
        )
        monkeypatch.setattr("app.services.risk_score_service._humanize_delta", lambda _: "3h ago")

        activity = await service._fetch_last_activity(uuid4())

        assert activity == "Logged obligation 3h ago"

    @pytest.mark.asyncio
    async def test_get_patient_risk_builds_response_from_signals(self, service):
        patient_id = uuid4()
        service._execute = AsyncMock(  # type: ignore[method-assign]
            return_value=_response(data={"id": str(patient_id), "email": "patient@example.com"})
        )
        service._fetch_adherence_score = AsyncMock(return_value=None)  # type: ignore[method-assign]
        service._fetch_open_adr_count = AsyncMock(return_value=0)  # type: ignore[method-assign]
        service._fetch_recent_symptom_severity = AsyncMock(return_value=6)  # type: ignore[method-assign]
        service._fetch_active_med_count = AsyncMock(return_value=3)  # type: ignore[method-assign]
        service._fetch_last_activity = AsyncMock(  # type: ignore[method-assign]
            return_value="Reported 'fatigue' 2h ago"
        )

        result = await service.get_patient_risk(patient_id)

        assert result.patient_id == patient_id
        assert result.first_name == "Unknown"
        assert result.last_name == ""
        assert result.risk_level == "medium"
        assert result.adherence_score == 0.0
        assert result.active_med_count == 3
        assert result.last_activity == "Reported 'fatigue' 2h ago"


class TestHumanizeDelta:
    """Tests for the _humanize_delta helper function."""

    def test_minutes(self):
        assert _humanize_delta(timedelta(seconds=300)) == "5m ago"

    def test_hours(self):
        assert _humanize_delta(timedelta(hours=3)) == "3h ago"

    def test_days(self):
        assert _humanize_delta(timedelta(days=5)) == "5d ago"

    def test_minimum_is_1_minute(self):
        assert _humanize_delta(timedelta(seconds=30)) == "1m ago"

    def test_boundary_exactly_one_hour(self):
        result = _humanize_delta(timedelta(hours=1))
        assert result == "1h ago"

    def test_boundary_exactly_one_day(self):
        result = _humanize_delta(timedelta(days=1))
        assert result == "1d ago"
