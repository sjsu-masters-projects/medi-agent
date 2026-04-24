"""Internal cron jobs for reminders and nightly ADR scanning."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from supabase import Client

from app.core.exceptions import ValidationError
from app.db.supabase_execute import execute_async
from app.services.reminder_schedule_service import occurrence_datetimes_for_day

logger = logging.getLogger(__name__)


class CronService:
    """Background job orchestration triggered by Cloud Scheduler."""

    APPOINTMENT_REMINDER_CONFIG = (
        ("24h", 24, "Upcoming appointment tomorrow"),
        ("1h", 1, "Upcoming appointment soon"),
    )
    ADR_FLAG_MIN_SEVERITY = 5
    RUNNING_STALE_AFTER_HOURS = 6

    def __init__(self, db: Client) -> None:
        self.db = db

    async def dispatch_reminders(
        self, *, dry_run: bool = False, window_minutes: int = 15
    ) -> dict[str, Any]:
        """Dispatch reminder notifications for due appointments."""
        job_name = "reminders_dispatch"
        await self._ensure_job_not_running(job_name)
        run = await self._start_run(
            job_name,
            metadata={"dry_run": dry_run, "window_minutes": window_minutes},
        )

        started_at = run["started_at"]
        run_id = run["id"]
        summary: dict[str, Any] = {
            "appointment_24h_candidates": 0,
            "appointment_24h_created": 0,
            "appointment_24h_existing": 0,
            "appointment_1h_candidates": 0,
            "appointment_1h_created": 0,
            "appointment_1h_existing": 0,
            "medication_candidates": 0,
            "medication_created": 0,
            "medication_existing": 0,
            "obligation_candidates": 0,
            "obligation_created": 0,
            "obligation_existing": 0,
        }

        try:
            now = self._utc_now()
            for reminder_kind, hours_before, _title in self.APPOINTMENT_REMINDER_CONFIG:
                result = await self._dispatch_appointment_reminders(
                    now=now,
                    reminder_kind=reminder_kind,
                    hours_before=hours_before,
                    window_minutes=window_minutes,
                    dry_run=dry_run,
                )
                summary[f"appointment_{reminder_kind}_candidates"] = result["candidates"]
                summary[f"appointment_{reminder_kind}_created"] = result["created"]
                summary[f"appointment_{reminder_kind}_existing"] = result["existing"]

            scheduled_result = await self._dispatch_schedule_reminders(
                window_start=now,
                window_end=now + timedelta(minutes=window_minutes),
                dry_run=dry_run,
            )
            for key, value in scheduled_result.items():
                summary[key] = value

            finished = await self._finish_run(
                run_id,
                status="success",
                summary=summary,
            )
            return {
                "run_id": run_id,
                "job_name": job_name,
                "status": "success",
                "dry_run": dry_run,
                "started_at": started_at,
                "finished_at": finished["finished_at"],
                "summary": summary,
            }
        except Exception as exc:
            await self._finish_run(
                run_id,
                status="failed",
                summary=summary,
                error=str(exc),
            )
            raise

    async def run_nightly_adr_scan(
        self,
        *,
        dry_run: bool = False,
        lookback_hours: int | None = None,
        limit: int = 500,
    ) -> dict[str, Any]:
        """Flag newly reported symptoms that should enter the ADR pipeline."""
        job_name = "nightly_adr_scan"
        await self._ensure_job_not_running(job_name)
        run = await self._start_run(
            job_name,
            metadata={
                "dry_run": dry_run,
                "lookback_hours": lookback_hours,
                "limit": limit,
            },
        )

        started_at = run["started_at"]
        run_id = run["id"]
        summary: dict[str, Any] = {
            "lookback_hours": lookback_hours or 24,
            "symptoms_scanned": 0,
            "patients_with_new_symptoms": 0,
            "candidate_flags_created": 0,
            "high_severity_without_active_medications": 0,
        }

        try:
            since = await self._resolve_adr_scan_since(job_name, lookback_hours)
            symptom_rows = await self._fetch_symptom_reports_for_adr_scan(
                since=since,
                limit=limit,
            )
            summary["symptoms_scanned"] = len(symptom_rows)

            patient_ids = sorted({row["patient_id"] for row in symptom_rows})
            summary["patients_with_new_symptoms"] = len(patient_ids)

            active_medications = await self._fetch_active_medication_map(patient_ids)

            candidate_ids: list[str] = []
            high_severity_without_meds = 0
            for row in symptom_rows:
                severity = int(row.get("severity") or 0)
                has_related_medication = bool(row.get("related_medication_id"))
                has_active_medications = bool(active_medications.get(row["patient_id"]))
                should_flag = has_related_medication or (
                    has_active_medications and severity >= self.ADR_FLAG_MIN_SEVERITY
                )

                if should_flag:
                    candidate_ids.append(row["id"])
                elif severity >= self.ADR_FLAG_MIN_SEVERITY:
                    high_severity_without_meds += 1

            summary["candidate_flags_created"] = len(candidate_ids)
            summary["high_severity_without_active_medications"] = high_severity_without_meds
            summary["lookback_hours"] = round((self._utc_now() - since).total_seconds() / 3600, 2)

            if candidate_ids and not dry_run:
                await self._flag_symptom_reports_for_adr(candidate_ids)

            finished = await self._finish_run(
                run_id,
                status="success",
                summary=summary,
            )
            return {
                "run_id": run_id,
                "job_name": job_name,
                "status": "success",
                "dry_run": dry_run,
                "started_at": started_at,
                "finished_at": finished["finished_at"],
                "summary": summary,
            }
        except Exception as exc:
            await self._finish_run(
                run_id,
                status="failed",
                summary=summary,
                error=str(exc),
            )
            raise

    async def _dispatch_appointment_reminders(
        self,
        *,
        now: datetime,
        reminder_kind: str,
        hours_before: int,
        window_minutes: int,
        dry_run: bool,
    ) -> dict[str, int]:
        window_start = now + timedelta(hours=hours_before)
        window_end = window_start + timedelta(minutes=window_minutes)
        appointments = await self._fetch_upcoming_appointments(
            window_start=window_start,
            window_end=window_end,
        )

        if not appointments:
            return {"candidates": 0, "created": 0, "existing": 0}

        candidate_rows = [
            self._build_appointment_notification(
                appointment=appointment,
                reminder_kind=reminder_kind,
                hours_before=hours_before,
                window_start=window_start,
                window_end=window_end,
            )
            for appointment in appointments
        ]
        existing_keys = await self._fetch_existing_notification_keys(
            [row["dedupe_key"] for row in candidate_rows]
        )
        pending_rows = [row for row in candidate_rows if row["dedupe_key"] not in existing_keys]

        if pending_rows and not dry_run:
            await self._insert_notifications(pending_rows)

        return {
            "candidates": len(candidate_rows),
            "created": len(pending_rows),
            "existing": len(candidate_rows) - len(pending_rows),
        }

    async def _dispatch_schedule_reminders(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        dry_run: bool,
    ) -> dict[str, int]:
        if self.db is None:
            return {
                "medication_candidates": 0,
                "medication_created": 0,
                "medication_existing": 0,
                "obligation_candidates": 0,
                "obligation_created": 0,
                "obligation_existing": 0,
            }

        schedules = await self._fetch_enabled_reminder_schedules()
        if not schedules:
            return {
                "medication_candidates": 0,
                "medication_created": 0,
                "medication_existing": 0,
                "obligation_candidates": 0,
                "obligation_created": 0,
                "obligation_existing": 0,
            }

        medication_map = await self._fetch_medication_display_map(
            [str(row["target_id"]) for row in schedules if row.get("target_type") == "medication"]
        )
        obligation_map = await self._fetch_obligation_display_map(
            [str(row["target_id"]) for row in schedules if row.get("target_type") == "obligation"]
        )

        candidate_rows: list[dict[str, Any]] = []
        for schedule in schedules:
            candidate_rows.extend(
                self._build_schedule_notification_candidates(
                    schedule=schedule,
                    medication_map=medication_map,
                    obligation_map=obligation_map,
                    window_start=window_start,
                    window_end=window_end,
                )
            )

        existing_keys = await self._fetch_existing_notification_keys(
            [row["dedupe_key"] for row in candidate_rows]
        )
        pending_rows = [row for row in candidate_rows if row["dedupe_key"] not in existing_keys]

        if pending_rows and not dry_run:
            await self._insert_notifications(pending_rows)

        summary = {
            "medication_candidates": 0,
            "medication_created": 0,
            "medication_existing": 0,
            "obligation_candidates": 0,
            "obligation_created": 0,
            "obligation_existing": 0,
        }
        for row in candidate_rows:
            summary[f"{row['metadata']['target_type']}_candidates"] += 1
        for row in pending_rows:
            summary[f"{row['metadata']['target_type']}_created"] += 1
        for row in candidate_rows:
            if row["dedupe_key"] in existing_keys:
                summary[f"{row['metadata']['target_type']}_existing"] += 1
        return summary

    async def _ensure_job_not_running(self, job_name: str) -> None:
        cutoff = self._iso(self._utc_now() - timedelta(hours=self.RUNNING_STALE_AFTER_HOURS))
        response = await execute_async(
            self,
            lambda db: (
                db.table("cron_job_runs")
                .select("id")
                .eq("job_name", job_name)
                .eq("status", "running")
                .gte("started_at", cutoff)
                .limit(1)
            ),
            operation=f"check running cron job {job_name}",
            retry_transient=True,
        )
        if response.data:
            raise ValidationError(f"Cron job '{job_name}' is already running")

    async def _start_run(self, job_name: str, *, metadata: dict[str, Any]) -> dict[str, Any]:
        response = await execute_async(
            self,
            lambda db: db.table("cron_job_runs").insert(
                {
                    "job_name": job_name,
                    "status": "running",
                    "triggered_by": "scheduler",
                    "metadata": metadata,
                }
            ),
            operation=f"start cron job {job_name}",
            retry_transient=True,
        )
        row = (response.data or [None])[0]
        if row is None:
            raise ValidationError(f"Failed to create run record for cron job '{job_name}'")
        return cast(dict[str, Any], row)

    async def _finish_run(
        self,
        run_id: str,
        *,
        status: str,
        summary: dict[str, Any],
        error: str | None = None,
    ) -> dict[str, Any]:
        response = await execute_async(
            self,
            lambda db: (
                db.table("cron_job_runs")
                .update(
                    {
                        "status": status,
                        "summary": summary,
                        "error": error,
                        "finished_at": self._iso(self._utc_now()),
                    }
                )
                .eq("id", run_id)
            ),
            operation=f"finish cron job {run_id}",
            retry_transient=True,
        )
        row = (response.data or [None])[0]
        if row is None:
            raise ValidationError(f"Failed to finalize cron job run '{run_id}'")
        return cast(dict[str, Any], row)

    async def _fetch_upcoming_appointments(
        self, *, window_start: datetime, window_end: datetime
    ) -> list[dict[str, Any]]:
        response = await execute_async(
            self,
            lambda db: (
                db.table("appointments")
                .select(
                    "id, patient_id, scheduled_at, clinician_name, location, appointment_type, reason"
                )
                .eq("status", "scheduled")
                .gte("scheduled_at", self._iso(window_start))
                .lt("scheduled_at", self._iso(window_end))
            ),
            operation="fetch upcoming appointments for reminders",
            retry_transient=True,
        )
        return list(response.data or [])

    async def _fetch_enabled_reminder_schedules(self) -> list[dict[str, Any]]:
        response = await execute_async(
            self,
            lambda db: (
                db.table("reminder_schedules")
                .select(
                    "id, patient_id, target_type, target_id, timezone, times_of_day, days_of_week, is_enabled"
                )
                .eq("is_enabled", True)
            ),
            operation="fetch enabled reminder schedules",
            retry_transient=True,
        )
        return list(response.data or [])

    async def _fetch_medication_display_map(
        self, target_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        if not target_ids:
            return {}
        response = await execute_async(
            self,
            lambda db: db.table("medications")
            .select("id, name, dosage, instructions")
            .in_("id", target_ids),
            operation="fetch medication reminder display data",
            retry_transient=True,
        )
        return {str(row["id"]): row for row in list(response.data or [])}

    async def _fetch_obligation_display_map(
        self, target_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        if not target_ids:
            return {}
        response = await execute_async(
            self,
            lambda db: db.table("obligations")
            .select("id, description, notes")
            .in_("id", target_ids),
            operation="fetch obligation reminder display data",
            retry_transient=True,
        )
        return {str(row["id"]): row for row in list(response.data or [])}

    async def _fetch_existing_notification_keys(self, dedupe_keys: list[str]) -> set[str]:
        if not dedupe_keys:
            return set()

        response = await execute_async(
            self,
            lambda db: (
                db.table("notifications").select("dedupe_key").in_("dedupe_key", dedupe_keys)
            ),
            operation="fetch existing reminder dedupe keys",
            retry_transient=True,
        )
        return {str(row["dedupe_key"]) for row in (response.data or []) if row.get("dedupe_key")}

    async def _insert_notifications(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return

        await execute_async(
            self,
            lambda db: db.table("notifications").insert(rows),
            operation="insert cron notifications",
            retry_transient=True,
        )

    def _build_schedule_notification_candidates(
        self,
        *,
        schedule: dict[str, Any],
        medication_map: dict[str, dict[str, Any]],
        obligation_map: dict[str, dict[str, Any]],
        window_start: datetime,
        window_end: datetime,
    ) -> list[dict[str, Any]]:
        timezone_name = str(schedule.get("timezone") or "UTC")
        tz = ZoneInfo(timezone_name)
        local_dates = {
            window_start.astimezone(tz).date(),
            window_end.astimezone(tz).date(),
        }
        candidates: list[dict[str, Any]] = []
        for local_date in sorted(local_dates):
            for scheduled_at, local_time in occurrence_datetimes_for_day(schedule, local_date):
                scheduled_dt = self._parse_timestamp(scheduled_at)
                if not (window_start <= scheduled_dt < window_end):
                    continue
                candidates.append(
                    self._build_scheduled_item_notification(
                        schedule=schedule,
                        medication_map=medication_map,
                        obligation_map=obligation_map,
                        scheduled_at=scheduled_at,
                        local_time=local_time,
                    )
                )
        return candidates

    def _build_scheduled_item_notification(
        self,
        *,
        schedule: dict[str, Any],
        medication_map: dict[str, dict[str, Any]],
        obligation_map: dict[str, dict[str, Any]],
        scheduled_at: str,
        local_time: str,
    ) -> dict[str, Any]:
        target_type = str(schedule["target_type"])
        target_id = str(schedule["target_id"])
        patient_id = str(schedule["patient_id"])
        if target_type == "medication":
            medication = medication_map.get(target_id, {})
            title = "Medication reminder"
            body = (
                f"Time for {medication.get('name', 'your medication')} "
                f"({medication.get('dosage', '').strip()}). Scheduled for {local_time[:5]}."
            ).replace(" ().", ".")
            action_url = "/today"
            display_name = medication.get("name", "Medication")
        else:
            obligation = obligation_map.get(target_id, {})
            title = "Care plan reminder"
            body = (
                f"Scheduled task: {obligation.get('description', 'care plan task')} at "
                f"{local_time[:5]}."
            )
            action_url = "/today"
            display_name = obligation.get("description", "Obligation")

        return {
            "patient_id": patient_id,
            "notification_type": (
                "med_reminder" if target_type == "medication" else "obligation_reminder"
            ),
            "title": title,
            "body": body,
            "action_url": action_url,
            "dedupe_key": f"{target_type}:{target_id}:{scheduled_at}",
            "metadata": {
                "target_type": target_type,
                "target_id": target_id,
                "scheduled_at": scheduled_at,
                "display_name": display_name,
            },
        }

    async def _resolve_adr_scan_since(self, job_name: str, lookback_hours: int | None) -> datetime:
        if lookback_hours is not None:
            return self._utc_now() - timedelta(hours=lookback_hours)

        response = await execute_async(
            self,
            lambda db: (
                db.table("cron_job_runs")
                .select("finished_at, started_at")
                .eq("job_name", job_name)
                .eq("status", "success")
                .order("started_at", desc=True)
                .limit(1)
            ),
            operation=f"fetch last successful cron job {job_name}",
            retry_transient=True,
        )
        last_run = (response.data or [None])[0]
        if last_run is None:
            return self._utc_now() - timedelta(hours=24)

        return self._parse_timestamp(str(last_run.get("finished_at") or last_run["started_at"]))

    async def _fetch_symptom_reports_for_adr_scan(
        self, *, since: datetime, limit: int
    ) -> list[dict[str, Any]]:
        response = await execute_async(
            self,
            lambda db: (
                db.table("symptom_reports")
                .select("id, patient_id, severity, related_medication_id, created_at")
                .eq("flagged_for_adr", False)
                .gte("created_at", self._iso(since))
                .order("created_at")
                .limit(limit)
            ),
            operation="fetch symptom reports for ADR scan",
            retry_transient=True,
        )
        return list(response.data or [])

    async def _fetch_active_medication_map(
        self, patient_ids: list[str]
    ) -> dict[str, list[dict[str, Any]]]:
        if not patient_ids:
            return {}

        response = await execute_async(
            self,
            lambda db: (
                db.table("medications")
                .select("id, patient_id")
                .eq("is_active", True)
                .in_("patient_id", patient_ids)
            ),
            operation="fetch active medications for ADR scan",
            retry_transient=True,
        )
        rows = list(response.data or [])
        by_patient: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            by_patient.setdefault(str(row["patient_id"]), []).append(row)
        return by_patient

    async def _flag_symptom_reports_for_adr(self, symptom_ids: list[str]) -> None:
        await execute_async(
            self,
            lambda db: (
                db.table("symptom_reports").update({"flagged_for_adr": True}).in_("id", symptom_ids)
            ),
            operation="flag symptom reports for ADR review",
            retry_transient=True,
        )

    def _build_appointment_notification(
        self,
        *,
        appointment: dict[str, Any],
        reminder_kind: str,
        hours_before: int,
        window_start: datetime,
        window_end: datetime,
    ) -> dict[str, Any]:
        appointment_id = str(appointment["id"])
        patient_id = str(appointment["patient_id"])
        scheduled_at = str(appointment["scheduled_at"])
        dedupe_key = f"appointment:{appointment_id}:{reminder_kind}"
        location = appointment.get("location") or "your care team"
        clinician_name = appointment.get("clinician_name") or "your clinician"

        if reminder_kind == "24h":
            body = (
                f"You have a {appointment.get('appointment_type', 'follow-up')} appointment "
                f"with {clinician_name} at {scheduled_at}. Location: {location}."
            )
        else:
            body = (
                f"Your appointment with {clinician_name} starts at {scheduled_at}. "
                f"Location: {location}."
            )

        return {
            "patient_id": patient_id,
            "notification_type": "appointment",
            "title": next(
                title
                for kind, _hours, title in self.APPOINTMENT_REMINDER_CONFIG
                if kind == reminder_kind
            ),
            "body": body,
            "action_url": f"/appointments?appointmentId={appointment_id}",
            "dedupe_key": dedupe_key,
            "metadata": {
                "appointment_id": appointment_id,
                "scheduled_at": scheduled_at,
                "reminder_kind": reminder_kind,
                "hours_before": hours_before,
                "window_start": self._iso(window_start),
                "window_end": self._iso(window_end),
            },
        }

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.astimezone(UTC).isoformat()

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
