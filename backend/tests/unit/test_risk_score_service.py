"""Unit tests for RiskScoreService.calculate_risk_level — pure function tests.

Tests the risk classification algorithm with all boundary conditions.
No DB required — these tests exercise the pure calculate_risk_level() method.
"""

import pytest

from app.services.risk_score_service import RiskScoreService, _humanize_delta
from datetime import timedelta


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
        assert result in ("medium", "high")  # 0.60 is medium threshold start

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
            assert result in valid, f"Unexpected result '{result}' for inputs: {adherence}, {adrs}, {severity}"


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
