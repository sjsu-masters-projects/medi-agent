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
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from supabase import Client

from app.core.exceptions import ExternalServiceError, ValidationError
from app.services.reminder_schedule_service import (
    ReminderScheduleService,
    count_occurrences_in_period,
    occurrence_datetimes_for_day,
    validate_timezone_name,
)

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
            raise ExternalServiceError("Supabase", "Failed to log adherence")
        return result.data[0]

    async def get_stats(self, patient_id: UUID, period_days: int = 30) -> Any:
        """Calculate adherence statistics over a time window.

        Returns overall, medication-specific, and obligation-specific scores
        plus the current streak.
        """
        timezone_name = await self._get_patient_timezone(patient_id)
        timezone_info = ZoneInfo(timezone_name)
        today_local = datetime.now(timezone_info).date()
        start_date = today_local - timedelta(days=period_days - 1)
        cutoff = (
            datetime.combine(start_date, datetime.min.time(), tzinfo=timezone_info)
            .astimezone(UTC)
            .isoformat()
        )

        # Fetch all logs in the window
        logs = (
            self.db.table("adherence_logs")
            .select("*")
            .eq("patient_id", str(patient_id))
            .gte("logged_at", cutoff)
            .execute()
        )
        log_data = cast(list[dict[str, Any]], logs.data or [])

        active_medications = cast(
            list[dict[str, Any]],
            (
                self.db.table("medications")
                .select("id")
                .eq("patient_id", str(patient_id))
                .eq("is_active", True)
                .execute()
            ).data
            or [],
        )
        active_obligations = cast(
            list[dict[str, Any]],
            (
                self.db.table("obligations")
                .select("id")
                .eq("patient_id", str(patient_id))
                .eq("is_active", True)
                .execute()
            ).data
            or [],
        )
        schedule_map = await ReminderScheduleService(self.db).get_schedule_map_for_patient(
            str(patient_id)
        )

        med_expected = sum(
            self._expected_events_for_target(
                schedule_map.get(("medication", str(item["id"]))),
                start_date,
                today_local,
                period_days,
            )
            for item in active_medications
        )
        obl_expected = sum(
            self._expected_events_for_target(
                schedule_map.get(("obligation", str(item["id"]))),
                start_date,
                today_local,
                period_days,
            )
            for item in active_obligations
        )
        total_expected = med_expected + obl_expected
        if total_expected == 0:
            return self._empty_stats(patient_id, period_days)

        med_completed = self._count_completed_events(
            log_data,
            target_type="medication",
            timezone_info=timezone_info,
        )
        obl_completed = self._count_completed_events(
            log_data,
            target_type="obligation",
            timezone_info=timezone_info,
        )
        total_completed = med_completed + obl_completed

        return {
            "patient_id": str(patient_id),
            "overall_score": min(total_completed / total_expected, 1.0),
            "medication_score": min(med_completed / med_expected, 1.0) if med_expected else 0.0,
            "obligation_score": min(obl_completed / obl_expected, 1.0) if obl_expected else 0.0,
            "current_streak_days": self._calculate_streak_with_schedules(
                log_data,
                active_medications,
                active_obligations,
                schedule_map,
                start_date,
                today_local,
                timezone_info,
            ),
            "period_days": period_days,
            "total_expected": total_expected,
            "total_completed": total_completed,
        }

    # ── Helpers ─────────────────────────────────────────

    @staticmethod
    def _count_completed_events(
        logs: list[dict[str, Any]],
        *,
        target_type: str,
        timezone_info: ZoneInfo,
    ) -> int:
        completed_keys: set[tuple[str, str]] = set()
        for log in logs:
            if log["target_type"] != target_type or log["status"] not in {"completed", "taken"}:
                continue
            scheduled_time = log.get("scheduled_time")
            if scheduled_time:
                completed_keys.add((str(log["target_id"]), str(scheduled_time)))
                continue
            local_day = (
                datetime.fromisoformat(str(log["logged_at"]).replace("Z", "+00:00"))
                .astimezone(timezone_info)
                .date()
            )
            completed_keys.add((str(log["target_id"]), local_day.isoformat()))
        return len(completed_keys)

    def _calculate_streak_with_schedules(
        self,
        logs: list[dict[str, Any]],
        active_medications: list[dict[str, Any]],
        active_obligations: list[dict[str, Any]],
        schedule_map: dict[tuple[str, str], dict[str, Any]],
        start_date: date,
        today_local: date,
        timezone_info: ZoneInfo,
    ) -> int:
        """Count consecutive days (backwards from today) with full completion."""
        if not logs:
            return 0

        completed_by_date: dict[str, int] = {}
        for log in logs:
            if log["status"] not in {"completed", "taken"}:
                continue
            day = (
                (
                    datetime.fromisoformat(str(log["scheduled_time"]).replace("Z", "+00:00"))
                    if log.get("scheduled_time")
                    else datetime.fromisoformat(str(log["logged_at"]).replace("Z", "+00:00"))
                )
                .astimezone(timezone_info)
                .date()
            )
            day_str = day.isoformat()
            completed_by_date[day_str] = completed_by_date.get(day_str, 0) + 1

        streak = 0
        current = today_local
        while current >= start_date:
            expected = 0
            for item in active_medications:
                expected += len(
                    occurrence_datetimes_for_day(
                        schedule_map.get(("medication", str(item["id"])))
                        or {"times_of_day": [], "days_of_week": [], "is_enabled": False},
                        current,
                    )
                ) or (1 if ("medication", str(item["id"])) not in schedule_map else 0)
            for item in active_obligations:
                expected += len(
                    occurrence_datetimes_for_day(
                        schedule_map.get(("obligation", str(item["id"])))
                        or {"times_of_day": [], "days_of_week": [], "is_enabled": False},
                        current,
                    )
                ) or (1 if ("obligation", str(item["id"])) not in schedule_map else 0)
            if expected == 0:
                current -= timedelta(days=1)
                continue
            if completed_by_date.get(current.isoformat(), 0) >= expected:
                streak += 1
            else:
                break
            current -= timedelta(days=1)
        return streak

    @staticmethod
    def _calculate_streak(logs: list[dict[str, Any]], daily_expected: int) -> int:
        """Backward-compatible streak helper used in unit tests."""
        if not logs or daily_expected <= 0:
            return 0

        completed_by_date: dict[str, int] = {}
        for log in logs:
            if log.get("status") not in {"completed", "taken"}:
                continue
            logged_at = str(log.get("logged_at") or "")
            day = logged_at[:10]
            if not day:
                continue
            completed_by_date[day] = completed_by_date.get(day, 0) + 1

        if not completed_by_date:
            return 0

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
    def _expected_events_for_target(
        schedule: dict[str, Any] | None,
        start_date: date,
        end_date: date,
        fallback_period_days: int,
    ) -> int:
        if schedule:
            return count_occurrences_in_period(schedule, start_date, end_date)
        return fallback_period_days

    async def _get_patient_timezone(self, patient_id: UUID) -> str:
        result = (
            self.db.table("patients")
            .select("timezone")
            .eq("id", str(patient_id))
            .single()
            .execute()
        )
        patient_row = cast(dict[str, Any], result.data or {})
        timezone = str(patient_row.get("timezone") or "UTC")
        try:
            return validate_timezone_name(timezone)
        except ValidationError:
            return "UTC"

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
