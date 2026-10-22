"""Deterministic handoff-summary sections (CON-001).

Every line is read from a record the author may see and carries a source link. Nothing here
calls a model: the sections are the same for the same records. A section whose read fails is
reported as unavailable, never as empty. Visibility reuses the care-team rules the rest of the
clinician surface follows: the shared core comes from the database's shared summary function
(other teams' sensitive conditions become a marker), the plan, visits and ADR items are the
author's own team's, and the timeline is the bounded #208 timeline (private threads are left
out of a document that is meant to leave the record).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.core.exceptions import AuthorizationError
from app.models.handoff import HandoffItem, HandoffSection, HandoffSource
from app.services.care_plan_activity_scope import ActivityScope
from app.services.care_team_access import PatientAccess
from app.services.patient_timeline_service import PatientTimelineService
from app.services.shared_clinical_core_service import SharedClinicalCoreService

logger = logging.getLogger(__name__)

RECENT_DAYS = 30
SYMPTOM_LIMIT = 10
ADHERENCE_LIMIT = 500
VISIT_LIMIT = 10
TIMELINE_LIMIT = 8
ADR_LIMIT = 20
PLAN_ITEM_LIMIT = 40
OPEN_VISIT_STATUSES = ("scheduled", "confirmed", "proposed")
# A shared timeline excerpt leaves out private conversations: the document may be exported.
TIMELINE_EXCLUDED_DOMAINS = frozenset({"message"})


def _day(value: Any) -> str:
    return str(value)[:10] if value else "date not recorded"


def _clip(value: Any, limit: int = 240) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class HandoffSummaryBuilder:
    def __init__(
        self,
        db: Client,
        authorize: Callable[[UUID, UUID], Awaitable[None]],
    ) -> None:
        self.db = db
        self.authorize = authorize

    async def build(
        self, clinician_id: UUID, patient_id: UUID, care_team_id: str, access: PatientAccess
    ) -> list[HandoffSection]:
        pid = str(patient_id)
        sections = await asyncio.gather(
            self._guard("patient", "Patient", self._patient, pid),
            self._guard("shared_core", "Shared record", self._shared_core, clinician_id, pid),
            self._guard("team_plan", "Your care team's plan", self._team_plan, pid, care_team_id),
            self._guard(
                "team_activity", "Recent activity and adherence", self._activity, pid, access
            ),
            self._guard("symptoms", "Recent confirmed symptoms", self._symptoms, pid),
            self._guard("open_adr", "Open medication-safety reviews", self._adr, pid, access),
            self._guard("upcoming_visits", "Upcoming visits", self._visits, pid, access),
            self._timeline_section(clinician_id, patient_id),
        )
        return list(sections)

    async def _guard(
        self, key: str, title: str, reader: Callable[..., HandoffSection], *args: Any
    ) -> HandoffSection:
        try:
            return await asyncio.to_thread(reader, *args)
        except AuthorizationError:
            raise
        except Exception as error:
            # Type only: a record's content never goes to a log.
            logger.warning("handoff section %s unavailable: %s", key, type(error).__name__)
            return HandoffSection(
                key=key,
                title=title,
                status="unavailable",
                note="This section could not be read. Rebuild the summary before approving it.",
            )

    @staticmethod
    def _section(key: str, title: str, items: list[HandoffItem], empty: str) -> HandoffSection:
        return HandoffSection(
            key=key,
            title=title,
            status="available" if items else "empty",
            note=None if items else empty,
            items=items,
        )

    def _rows(self, query: Any) -> list[dict[str, Any]]:
        data = query.execute().data
        if not isinstance(data, list):
            raise ValueError("Expected a row list")
        return cast(list[dict[str, Any]], data)

    # ── sections ────────────────────────────────────────────────────────────────────────

    def _patient(self, pid: str) -> HandoffSection:
        rows = self._rows(
            self.db.table("patients")
            .select("id,first_name,last_name,date_of_birth,preferred_language")
            .eq("id", pid)
            .limit(1)
        )
        if not rows:
            raise ValueError("Patient not found")
        p = rows[0]
        item = HandoffItem(
            id=f"patients-{pid}",
            text=f"{p['first_name']} {p['last_name']}",
            detail=f"Date of birth {p.get('date_of_birth')}; preferred language "
            f"{p.get('preferred_language')}",
            source=HandoffSource(
                table="patients", id=pid, label="Patient profile", href=f"/patients/{pid}"
            ),
        )
        return self._section("patient", "Patient", [item], "")

    def _shared_core(self, clinician_id: UUID, pid: str) -> HandoffSection:
        core = SharedClinicalCoreService(self.db).summary_for_clinician(clinician_id, UUID(pid))
        recorders = {
            str(t["care_team_id"]): t for t in core.get("care_teams") or [] if t.get("care_team_id")
        }
        items = [
            *self._core_items("medications", core.get("medications"), recorders, pid),
            *self._core_items("allergies", core.get("allergies"), recorders, pid),
            *self._core_items("conditions", core.get("conditions"), recorders, pid),
        ]
        if core.get("some_conditions_private"):
            items.append(
                HandoffItem(
                    id="conditions-private-marker",
                    text="Some conditions are private and are not included in this summary.",
                    source=HandoffSource(
                        kind="rule", label="The patient limits who sees some conditions"
                    ),
                )
            )
        return self._section(
            "shared_core",
            "Shared record",
            items,
            "No active medications, allergies or visible conditions are recorded.",
        )

    @staticmethod
    def _recorded_by(row: dict[str, Any], recorders: dict[str, dict[str, Any]]) -> str:
        team = recorders.get(str(row.get("recorded_by_care_team_id"))) or {}
        name = row.get("recorded_by") or team.get("clinician_name")
        parts = [p for p in (name, team.get("clinic_name")) if p]
        return "Recorded by " + ", ".join(parts) if parts else "Recording team not recorded"

    def _core_items(
        self, table: str, rows: Any, recorders: dict[str, dict[str, Any]], pid: str
    ) -> list[HandoffItem]:
        items: list[HandoffItem] = []
        for row in rows or []:
            text, detail = self._core_text(table, row)
            items.append(
                HandoffItem(
                    id=f"{table}-{row['id']}",
                    text=text,
                    detail=detail,
                    source=HandoffSource(
                        table=table,
                        id=str(row["id"]),
                        label=self._recorded_by(row, recorders),
                        href=f"/patients/{pid}?tab=profile",
                    ),
                )
            )
        return items

    @staticmethod
    def _core_text(table: str, row: dict[str, Any]) -> tuple[str, str | None]:
        if table == "medications":
            parts = (row.get("name"), row.get("dosage"), row.get("frequency"))
            return "Medication: " + " ".join(str(x) for x in parts if x), _clip(
                row.get("instructions")
            )
        if table == "allergies":
            reaction = ", ".join(str(x) for x in (row.get("reaction"), row.get("severity")) if x)
            return f"Allergy: {row.get('allergen')}", reaction or None
        code = f" ({row['icd10_code']})" if row.get("icd10_code") else ""
        return f"Condition: {row.get('name')}{code}", None

    def _team_plan(self, pid: str, care_team_id: str) -> HandoffSection:
        plans = self._rows(
            self.db.table("care_plans")
            .select("id,care_team_id,ownership_state")
            .eq("patient_id", pid)
            .eq("care_team_id", care_team_id)
            .eq("ownership_state", "owned")
        )
        items: list[HandoffItem] = []
        note: str | None = None
        for plan in plans:
            if str(plan.get("care_team_id")) != care_team_id:
                continue
            version = self._approved_version(str(plan["id"]))
            if version:
                note = f"Approved {_day(version.get('approved_at'))}, version {version['version_number']}."
                items += self._plan_items(pid, version)
        section = self._section(
            "team_plan", "Your care team's plan", items, "Your care team has no approved plan."
        )
        if items:
            section.note = note
        return section

    def _approved_version(self, plan_id: str) -> dict[str, Any] | None:
        versions = self._rows(
            self.db.table("care_plan_versions")
            .select("id,version_number,approved_at")
            .eq("care_plan_id", plan_id)
            .eq("status", "approved")
            .order("approved_at", desc=True)
            .limit(1)
        )
        return versions[0] if versions else None

    def _plan_items(self, pid: str, version: dict[str, Any]) -> list[HandoffItem]:
        rows = self._rows(
            self.db.table("care_plan_items")
            .select("id,title,frequency,instructions,category,is_removed")
            .eq("plan_version_id", str(version["id"]))
            .eq("is_removed", False)
            .order("created_at")
            .limit(PLAN_ITEM_LIMIT)
        )
        return [
            HandoffItem(
                id=f"care_plan_items-{row['id']}",
                text=f"{row.get('title')} ({row.get('frequency')})",
                detail=_clip(row.get("instructions")),
                source=HandoffSource(
                    table="care_plan_items",
                    id=str(row["id"]),
                    label=f"Approved plan version {version['version_number']}",
                    href=f"/patients/{pid}?tab=care-plan#care-plan-item-{row['id']}",
                ),
            )
            for row in rows
        ]

    def _activity(self, pid: str, access: PatientAccess) -> HandoffSection:
        since = (datetime.now(UTC) - timedelta(days=RECENT_DAYS)).isoformat()
        rows = self._rows(
            self.db.table("adherence_logs")
            .select("id,target_type,target_id,status,logged_at")
            .eq("patient_id", pid)
            .gte("logged_at", since)
            .order("logged_at", desc=True)
            .limit(ADHERENCE_LIMIT)
        )
        visible = ActivityScope(self.db, UUID(pid), access).keep(rows)
        counts: dict[str, int] = {}
        for row in visible:
            counts[str(row.get("status"))] = counts.get(str(row.get("status")), 0) + 1
        items: list[HandoffItem] = []
        if visible:
            parts = ", ".join(f"{n} {status}" for status, n in sorted(counts.items()))
            items.append(
                HandoffItem(
                    id="adherence_logs-recent",
                    text=f"{len(visible)} responses in the last {RECENT_DAYS} days: {parts}",
                    detail="Counted from the patient's logged responses to your team's "
                    "activities and to shared activities.",
                    source=HandoffSource(
                        table="adherence_logs",
                        label=f"{len(visible)} logged responses",
                        href=f"/patients/{pid}?tab=timeline",
                    ),
                )
            )
        return self._section(
            "team_activity",
            "Recent activity and adherence",
            items,
            f"No responses were logged in the last {RECENT_DAYS} days.",
        )

    def _symptoms(self, pid: str) -> HandoffSection:
        since = (datetime.now(UTC) - timedelta(days=RECENT_DAYS)).isoformat()
        rows = self._rows(
            self.db.table("symptom_reports")
            .select("id,symptom,severity,created_at,confirmation_state")
            .eq("patient_id", pid)
            .eq("confirmation_state", "patient_confirmed")
            .gte("created_at", since)
            .order("created_at", desc=True)
            .limit(SYMPTOM_LIMIT)
        )
        items = [
            HandoffItem(
                id=f"symptom_reports-{r['id']}",
                text=f"{r.get('symptom')}, severity {r.get('severity')}/10",
                detail=f"Confirmed by the patient {_day(r.get('created_at'))}",
                source=HandoffSource(
                    table="symptom_reports",
                    id=str(r["id"]),
                    label="Patient-confirmed symptom report",
                    href=f"/patients/{pid}?tab=symptoms#symptom-{r['id']}",
                ),
            )
            for r in rows
            if r.get("confirmation_state") == "patient_confirmed"
        ]
        return self._section(
            "symptoms",
            "Recent confirmed symptoms",
            items,
            f"No patient-confirmed symptoms in the last {RECENT_DAYS} days.",
        )

    def _adr(self, pid: str, access: PatientAccess) -> HandoffSection:
        rows = self._rows(
            self.db.table("adr_assessments")
            .select(
                "id,suspect_medication_name,causality,naranjo_score,status,reviewed_by,"
                "reviewed_by_care_team_id,created_at"
            )
            .eq("patient_id", pid)
            .order("created_at", desc=True)
            .limit(ADR_LIMIT * 3)
        )
        mine = [
            r
            for r in rows
            if r.get("status") not in {"dismissed", "submitted"}
            and r.get("reviewed_by")
            and access.can_see_adr(r)
            and access.owns(r.get("reviewed_by_care_team_id"))
        ][:ADR_LIMIT]
        items = [
            HandoffItem(
                id=f"adr_assessments-{r['id']}",
                text=f"{r.get('suspect_medication_name')}: {r.get('causality')} "
                f"(Naranjo score {r.get('naranjo_score')})",
                detail=f"Opened {_day(r.get('created_at'))}",
                source=HandoffSource(
                    table="adr_assessments",
                    id=str(r["id"]),
                    label="Reviewed by your care team",
                    href=f"/adr-reviews/{r['id']}",
                ),
            )
            for r in mine
        ]
        return self._section(
            "open_adr",
            "Open medication-safety reviews",
            items,
            "Your care team has no open medication-safety reviews.",
        )

    def _visits(self, pid: str, access: PatientAccess) -> HandoffSection:
        now = datetime.now(UTC).isoformat()
        rows = self._rows(
            self.db.table("appointments")
            .select("id,care_team_id,scheduled_at,status,appointment_type")
            .eq("patient_id", pid)
            .gte("scheduled_at", now)
            .in_("status", list(OPEN_VISIT_STATUSES))
            .order("scheduled_at")
            .limit(VISIT_LIMIT * 3)
        )
        mine = [r for r in rows if access.owns(r.get("care_team_id"))][:VISIT_LIMIT]
        items = [
            HandoffItem(
                id=f"appointments-{r['id']}",
                text=f"{str(r.get('appointment_type')).replace('_', ' ').capitalize()} on "
                f"{_day(r.get('scheduled_at'))}",
                detail=f"Status: {r.get('status')}",
                source=HandoffSource(
                    table="appointments",
                    id=str(r["id"]),
                    label="Your care team's appointment",
                    href=f"/appointments?appointmentId={r['id']}",
                ),
            )
            for r in mine
        ]
        return self._section("upcoming_visits", "Upcoming visits", items, "No upcoming visits.")

    async def _timeline_section(self, clinician_id: UUID, patient_id: UUID) -> HandoffSection:
        title = "Timeline highlights"
        try:
            timeline = await PatientTimelineService(self.db, self.authorize).get_timeline(
                clinician_id, patient_id
            )
        except AuthorizationError:
            raise
        except Exception as error:
            logger.warning("handoff section timeline unavailable: %s", type(error).__name__)
            return HandoffSection(
                key="timeline",
                title=title,
                status="unavailable",
                note="The timeline could not be read. Rebuild the summary before approving it.",
            )
        events = [e for e in timeline.events if e.domain not in TIMELINE_EXCLUDED_DOMAINS]
        items = [
            HandoffItem(
                id=f"timeline-{e.id}",
                text=f"{e.title} on {_day(e.occurred_at.isoformat())}",
                detail=_clip("; ".join(f"{k}: {v}" for k, v in e.details.items() if v), 240),
                source=HandoffSource(
                    table=e.source_table,
                    id=str(e.source_id),
                    label=f"{e.timestamp_label} record",
                    href=e.source_href,
                ),
            )
            for e in events[:TIMELINE_LIMIT]
        ]
        section = self._section("timeline", title, items, "No timeline events were found.")
        degraded = [s.source for s in timeline.sources if s.status == "unavailable"]
        if degraded:
            section.note = "Some timeline sources could not be read: " + ", ".join(degraded)
            if section.status == "empty":
                section.status = "unavailable"
        return section
