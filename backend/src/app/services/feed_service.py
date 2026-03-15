"""Today Feed — aggregates meds + obligations across all providers."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from supabase import Client

logger = logging.getLogger(__name__)


class FeedService:
    """Patient-scoped feed operations."""

    def __init__(self, db: Client) -> None:
        self.db = db

    async def get_today(
        self,
        patient_id: UUID,
        target_date: date | None = None,
        timezone: str = "UTC",
    ) -> dict[str, Any]:
        """Get today's feed for a patient."""
        if target_date is None:
            target_date = datetime.now().date()

        # Fetch data concurrently for performance
        medications, obligations, adherence_logs = await asyncio.gather(
            self._get_medications(patient_id),
            self._get_obligations(patient_id),
            self._get_today_adherence(patient_id, target_date),
        )

        # Build adherence lookup
        adherence_map = self._build_adherence_map(adherence_logs)

        # Transform to tasks
        tasks = []
        tasks.extend(self._medications_to_tasks(medications, adherence_map))
        tasks.extend(self._obligations_to_tasks(obligations, adherence_map))

        # Sort by scheduled time
        tasks.sort(key=lambda t: t.get("scheduled_time") or "99:99:99")

        # Calculate summary
        summary = self._calculate_summary(tasks)

        return {
            "date": target_date.isoformat(),
            "timezone": timezone,
            "tasks": tasks,
            "summary": summary,
        }

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
            logger.error(f"Failed to fetch medications: {e}", extra={"patient_id": str(patient_id)})
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
            logger.error(f"Failed to fetch obligations: {e}", extra={"patient_id": str(patient_id)})
            return []

    async def _get_today_adherence(
        self, patient_id: UUID, target_date: date
    ) -> list[dict[str, Any]]:
        """Fetch today's adherence logs."""
        try:
            # Calculate date range for today
            today_start = datetime.combine(target_date, datetime.min.time())
            today_end = today_start + timedelta(days=1)

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
            logger.error(
                f"Failed to fetch adherence logs: {e}", extra={"patient_id": str(patient_id)}
            )
            return []

    def _build_adherence_map(
        self, logs: list[dict[str, Any]]
    ) -> dict[tuple[str, str], dict[str, Any]]:
        """Build lookup: (target_type, target_id) -> latest log."""
        adherence_map: dict[tuple[str, str], dict[str, Any]] = {}
        for log in logs:
            key = (log["target_type"], log["target_id"])
            # Keep most recent log if multiple exist
            if key not in adherence_map or log["logged_at"] > adherence_map[key]["logged_at"]:
                adherence_map[key] = log
        return adherence_map

    def _medications_to_tasks(
        self,
        medications: list[dict[str, Any]],
        adherence_map: dict[tuple[str, str], dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Transform medications to task format."""
        tasks = []
        for med in medications:
            adherence = adherence_map.get(("medication", med["id"]))

            task = {
                "id": str(uuid4()),  # Unique task ID
                "type": "medication",
                "target_id": med["id"],
                "name": f"{med['name']} {med['dosage']}",
                "description": med.get("instructions"),
                "frequency": med["frequency"],
                "scheduled_time": adherence.get("scheduled_time") if adherence else None,
                "status": self._determine_status(adherence),
                "completed_at": adherence.get("logged_at") if adherence else None,
                "provider": self._extract_provider(med.get("care_teams")),
            }
            tasks.append(task)
        return tasks

    def _obligations_to_tasks(
        self,
        obligations: list[dict[str, Any]],
        adherence_map: dict[tuple[str, str], dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Transform obligations to task format."""
        tasks = []
        for obl in obligations:
            adherence = adherence_map.get(("obligation", obl["id"]))

            task = {
                "id": str(uuid4()),
                "type": "obligation",
                "target_id": obl["id"],
                "name": obl["description"],
                "description": None,
                "frequency": obl["frequency"],
                "scheduled_time": adherence.get("scheduled_time") if adherence else None,
                "status": self._determine_status(adherence),
                "completed_at": adherence.get("logged_at") if adherence else None,
                "provider": self._extract_provider(obl.get("care_teams")),
            }
            tasks.append(task)
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
