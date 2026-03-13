"""Adherence service — log medication/obligation completion and calculate scores.

Scoring algorithm:
    score = completed_count / expected_count (over period_days window)
    streak = consecutive days with 100% completion (current, not historical)

The 'expected' count is derived from active medications + obligations
and their frequencies. For MVP, we use a simplified model where
each active item = 1 expected event per day.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class AdherenceService:
    """Adherence tracking and scoring."""

    def __init__(self, db: Client) -> None:
        self.db = db

    async def log_adherence(self, patient_id: UUID, data: dict[str, Any]) -> Any:
        """Log a single adherence event (med taken, obligation done, or skipped).

        Validates that the target (medication or obligation) exists
        and belongs to the patient.
        """
        target_type = data["target_type"]
        target_id = data["target_id"]

        # Verify the target exists and belongs to the patient
        table = "medications" if target_type == "medication" else "obligations"
        target = (
            self.db.table(table)
            .select("id")
            .eq("id", str(target_id))
            .eq("patient_id", str(patient_id))
            .execute()
        )
        if not target.data:
            raise ValidationError(
                f"{target_type.capitalize()} '{target_id}' not found for this patient"
            )

        row = {
            "patient_id": str(patient_id),
            "target_type": target_type,
            "target_id": str(target_id),
            "status": data["status"],
            "scheduled_time": data.get("scheduled_time"),
            "notes": data.get("notes"),
        }
        result = self.db.table("adherence_logs").insert(row).execute()
        if not result.data:
            raise Exception("Failed to log adherence")
        return result.data[0]

    async def get_stats(self, patient_id: UUID, period_days: int = 30) -> Any:
        """Calculate adherence statistics over a time window.

        Returns overall, medication-specific, and obligation-specific scores
        plus the current streak.
        """
        cutoff = (datetime.now(UTC) - timedelta(days=period_days)).isoformat()

        # Fetch all logs in the window
        logs = (
            self.db.table("adherence_logs")
            .select("*")
            .eq("patient_id", str(patient_id))
            .gte("logged_at", cutoff)
            .execute()
        )
        log_data = cast(list[dict[str, Any]], logs.data or [])

        # Count active items to estimate expected events
        med_count = len(
            (
                self.db.table("medications")
                .select("id")
                .eq("patient_id", str(patient_id))
                .eq("is_active", True)
                .execute()
            ).data
            or []
        )
        obl_count = len(
            (
                self.db.table("obligations")
                .select("id")
                .eq("patient_id", str(patient_id))
                .eq("is_active", True)
                .execute()
            ).data
            or []
        )

        # Simplified: 1 expected event per active item per day
        total_expected = (med_count + obl_count) * period_days
        if total_expected == 0:
            return self._empty_stats(patient_id, period_days)

        # Count completed events
        med_completed = sum(
            1
            for log in log_data
            if log["target_type"] == "medication" and log["status"] == "completed"
        )
        obl_completed = sum(
            1
            for log in log_data
            if log["target_type"] == "obligation" and log["status"] == "completed"
        )
        total_completed = med_completed + obl_completed

        med_expected = med_count * period_days
        obl_expected = obl_count * period_days

        return {
            "patient_id": str(patient_id),
            "overall_score": min(total_completed / total_expected, 1.0),
            "medication_score": min(med_completed / med_expected, 1.0) if med_expected else 0.0,
            "obligation_score": min(obl_completed / obl_expected, 1.0) if obl_expected else 0.0,
            "current_streak_days": self._calculate_streak(log_data, med_count + obl_count),
            "period_days": period_days,
            "total_expected": total_expected,
            "total_completed": total_completed,
        }

    # ── Helpers ─────────────────────────────────────────

    @staticmethod
    def _calculate_streak(logs: list[dict[str, Any]], daily_expected: int) -> int:
        """Count consecutive days (backwards from today) with full completion."""
        if not logs or daily_expected == 0:
            return 0

        # Group completed logs by date
        completed_by_date: dict[str, int] = {}
        for log in logs:
            if log["status"] == "completed":
                day = log["logged_at"][:10]  # "2025-01-15"
                completed_by_date[day] = completed_by_date.get(day, 0) + 1

        # Walk backwards from today
        streak = 0
        today = datetime.now(UTC).date()
        for i in range(len(completed_by_date) + 1):
            day_str = (today - timedelta(days=i)).isoformat()
            if completed_by_date.get(day_str, 0) >= daily_expected:
                streak += 1
            else:
                break
        return streak

    @staticmethod
    def _empty_stats(patient_id: UUID, period_days: int) -> Any:
        return {
            "patient_id": str(patient_id),
            "overall_score": 0.0,
            "medication_score": 0.0,
            "obligation_score": 0.0,
            "current_streak_days": 0,
            "period_days": period_days,
            "total_expected": 0,
            "total_completed": 0,
        }
