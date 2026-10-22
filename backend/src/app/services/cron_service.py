"""Internal cron jobs: reminder dispatch and the weekly reference refresh."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from supabase import Client

from app.core.exceptions import ValidationError
from app.core.job_logging import JobRunLog
from app.db.supabase_execute import execute_async
from app.services.activity_grouping import norm_text
from app.services.email_service import EmailDeliveryService
from app.services.feed_service import FeedService
from app.services.health_knowledge_service import HealthKnowledgeService
from app.services.reminder_schedule_service import (
    occurrence_datetimes_for_day,
    schedule_matches_frequency,
)

logger = logging.getLogger(__name__)

# Fills the run's summary in place; returns a short, PHI-free reason when the run as a
# whole must count as failed although it completed (for example, subjects that errored).
JobWork = Callable[[dict[str, Any]], Awaitable[str | None]]


class CronJobAlreadyRunningError(ValidationError):
    """Another run of the same job started recently and has not finished."""

    def __init__(self, job_name: str) -> None:
        super().__init__(f"Cron job '{job_name}' is already running")


class CronService:
    """Background job orchestration triggered by Cloud Scheduler."""

    APPOINTMENT_REMINDER_CONFIG = (
        ("24h", 24, "Upcoming appointment tomorrow"),
        ("1h", 1, "Upcoming appointment soon"),
    )
    RUNNING_STALE_AFTER_HOURS = 6
    # Booked visits: an accepted offer is ``confirmed``; older rows are ``scheduled``. The
    # notification centre treats both as booked (migrations 051 and 054).
    BOOKED_APPOINTMENT_STATUSES = ("confirmed", "scheduled")
    # Each dispatch starts where the last successful one ended, so a late or retried
    # Scheduler run leaves no gap. After a longer pause the next run starts at "now":
    # reminders for medicines that were due an hour ago are no longer useful.
    MAX_REMINDER_CATCH_UP = timedelta(minutes=60)
    # Reading the combined-entry grouping: a few quick attempts inside a small total budget
    # (the dispatcher must finish well inside its Scheduler interval).
    GROUPING_RETRY_DELAYS = (0.2, 0.5)
    GROUPING_RETRY_BUDGET_SECONDS = 3.0
    # With grouping unavailable, an occurrence due at least this far beyond the next run's
    # start may wait for that run; anything sooner is sent now, one per identity.
    MAX_GROUPING_DEFER_LATENESS = timedelta(minutes=5)

    def __init__(self, db: Client) -> None:
        self.db = db

    async def dispatch_reminders(
        self, *, dry_run: bool = False, window_minutes: int = 15
    ) -> dict[str, Any]:
        """Dispatch due appointment, medication and care-plan reminder notifications.

        Windows are contiguous: this run covers ``[previous window end, now + window)``,
        so nothing due between two Scheduler runs is skipped when a run is late. Dedupe
        keys make any overlap harmless.
        """
        job_name = "reminders_dispatch"
        summary: dict[str, Any] = {
            "window_start": None,
            "window_end": None,
            "window_mode": None,
            "catch_up_minutes": 0,
            "appointment_24h_candidates": 0,
            "appointment_24h_created": 0,
            "appointment_24h_existing": 0,
            "appointment_1h_candidates": 0,
            "appointment_1h_created": 0,
            "appointment_1h_existing": 0,
            **self._empty_schedule_summary(),
        }

        async def work(summary: dict[str, Any]) -> None:
            now = self._utc_now()
            window_start, window_end, mode = self._reminder_window(
                now=now,
                window_minutes=window_minutes,
                previous_end=await self._previous_reminder_window_end(job_name),
            )
            summary["window_start"] = self._iso(window_start)
            summary["window_end"] = self._iso(window_end)
            summary["window_mode"] = mode
            summary["catch_up_minutes"] = round(
                max(0.0, (now - window_start).total_seconds()) / 60, 1
            )
            for reminder_kind, hours_before, _title in self.APPOINTMENT_REMINDER_CONFIG:
                result = await self._dispatch_appointment_reminders(
                    window_start=window_start,
                    window_end=window_end,
                    reminder_kind=reminder_kind,
                    hours_before=hours_before,
                    dry_run=dry_run,
                )
                summary[f"appointment_{reminder_kind}_candidates"] = result["candidates"]
                summary[f"appointment_{reminder_kind}_created"] = result["created"]
                summary[f"appointment_{reminder_kind}_existing"] = result["existing"]

            summary.update(
                await self._dispatch_schedule_reminders(
                    window_start=window_start,
                    window_end=window_end,
                    dry_run=dry_run,
                )
            )

        return await self._run_job(
            job_name,
            dry_run=dry_run,
            metadata={"dry_run": dry_run, "window_minutes": window_minutes},
            summary=summary,
            work=work,
        )

    @classmethod
    def _reminder_window(
        cls, *, now: datetime, window_minutes: int, previous_end: datetime | None
    ) -> tuple[datetime, datetime, str]:
        """The ``[start, end)`` this run covers and why it starts where it does."""
        end = now + timedelta(minutes=window_minutes)
        if previous_end is None:
            return now, end, "first_run"
        if previous_end < now - cls.MAX_REMINDER_CATCH_UP:
            return now, end, "catch_up_capped"
        # An early or repeated run never moves the window backwards.
        return previous_end, max(end, previous_end), "contiguous"

    async def _previous_reminder_window_end(self, job_name: str) -> datetime | None:
        """Where the last successful real (not dry-run) dispatch window ended, if recorded."""
        response = await execute_async(
            self,
            lambda db: (
                db.table("cron_job_runs")
                .select("summary, metadata")
                .eq("job_name", job_name)
                .eq("status", "success")
                .order("started_at", desc=True)
                .limit(10)
            ),
            operation=f"fetch last {job_name} window",
            retry_transient=True,
        )
        for row in cast(list[dict[str, Any]], response.data or []):
            if (row.get("metadata") or {}).get("dry_run"):
                continue
            recorded = row.get("summary") or {}
            window_end = recorded.get("window_end")
            if not window_end:
                return None
            end = self._parse_timestamp(str(window_end))
            # Occurrences deferred because grouping was unavailable are picked up again by
            # starting the next window at the earliest of them (bounded by the catch-up cap).
            resume = recorded.get("resume_from")
            return min(end, self._parse_timestamp(str(resume))) if resume else end
        return None

    async def run_health_knowledge_refresh(self, *, limit: int = 150) -> dict[str, Any]:
        """Re-check public medication and condition references; record the run.

        A run in which any subject raised counts as failed, so the Cloud Run execution
        fails too; subjects whose source was unavailable do not (the cache keeps serving).
        """

        async def work(summary: dict[str, Any]) -> str | None:
            summary.update(await HealthKnowledgeService(self.db).refresh_due(limit=limit))
            failed = int(summary.get("subjects_failed") or 0)
            return f"{failed} reference subjects failed" if failed else None

        return await self._run_job(
            "health_knowledge_refresh",
            dry_run=False,
            metadata={"limit": limit},
            summary={},
            work=work,
        )

    async def dispatch_emails(self, *, dry_run: bool = False) -> dict[str, Any]:
        """Send due verified opt-in email and reconcile provider status; record the run.

        A dry run only counts due rows and sends awaiting a status check. Rows that
        raised are retried by a later run, so the run counts as failed when any did.
        """

        async def work(summary: dict[str, Any]) -> str | None:
            service = EmailDeliveryService(self.db)
            if dry_run:
                summary.update(await service.pending())
                return None
            summary.update(await service.dispatch())
            errors = int(summary.get("errors") or 0)
            return f"{errors} email rows deferred" if errors else None

        return await self._run_job(
            "email_dispatch",
            dry_run=dry_run,
            metadata={"dry_run": dry_run},
            summary={},
            work=work,
        )

    async def dispatch_emails_isolated(self) -> None:
        """Run email dispatch after reminders without letting it fail the reminder run.

        The email run has its own run record and log lines; here any failure is reduced
        to a type name so a provider or network error cannot turn a successful reminder
        run into an HTTP error.
        """
        try:
            await self.dispatch_emails()
        except Exception as exc:  # noqa: BLE001 - isolation is the purpose
            logger.warning(
                "Email dispatch after reminders did not complete (%s)", type(exc).__name__
            )

    async def _run_job(
        self,
        job_name: str,
        *,
        dry_run: bool,
        metadata: dict[str, Any],
        summary: dict[str, Any],
        work: JobWork,
    ) -> dict[str, Any]:
        """Record one run in ``cron_job_runs`` and log its start and its outcome.

        The log line and the run record carry the same summary. A run already in progress
        is logged as skipped; any exception is logged as a failure with its type and
        category only, recorded on the run, and re-raised.
        """
        log = JobRunLog(job_name, dry_run=dry_run)
        try:
            await self._ensure_job_not_running(job_name)
            run = await self._start_run(job_name, metadata=metadata)
        except CronJobAlreadyRunningError:
            log.finished("skipped", summary, reason="already_running")
            raise
        except Exception as exc:
            log.finished("failed", summary, error=exc, reason="run_not_recorded")
            raise

        run_id = str(run["id"])
        log.started(run_id=run_id, parameters=metadata)
        try:
            failure = await work(summary)
            status = "failed" if failure else "success"
            finished = await self._finish_run(run_id, status=status, summary=summary, error=failure)
        except Exception as exc:
            try:
                await self._finish_run(run_id, status="failed", summary=summary, error=str(exc))
            except Exception:  # noqa: BLE001 - the original failure is the one to report
                logger.warning("Could not record the failed %s run", job_name)
            log.finished("failed", summary, error=exc)
            raise

        if failure:
            log.finished("failed", summary, reason=failure)
        else:
            log.finished("success", summary)
        return {
            "run_id": run_id,
            "job_name": job_name,
            "status": status,
            "dry_run": dry_run,
            "started_at": run["started_at"],
            "finished_at": finished["finished_at"],
            "summary": summary,
        }

    async def _dispatch_appointment_reminders(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        reminder_kind: str,
        hours_before: int,
        dry_run: bool,
    ) -> dict[str, int]:
        visit_window_start = window_start + timedelta(hours=hours_before)
        visit_window_end = window_end + timedelta(hours=hours_before)
        appointments = await self._fetch_upcoming_appointments(
            window_start=visit_window_start,
            window_end=visit_window_end,
        )

        if not appointments:
            return {"candidates": 0, "created": 0, "existing": 0}

        candidate_rows = [
            self._build_appointment_notification(
                appointment=appointment,
                reminder_kind=reminder_kind,
                hours_before=hours_before,
                window_start=visit_window_start,
                window_end=visit_window_end,
            )
            for appointment in appointments
        ]
        existing_keys = await self._fetch_existing_notification_keys(
            [row["dedupe_key"] for row in candidate_rows]
        )
        pending_rows = [row for row in candidate_rows if row["dedupe_key"] not in existing_keys]

        conflicts: set[str] = set()
        if pending_rows and not dry_run:
            conflicts = await self._insert_notifications(pending_rows)

        created = len(pending_rows) - len(conflicts)
        return {
            "candidates": len(candidate_rows),
            "created": created,
            "existing": len(candidate_rows) - created,
        }

    @staticmethod
    def _empty_schedule_summary() -> dict[str, Any]:
        return {
            "medication_candidates": 0,
            "medication_created": 0,
            "medication_existing": 0,
            "obligation_candidates": 0,
            "obligation_created": 0,
            "obligation_existing": 0,
            "skipped_inactive_target": 0,
            "skipped_frequency_mismatch": 0,
        }

    async def _dispatch_schedule_reminders(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        dry_run: bool,
    ) -> dict[str, Any]:
        summary = self._empty_schedule_summary()
        if self.db is None:
            return summary

        schedules = await self._fetch_enabled_reminder_schedules()
        if not schedules:
            return summary
        schedules, ungrouped_patients = await self._collapse_combined_schedules(
            schedules, window_end, summary
        )

        medication_map = await self._fetch_medication_display_map(
            [str(row["target_id"]) for row in schedules if row.get("target_type") == "medication"]
        )
        obligation_map = await self._fetch_obligation_display_map(
            [str(row["target_id"]) for row in schedules if row.get("target_type") == "obligation"]
        )

        candidate_rows: list[dict[str, Any]] = []
        for schedule in schedules:
            target_map = (
                medication_map if schedule.get("target_type") == "medication" else obligation_map
            )
            target = target_map.get(str(schedule.get("target_id")))
            if not target:
                # The medicine or care-plan item was stopped or removed; the schedule is
                # still enabled but must not remind anyone.
                summary["skipped_inactive_target"] += 1
                continue
            if not schedule_matches_frequency(schedule, str(target.get("frequency") or "")):
                summary["skipped_frequency_mismatch"] += 1
                continue
            candidate_rows.extend(
                self._build_schedule_notification_candidates(
                    schedule=schedule,
                    medication_map=medication_map,
                    obligation_map=obligation_map,
                    window_start=window_start,
                    window_end=window_end,
                )
            )

        if ungrouped_patients:
            candidate_rows = self._safe_ungrouped_candidates(
                candidate_rows,
                ungrouped_patients,
                medication_map=medication_map,
                obligation_map=obligation_map,
                window_end=window_end,
                summary=summary,
            )

        existing_keys = await self._fetch_existing_notification_keys(
            [row["dedupe_key"] for row in candidate_rows]
        )
        pending_rows = [row for row in candidate_rows if row["dedupe_key"] not in existing_keys]

        conflicts: set[str] = set()
        if pending_rows and not dry_run:
            conflicts = await self._insert_notifications(pending_rows)

        for row in candidate_rows:
            target_type = row["metadata"]["target_type"]
            summary[f"{target_type}_candidates"] += 1
            if row["dedupe_key"] in existing_keys or row["dedupe_key"] in conflicts:
                summary[f"{target_type}_existing"] += 1
            else:
                summary[f"{target_type}_created"] += 1
        return summary

    async def _read_combined_groups(
        self, patient_id: str, local_date: Any, deadline: float, summary: dict[str, Any]
    ) -> list[list[tuple[str, str]]] | None:
        """The patient's combined entries, retried with bounded backoff; None if unreadable.

        At most ``len(GROUPING_RETRY_DELAYS) + 1`` attempts, and no attempt starts after the
        run-wide ``deadline``, so a degraded database cannot stall the dispatcher.
        """
        assert self.db is not None
        for attempt in range(len(self.GROUPING_RETRY_DELAYS) + 1):
            try:
                return await FeedService(self.db).combined_groups(UUID(patient_id), local_date)
            except Exception:  # noqa: BLE001 - any read failure falls back safely
                if attempt >= len(self.GROUPING_RETRY_DELAYS):
                    break
                delay = self.GROUPING_RETRY_DELAYS[attempt]
                if time.monotonic() + delay >= deadline:
                    break
                summary["grouping_retries"] = summary.get("grouping_retries", 0) + 1
                await asyncio.sleep(delay)
        return None

    async def _collapse_combined_schedules(
        self, schedules: list[dict[str, Any]], window_end: datetime, summary: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], set[str]]:
        """One reminder per occurrence for a combined Today entry (PLAN-002 decision 5).

        Identical activities of several plans are one entry in Today, with one reminder. The
        entry's own schedule wins; if it has none, the first member that does is used. The
        notification is keyed on the entry's id, so the key is the same on every run and for
        every retry, and the existing unique key makes concurrent dispatcher runs safe.

        The grouping read is retried with bounded backoff. A patient whose grouping is still
        unreadable is returned in the second value: their reminders are never sent ungrouped
        (see ``_safe_ungrouped_candidates``). Only a patient with two or more schedules can
        have a combined entry, so only they are affected.
        """
        by_patient: dict[str, list[dict[str, Any]]] = {}
        for schedule in schedules:
            by_patient.setdefault(str(schedule["patient_id"]), []).append(schedule)
        dropped: set[str] = set()
        primary_of: dict[str, str] = {}
        ungrouped: set[str] = set()
        deadline = time.monotonic() + self.GROUPING_RETRY_BUDGET_SECONDS
        for patient_id, owned in by_patient.items():
            if len(owned) < 2 or self.db is None:
                continue
            local_date = window_end.astimezone(
                ZoneInfo(str(owned[0].get("timezone") or "UTC"))
            ).date()
            groups = await self._read_combined_groups(patient_id, local_date, deadline, summary)
            if groups is None:
                # Counted, never logged with an identifier.
                logger.warning("Reminder grouping unavailable after retries for one patient")
                summary["grouping_unavailable"] = summary.get("grouping_unavailable", 0) + 1
                ungrouped.add(patient_id)
                continue
            for group in groups:
                primary = group[0][1]
                scheduled = [
                    schedule
                    for kind, member_id in group
                    for schedule in owned
                    if str(schedule["target_id"]) == member_id
                    and schedule.get("target_type") == kind
                ]
                if not scheduled:
                    continue
                keep = next(
                    (row for row in scheduled if str(row["target_id"]) == primary), scheduled[0]
                )
                dropped.update(str(row["id"]) for row in scheduled if row is not keep)
                primary_of[str(keep["id"])] = primary
        if dropped:
            summary["skipped_combined_duplicate"] = len(dropped)
        kept = [row for row in schedules if str(row["id"]) not in dropped]
        for row in kept:
            if str(row["id"]) in primary_of:
                row["group_primary_id"] = primary_of[str(row["id"])]
        return kept, ungrouped

    @staticmethod
    def _activity_identity(target_type: str, target: dict[str, Any]) -> tuple[str, ...]:
        """What makes two reminders the same activity when grouping is unavailable.

        Deliberately narrower than the feed's grouping (it cannot see plan items): kind plus
        the normalised name or description, dose, frequency and instructions. Two items with
        the same identity are one reminder; items that differ in any of these keep their own.
        """
        if target_type == "medication":
            return (
                "medication",
                norm_text(target.get("name")),
                norm_text(target.get("dosage")),
                norm_text(target.get("frequency")),
                norm_text(target.get("instructions")),
            )
        return (
            "obligation",
            norm_text(target.get("description")),
            norm_text(target.get("frequency")),
            norm_text(target.get("notes")),
        )

    def _safe_ungrouped_candidates(
        self,
        candidate_rows: list[dict[str, Any]],
        ungrouped_patients: set[str],
        *,
        medication_map: dict[str, dict[str, Any]],
        obligation_map: dict[str, dict[str, Any]],
        window_end: datetime,
        summary: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Reminders for patients whose combined grouping could not be read.

        Never zero for a due dose, never two for one entry:

        * An occurrence due late enough that the next run (about ``window_end``) still
          delivers it within ``MAX_GROUPING_DEFER_LATENESS`` waits for that run, which reads
          the grouping again. The next window is told where to resume (``resume_from``).
        * Anything sooner is sent now, once per (activity identity, scheduled time): the
          lowest target id of identical activities represents them, so the key is stable.
        """
        keep_after = window_end - self.MAX_GROUPING_DEFER_LATENESS
        result: list[dict[str, Any]] = []
        chosen: dict[tuple[str, tuple[str, ...], str], dict[str, Any]] = {}
        deferred_from: datetime | None = None
        deferred = 0
        deduped = 0
        for row in sorted(candidate_rows, key=lambda r: str(r["metadata"]["target_id"])):
            if str(row["patient_id"]) not in ungrouped_patients:
                result.append(row)
                continue
            meta = row["metadata"]
            due = self._parse_timestamp(str(meta["scheduled_at"]))
            if due >= keep_after:
                deferred += 1
                deferred_from = due if deferred_from is None else min(deferred_from, due)
                continue
            target_map = medication_map if meta["target_type"] == "medication" else obligation_map
            identity = self._activity_identity(
                str(meta["target_type"]), target_map.get(str(meta["target_id"])) or {}
            )
            key = (str(row["patient_id"]), identity, str(meta["scheduled_at"]))
            if key in chosen:
                deduped += 1
                continue
            chosen[key] = row
            result.append(row)
        if deferred:
            summary["reminders_deferred"] = deferred
            if deferred_from is not None:
                summary["resume_from"] = self._iso(deferred_from)
            logger.warning("Deferred %d reminders to the next run (grouping unavailable)", deferred)
        if deduped:
            summary["reminders_deduped_by_identity"] = deduped
        return result

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
            raise CronJobAlreadyRunningError(job_name)

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
                    "id, patient_id, scheduled_at, clinician_name, location, appointment_type, "
                    "reason, clinic_id, clinics(display_name)"
                )
                .in_("status", list(self.BOOKED_APPOINTMENT_STATUSES))
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
            .select("id, name, dosage, instructions, frequency")
            .in_("id", target_ids)
            .eq("is_active", True),
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
            .select("id, description, notes, frequency")
            .in_("id", target_ids)
            .eq("is_active", True),
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

    async def _insert_notifications(self, rows: list[dict[str, Any]]) -> set[str]:
        """Insert reminder rows; return the dedupe keys another writer already inserted.

        ``notifications.dedupe_key`` has a partial unique index, which PostgREST's
        ``on_conflict`` cannot target. One conflicting row (a concurrent run, or a batch
        that committed before its response was lost) fails the whole batch, so the batch
        is never retried blindly: on a unique violation each row is inserted on its own
        and a conflict is counted as already sent.
        """
        if not rows:
            return set()

        try:
            await execute_async(
                self,
                lambda db: db.table("notifications").insert(rows),
                operation="insert cron notifications",
                retry_transient=False,
            )
            return set()
        except Exception as exc:
            if not self._is_unique_violation(exc):
                raise

        def insert_one(row: dict[str, Any]) -> Callable[[Client], Any]:
            return lambda db: db.table("notifications").insert(row)

        conflicts: set[str] = set()
        for row in rows:
            try:
                await execute_async(
                    self,
                    insert_one(row),
                    operation="insert cron notification",
                    retry_transient=True,
                )
            except Exception as exc:
                if not self._is_unique_violation(exc):
                    raise
                conflicts.add(str(row["dedupe_key"]))
        return conflicts

    @staticmethod
    def _is_unique_violation(exc: BaseException) -> bool:
        if str(getattr(exc, "code", "") or "").strip() == "23505":
            return True
        return "duplicate key" in str(exc).lower()

    def _build_schedule_notification_candidates(
        self,
        *,
        schedule: dict[str, Any],
        medication_map: dict[str, dict[str, Any]],
        obligation_map: dict[str, dict[str, Any]],
        window_start: datetime,
        window_end: datetime,
    ) -> list[dict[str, Any]]:
        target_map = (
            medication_map if schedule.get("target_type") == "medication" else obligation_map
        )
        target = target_map.get(str(schedule.get("target_id"))) or {}
        if not schedule_matches_frequency(schedule, str(target.get("frequency") or "")):
            return []
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
            # A combined entry is keyed on the entry's own id, so every member's schedule and
            # every retry produce the same key.
            "dedupe_key": f"{target_type}:{schedule.get('group_primary_id') or target_id}:{scheduled_at}",
            "metadata": {
                "target_type": target_type,
                "target_id": str(schedule.get("group_primary_id") or target_id),
                "scheduled_at": scheduled_at,
                "display_name": display_name,
            },
        }

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
        # The visit time is part of the key, so a rescheduled visit is reminded again for
        # its new time; one normalised form keeps the key stable across runs.
        visit_at = self._iso(self._parse_timestamp(scheduled_at))
        dedupe_key = f"appointment:{appointment_id}:{reminder_kind}:{visit_at}"
        location = appointment.get("location") or "your care team"
        clinician_name = appointment.get("clinician_name") or "your clinician"
        # The appointment's own clinic, never the clinician's default one (CLN-003 slice F).
        clinic_row = appointment.get("clinics")
        clinic_name = (
            " ".join(str(clinic_row.get("display_name") or "").split())
            if isinstance(clinic_row, dict)
            else ""
        )
        clinic_text = f" Clinic: {clinic_name}." if clinic_name else ""

        if reminder_kind == "24h":
            body = (
                f"You have a {appointment.get('appointment_type', 'follow-up')} appointment "
                f"with {clinician_name} at {scheduled_at}.{clinic_text} Location: {location}."
            )
        else:
            body = (
                f"Your appointment with {clinician_name} starts at {scheduled_at}."
                f"{clinic_text} Location: {location}."
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
            "action_url": f"/visits?appointmentId={appointment_id}",
            "dedupe_key": dedupe_key,
            "metadata": {
                "appointment_id": appointment_id,
                "clinic_id": appointment.get("clinic_id"),
                "clinic_name": clinic_name or None,
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
