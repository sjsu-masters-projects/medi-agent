"""Bounded, read-only timeline of actual source records for an assigned clinician."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.models.dashboard import (
    PatientTimelineEvent,
    PatientTimelineResponse,
    TimelineSourceCoverage,
)
from app.services.care_plan_activity_scope import ActivityScope
from app.services.care_team_access import CareTeamAccessService, PatientAccess

SOURCE_LIMIT = 40
CONVERSATION_LIMIT = 10


@dataclass(frozen=True)
class Source:
    table: str
    domain: str
    title: str
    fields: str
    timestamp: str = "created_at"
    timestamp_label: str = "Recorded"
    parent: str | None = None
    reference: str | None = None
    tab: str | None = None


SOURCES = (
    Source(
        "documents", "document", "Document uploaded", "file_name,review_status", tab="documents"
    ),
    Source(
        "documents",
        "approval",
        "Document review",
        "file_name,review_status",
        "reviewed_at",
        "Reviewed",
        tab="documents",
    ),
    Source(
        "medications",
        "medication",
        "Medication recorded",
        "name,dosage,frequency,is_active,start_date,end_date",
    ),
    Source(
        "symptom_reports",
        "symptom",
        "Patient-confirmed symptom",
        "symptom,severity,confirmation_state",
    ),
    Source(
        "adherence_logs",
        "adherence",
        "Adherence response",
        "target_type,target_id,status",
        "logged_at",
        "Logged",
    ),
    Source(
        "care_conversation_messages",
        "message",
        "Private message",
        "sender_role,conversation_id",
        parent="care_conversations",
        reference="conversation_id",
        tab="messages",
    ),
    Source(
        "appointments",
        "appointment",
        "Appointment recorded",
        "scheduled_at,status,appointment_type",
        tab="appointments",
    ),
    Source(
        "appointment_offer_events",
        "action",
        "Appointment action",
        "appointment_id,action,new_status",
        reference="appointment_id",
        tab="appointments",
    ),
    Source(
        "care_plan_audit_events",
        "approval",
        "Care-plan event",
        "plan_version_id,event_type",
        parent="care_plan_versions",
        reference="plan_version_id",
    ),
    Source(
        "clinical_fact_audit_events",
        "approval",
        "Clinical fact event",
        "fact_id,event_type",
        parent="clinical_facts",
        reference="fact_id",
    ),
    Source(
        "adr_assessment_audit_events",
        "action",
        "ADR review action",
        "adr_assessment_id,event_type",
        parent="adr_assessments",
        reference="adr_assessment_id",
        tab="adr",
    ),
    Source(
        "clinical_action_audit_records",
        "action",
        "Clinical action event",
        "recommendation_id,event_type",
        parent="clinical_recommendations",
        reference="recommendation_id",
    ),
)


class PatientTimelineService:
    """Authorize before building any source query, including private-thread joins."""

    def __init__(self, db: Client, authorize: Callable[[UUID, UUID], Awaitable[None]]) -> None:
        self.db = db
        self.authorize = authorize

    async def get_timeline(self, clinician_id: UUID, patient_id: UUID) -> PatientTimelineResponse:
        await self.authorize(clinician_id, patient_id)
        # Documents, plan versions, ADR reviews, visits and the facts behind them belong to
        # one care team; only this clinician's own links decide what appears.
        access = await asyncio.to_thread(
            CareTeamAccessService(self.db).for_patient, clinician_id, patient_id, require=False
        )
        activities = ActivityScope(self.db, patient_id, access)
        batches = await asyncio.gather(
            *(
                self._read_source(source, clinician_id, patient_id, access, activities)
                for source in SOURCES
            )
        )
        events = [event for batch, _ in batches for event in batch]
        events.sort(key=lambda event: (event.occurred_at, event.id), reverse=True)
        return PatientTimelineResponse(
            patient_id=patient_id,
            retrieved_at=datetime.now(UTC),
            events=events,
            sources=[coverage for _, coverage in batches],
        )

    def _query(self, source: Source, clinician_id: UUID, patient_id: UUID) -> Any:
        columns = f"id,{source.timestamp},{source.fields}"
        if source.parent:
            columns += f",{source.parent}!inner(patient_id)"
        query = self.db.table(source.table).select(columns)
        scope = f"{source.parent}.patient_id" if source.parent else "patient_id"
        query = query.eq(scope, str(patient_id))
        if source.domain == "symptom":
            query = query.eq("confirmation_state", "patient_confirmed")
        return (
            query.not_.is_(source.timestamp, "null")
            .order(source.timestamp, desc=True)
            .order("id", desc=True)
            .limit(SOURCE_LIMIT + 1)
        )

    async def _read_source(
        self,
        source: Source,
        clinician_id: UUID,
        patient_id: UUID,
        access: PatientAccess,
        activities: ActivityScope,
    ) -> tuple[list[PatientTimelineEvent], TimelineSourceCoverage]:
        coverage = TimelineSourceCoverage(
            source=f"{source.table}.{source.timestamp}", status="available", limit=SOURCE_LIMIT
        )
        try:
            if source.domain == "message":
                rows = await self._read_messages(clinician_id, patient_id, coverage)
            else:
                result = await asyncio.to_thread(
                    self._query(source, clinician_id, patient_id).execute
                )
                rows = result.data
                if isinstance(rows, list):
                    rows = await asyncio.to_thread(self._owned, source, rows, access, activities)
            if not isinstance(rows, list):
                raise ValueError("Expected a source row list")
        except Exception:
            # Coverage is explicitly unavailable; never represent a failed read as no events.
            coverage.status = "unavailable"
            return [], coverage
        coverage.has_more = len(rows) > SOURCE_LIMIT or bool(coverage.conversations_truncated)
        events = []
        for row in rows[:SOURCE_LIMIT]:
            try:
                events.append(self._event(source, row, patient_id))
            except (ValueError, TypeError, KeyError):
                coverage.omitted_invalid += 1
        coverage.returned = len(events)
        return events, coverage

    def _fetch(self, table: str, columns: str, ids: list[str]) -> dict[str, dict[str, Any]]:
        found: dict[str, dict[str, Any]] = {}
        wanted = sorted(set(ids))
        for start in range(0, len(wanted), 100):
            result = (
                self.db.table(table)
                .select(columns)
                .in_("id", wanted[start : start + 100])
                .execute()
            )
            for item in cast(list[dict[str, Any]], result.data or []):
                found[str(item["id"])] = item
        return found

    def _owned(
        self, source: Source, rows: list[Any], access: PatientAccess, activities: ActivityScope
    ) -> list[Any]:
        """Keep the events this clinician may read; an owner that cannot be found hides it.

        Medications, confirmed symptoms and private threads (already limited to the actor) are
        shared. Everything else follows the record it is about. A lookup failure raises, which
        marks the source unavailable rather than showing it unfiltered.
        """
        table = source.table
        if table in {"medications", "symptom_reports", "clinical_action_audit_records"}:
            return rows
        if table == "adherence_logs":
            return activities.keep(rows)
        if table == "documents":
            docs = self._fetch(
                "documents", "id, routing_state, care_team_id", [r["id"] for r in rows]
            )
            return [r for r in rows if r["id"] in docs and access.can_see_document(docs[r["id"]])]
        if table in {"appointments", "appointment_offer_events"}:
            key = "appointment_id" if table == "appointment_offer_events" else "id"
            visits = self._fetch("appointments", "id, care_team_id", [r[key] for r in rows])
            return [
                r
                for r in rows
                if r[key] in visits and access.owns(visits[r[key]].get("care_team_id"))
            ]
        if table == "adr_assessment_audit_events":
            adrs = self._fetch(
                "adr_assessments",
                "id, reviewed_by, reviewed_by_care_team_id",
                [r["adr_assessment_id"] for r in rows],
            )
            return [
                r
                for r in rows
                if r["adr_assessment_id"] in adrs
                and access.can_see_adr(adrs[r["adr_assessment_id"]])
            ]
        if table == "clinical_fact_audit_events":
            visible = CareTeamAccessService(self.db).visible_fact_ids(
                access, [r["fact_id"] for r in rows]
            )
            return [r for r in rows if str(r["fact_id"]) in visible]
        if table == "care_plan_audit_events":
            versions = self._fetch(
                "care_plan_versions", "id, care_plan_id", [r["plan_version_id"] for r in rows]
            )
            plans = self._fetch(
                "care_plans",
                "id, care_team_id, ownership_state",
                [v["care_plan_id"] for v in versions.values() if v.get("care_plan_id")],
            )

            def readable(version_id: str) -> bool:
                plan = plans.get(str((versions.get(version_id) or {}).get("care_plan_id")))
                return bool(plan) and access.can_read_plan(cast(dict[str, Any], plan))

            return [r for r in rows if readable(r["plan_version_id"])]
        return []  # a source this module does not know how to scope is never shown

    async def _read_messages(
        self, clinician_id: UUID, patient_id: UUID, coverage: TimelineSourceCoverage
    ) -> list[dict[str, Any]]:
        # Discover only this actor's threads. The existing RPC then locks and verifies
        # the exact team, conversation clinic and active membership before reading messages.
        query = (
            self.db.table("care_conversations")
            .select("id")
            .eq("patient_id", str(patient_id))
            .eq("clinician_id", str(clinician_id))
            .order("last_message_at", desc=True, nullsfirst=False)
            .order("id", desc=True)
            .limit(CONVERSATION_LIMIT + 1)
        )
        result = await asyncio.to_thread(query.execute)
        if not isinstance(result.data, list):
            raise ValueError("Expected conversation rows")
        coverage.conversation_limit = CONVERSATION_LIMIT
        coverage.conversations_truncated = len(result.data) > CONVERSATION_LIMIT
        threads = cast(list[dict[str, Any]], result.data)
        batches = await asyncio.gather(
            *(
                self._thread_messages(clinician_id, UUID(thread["id"]))
                for thread in threads[:CONVERSATION_LIMIT]
            )
        )
        rows = [row for batch in batches for row in batch]
        rows.sort(
            key=lambda row: (
                datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
                row["id"],
            ),
            reverse=True,
        )
        return rows[: SOURCE_LIMIT + 1]

    async def _thread_messages(self, clinician_id: UUID, thread_id: UUID) -> list[dict[str, Any]]:
        result = await asyncio.to_thread(
            self.db.rpc(
                "care_conversation_operation",
                {
                    "p_actor_id": str(clinician_id),
                    "p_actor_role": "clinician",
                    "p_action": "messages",
                    "p_payload": {"conversation_id": str(thread_id), "limit": SOURCE_LIMIT + 1},
                },
            ).execute
        )
        if not isinstance(result.data, dict) or not isinstance(result.data.get("items"), list):
            raise ValueError("Expected authorized message rows")
        return [{**row, "conversation_id": str(thread_id)} for row in result.data["items"]]

    @staticmethod
    def _event(source: Source, row: dict[str, Any], patient_id: UUID) -> PatientTimelineEvent:
        source_id = UUID(row["id"])
        timestamp = row.get(source.timestamp)
        if not isinstance(timestamp, str):
            raise ValueError("Missing source date")
        occurred_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if occurred_at.tzinfo is None:
            raise ValueError("A source timestamp must include its timezone")
        event_id = f"{source.table}-{source.timestamp}-{source_id}"
        base = f"/patients/{patient_id}"
        details = {
            field: _display(row.get(field))
            for field in source.fields.split(",")
            if not field.endswith("_id")
        }
        reference = UUID(row[source.reference]) if source.reference else source_id
        destination = None
        if source.tab == "documents":
            destination = f"{base}?tab=documents#document-{reference}"
        elif source.tab == "appointments":
            destination = f"/appointments?appointmentId={reference}"
        elif source.tab == "messages":
            destination = f"/messages?conversation={reference}"
        elif source.tab == "adr":
            destination = f"/adr-reviews/{reference}"
        elif source.domain == "symptom":
            destination = f"{base}?tab=symptoms#symptom-{source_id}"
        return PatientTimelineEvent(
            id=event_id,
            domain=source.domain,
            source_table=source.table,
            source_id=source_id,
            occurred_at=occurred_at,
            timestamp_label=source.timestamp_label,
            title=source.title,
            details=details,
            source_href=f"{base}?tab=timeline#source-{event_id}",
            destination_href=destination,
        )


def _display(value: Any) -> str | None:
    """Only selected scalar source fields; never raw payloads, private rationale or URLs."""
    if value is None:
        return None
    if isinstance(value, str | bool | int | float):
        return str(value)
    raise ValueError("Expected a scalar source field")
