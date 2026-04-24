"""Today Feed — aggregates meds + obligations across all providers."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from supabase import Client

from app.services.reminder_schedule_service import (
    ReminderScheduleService,
    infer_frequency_guidance,
    occurrence_datetimes_for_day,
    validate_timezone_name,
)

logger = logging.getLogger(__name__)


class FeedService:
    """Patient-scoped feed operations."""

    def __init__(self, db: Client) -> None:
        self.db = db

    async def get_today(
        self,
        patient_id: UUID,
        target_date: date | None = None,
        timezone: str | None = None,
    ) -> dict[str, Any]:
        """Get today's feed for a patient."""
        patient_row = await self._get_patient(patient_id)
        effective_timezone = validate_timezone_name(
            timezone or str(patient_row.get("timezone") or "UTC")
        )
        timezone_info = ZoneInfo(effective_timezone)
        if target_date is None:
            target_date = datetime.now(timezone_info).date()

        # Fetch data concurrently for performance
        medications, obligations, adherence_logs, reminder_map = await asyncio.gather(
            self._get_medications(patient_id),
            self._get_obligations(patient_id),
            self._get_today_adherence(patient_id, target_date, effective_timezone),
            self._get_reminder_schedule_map(patient_id),
        )

        adherence_occurrence_map, adherence_unscheduled_map = self._build_adherence_maps(
            adherence_logs
        )

        # Transform to tasks
        tasks: list[dict[str, Any]] = []
        tasks.extend(
            self._medications_to_tasks(
                medications,
                target_date,
                reminder_map,
                adherence_occurrence_map,
                adherence_unscheduled_map,
            )
        )
        tasks.extend(
            self._obligations_to_tasks(
                obligations,
                target_date,
                reminder_map,
                adherence_occurrence_map,
                adherence_unscheduled_map,
            )
        )

        # Sort by scheduled time
        tasks.sort(
            key=lambda t: (
                t.get("scheduled_at") or "9999-99-99T99:99:99+00:00",
                t.get("name") or "",
            )
        )

        # Calculate summary
        summary = self._calculate_summary(tasks)

        return {
            "date": target_date.isoformat(),
            "timezone": effective_timezone,
            "tasks": tasks,
            "summary": summary,
        }

    async def _get_patient(self, patient_id: UUID) -> dict[str, Any]:
        result = (
            self.db.table("patients")
            .select("id, timezone")
            .eq("id", str(patient_id))
            .single()
            .execute()
        )
        return cast(dict[str, Any], result.data or {"id": str(patient_id), "timezone": "UTC"})

    async def _get_medications(self, patient_id: UUID) -> list[dict[str, Any]]:
        """Fetch active medications with provider info."""
        try:
            result = (
                self.db.table("medications")
                .select(
                    """
                    id,
                    name,
                    dosage,
                    frequency,
                    instructions,
                    prescribed_by_care_team_id,
                    care_teams!prescribed_by_care_team_id(
                        id,
                        clinicians(
                            id,
                            first_name,
                            last_name,
                            specialty,
                            clinic_name
                        )
                    )
                """
                )
                .eq("patient_id", str(patient_id))
                .eq("is_active", True)
                .execute()
            )
            return result.data or []  # type: ignore[return-value]
        except Exception as e:
            logger.error(f"Failed to fetch medications: {e}")
            return []

    async def _get_obligations(self, patient_id: UUID) -> list[dict[str, Any]]:
        """Fetch active obligations with provider info."""
        try:
            result = (
                self.db.table("obligations")
                .select(
                    """
                    id,
                    description,
                    notes,
                    frequency,
                    obligation_type,
                    set_by_care_team_id,
                    care_teams!set_by_care_team_id(
                        id,
                        clinicians(
                            id,
                            first_name,
                            last_name,
                            specialty,
                            clinic_name
                        )
                    )
                """
                )
                .eq("patient_id", str(patient_id))
                .eq("is_active", True)
                .execute()
            )
            return result.data or []  # type: ignore[return-value]
        except Exception as e:
            logger.error(f"Failed to fetch obligations: {e}")
            return []

    async def _get_today_adherence(
        self, patient_id: UUID, target_date: date, timezone_name: str
    ) -> list[dict[str, Any]]:
        """Fetch today's adherence logs."""
        try:
            timezone_info = ZoneInfo(timezone_name)
            local_start = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone_info)
            local_end = local_start + timedelta(days=1)
            today_start = local_start.astimezone(UTC)
            today_end = local_end.astimezone(UTC)

            result = (
                self.db.table("adherence_logs")
                .select("target_id, target_type, status, logged_at, scheduled_time")
                .eq("patient_id", str(patient_id))
                .gte("logged_at", today_start.isoformat())
                .lt("logged_at", today_end.isoformat())
                .execute()
            )
            return result.data or []  # type: ignore[return-value]
        except Exception as e:
            logger.error(f"Failed to fetch adherence logs: {e}")
            return []

    async def _get_reminder_schedule_map(
        self, patient_id: UUID
    ) -> dict[tuple[str, str], dict[str, Any]]:
        service = ReminderScheduleService(self.db)
        return await service.get_schedule_map_for_patient(str(patient_id))

    def _build_adherence_maps(
        self, logs: list[dict[str, Any]]
    ) -> tuple[dict[tuple[str, str, str], dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
        """Build exact-occurrence and unscheduled adherence lookups."""
        occurrence_map: dict[tuple[str, str, str], dict[str, Any]] = {}
        unscheduled_map: dict[tuple[str, str], dict[str, Any]] = {}
        for log in logs:
            target_type = str(log["target_type"])
            target_id = str(log["target_id"])
            scheduled_time = log.get("scheduled_time")
            if scheduled_time:
                occurrence_key = (target_type, target_id, str(scheduled_time))
                if (
                    occurrence_key not in occurrence_map
                    or log["logged_at"] > occurrence_map[occurrence_key]["logged_at"]
                ):
                    occurrence_map[occurrence_key] = log
            else:
                key = (target_type, target_id)
                if (
                    key not in unscheduled_map
                    or log["logged_at"] > unscheduled_map[key]["logged_at"]
                ):
                    unscheduled_map[key] = log
        return occurrence_map, unscheduled_map

    def _medications_to_tasks(
        self,
        medications: list[dict[str, Any]],
        target_date: date,
        reminder_map: dict[tuple[str, str], dict[str, Any]],
        adherence_occurrence_map: dict[tuple[str, str, str], dict[str, Any]],
        adherence_unscheduled_map: dict[tuple[str, str], dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Transform medications to task format."""
        tasks: list[dict[str, Any]] = []
        for med in medications:
            schedule = reminder_map.get(("medication", str(med["id"])))
            if schedule:
                tasks.extend(
                    self._scheduled_tasks_for_item(
                        target_type="medication",
                        target=med,
                        target_date=target_date,
                        schedule=schedule,
                        adherence_occurrence_map=adherence_occurrence_map,
                    )
                )
                continue

            adherence = adherence_unscheduled_map.get(("medication", str(med["id"])))
            guidance = infer_frequency_guidance(str(med.get("frequency") or ""))
            tasks.append(
                {
                    "id": f"medication:{med['id']}:unscheduled",
                    "type": "medication",
                    "target_id": med["id"],
                    "name": f"{med['name']} {med['dosage']}",
                    "description": med.get("instructions"),
                    "frequency": med["frequency"],
                    "scheduled_time": None,
                    "scheduled_at": None,
                    "status": self._determine_status(adherence),
                    "completed_at": adherence.get("logged_at") if adherence else None,
                    "requires_schedule_configuration": bool(
                        guidance["supports_automatic_reminders"]
                        and guidance.get("recommended_times_per_day")
                    ),
                    "provider": self._extract_provider(med.get("care_teams")),
                }
            )
        return tasks

    def _obligations_to_tasks(
        self,
        obligations: list[dict[str, Any]],
        target_date: date,
        reminder_map: dict[tuple[str, str], dict[str, Any]],
        adherence_occurrence_map: dict[tuple[str, str, str], dict[str, Any]],
        adherence_unscheduled_map: dict[tuple[str, str], dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Transform obligations to task format."""
        tasks: list[dict[str, Any]] = []
        for obl in obligations:
            schedule = reminder_map.get(("obligation", str(obl["id"])))
            if schedule:
                tasks.extend(
                    self._scheduled_tasks_for_item(
                        target_type="obligation",
                        target=obl,
                        target_date=target_date,
                        schedule=schedule,
                        adherence_occurrence_map=adherence_occurrence_map,
                    )
                )
                continue

            adherence = adherence_unscheduled_map.get(("obligation", str(obl["id"])))
            guidance = infer_frequency_guidance(str(obl.get("frequency") or ""))
            tasks.append(
                {
                    "id": f"obligation:{obl['id']}:unscheduled",
                    "type": "obligation",
                    "target_id": obl["id"],
                    "name": obl["description"],
                    "description": obl.get("notes"),
                    "frequency": obl["frequency"],
                    "scheduled_time": None,
                    "scheduled_at": None,
                    "status": self._determine_status(adherence),
                    "completed_at": adherence.get("logged_at") if adherence else None,
                    "requires_schedule_configuration": bool(
                        guidance["supports_automatic_reminders"]
                        and guidance.get("recommended_times_per_day")
                    ),
                    "provider": self._extract_provider(obl.get("care_teams")),
                }
            )
        return tasks

    def _scheduled_tasks_for_item(
        self,
        *,
        target_type: str,
        target: dict[str, Any],
        target_date: date,
        schedule: dict[str, Any],
        adherence_occurrence_map: dict[tuple[str, str, str], dict[str, Any]],
    ) -> list[dict[str, Any]]:
        occurrences = occurrence_datetimes_for_day(schedule, target_date)
        if not occurrences:
            return []

        tasks: list[dict[str, Any]] = []
        for scheduled_at, local_time in occurrences:
            adherence = adherence_occurrence_map.get((target_type, str(target["id"]), scheduled_at))
            name = (
                f"{target['name']} {target['dosage']}"
                if target_type == "medication"
                else target["description"]
            )
            tasks.append(
                {
                    "id": f"{target_type}:{target['id']}:{scheduled_at}",
                    "type": target_type,
                    "target_id": target["id"],
                    "name": name,
                    "description": target.get("instructions") or target.get("notes"),
                    "frequency": target["frequency"],
                    "scheduled_time": local_time,
                    "scheduled_at": scheduled_at,
                    "status": self._determine_status(adherence),
                    "completed_at": adherence.get("logged_at") if adherence else None,
                    "requires_schedule_configuration": False,
                    "provider": self._extract_provider(target.get("care_teams")),
                }
            )
        return tasks

    def _determine_status(self, adherence: dict[str, Any] | None) -> str:
        """Determine task status from adherence log."""
        if not adherence:
            return "pending"

        status = adherence.get("status")
        if status in ["completed", "taken"]:
            return "completed"
        elif status == "skipped":
            return "skipped"
        else:
            return "pending"

    def _extract_provider(self, care_teams: dict[str, Any] | None) -> dict[str, Any] | None:
        """Extract provider info from care_teams join."""
        if not care_teams:
            return None

        clinician = care_teams.get("clinicians")
        if not clinician:
            return None

        return {
            "id": clinician["id"],
            "name": f"Dr. {clinician['first_name']} {clinician['last_name']}",
            "specialty": clinician["specialty"],
            "clinic_name": clinician["clinic_name"],
        }

    def _calculate_summary(self, tasks: list[dict[str, Any]]) -> dict[str, int]:
        """Calculate task summary statistics."""
        total = len(tasks)
        completed = sum(1 for t in tasks if t["status"] == "completed")
        pending = sum(1 for t in tasks if t["status"] == "pending")
        skipped = sum(1 for t in tasks if t["status"] == "skipped")
        missed = sum(1 for t in tasks if t["status"] == "missed")

        return {
            "total": total,
            "completed": completed,
            "pending": pending,
            "skipped": skipped,
            "missed": missed,
        }
