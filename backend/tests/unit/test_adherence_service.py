"""Test adherence scoring algorithm — the most complex logic in the backend."""

from app.services.adherence_service import AdherenceService


class TestStreakCalculation:
    """Tests for _calculate_streak — pure function, no DB."""

    def test_empty_logs_returns_zero(self):
        assert AdherenceService._calculate_streak([], daily_expected=2) == 0

    def test_zero_expected_returns_zero(self):
        logs = [{"status": "completed", "logged_at": "2025-01-15T10:00:00"}]
        assert AdherenceService._calculate_streak(logs, daily_expected=0) == 0

    def test_no_completed_logs_returns_zero(self):
        logs = [{"status": "skipped", "logged_at": "2025-01-15T10:00:00"}]
        assert AdherenceService._calculate_streak(logs, daily_expected=1) == 0


class TestEmptyStats:
    """Tests for _empty_stats — edge case when patient has no meds/obligations."""

    def test_all_scores_zero(self):
        from uuid import uuid4

        stats = AdherenceService._empty_stats(uuid4(), period_days=30)
        assert stats["overall_score"] == 0.0
        assert stats["medication_score"] == 0.0
        assert stats["obligation_score"] == 0.0
        assert stats["current_streak_days"] == 0
        assert stats["total_expected"] == 0
        assert stats["total_completed"] == 0
        assert stats["period_days"] == 30
