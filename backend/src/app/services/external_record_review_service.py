"""Bounded source-driven review work for the caller's current patient links."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.core.exceptions import ExternalServiceError
from app.db.supabase_execute import execute_async
from app.models.external_record_review import (
    ExternalRecordReviewItem,
    ExternalRecordReviewsResponse,
)
from app.services.care_team_access import CareTeamAccessService, PatientAccess
from app.services.clinic_membership_service import ClinicMembershipService

PAGE_SIZE = 10
CANDIDATE_LIMIT = 200
CITATION_LIMIT = 20
# Beyond the inspected page, later candidates are read as ids only, to count the visible ones.
TAIL_PAGE = 200
TAIL_PAGES = 10
SOURCE_TYPES = ("document", "fhir_resource", "external_record")


class ExternalRecordReviewService:
    def __init__(self, db: Client) -> None:
        self.db = db
        self.memberships = ClinicMembershipService(self)
        self.access = CareTeamAccessService(db)

    async def list_reviews(
        self, clinician_id: UUID, *, clinic_id: UUID | None = None, page: int = 1
    ) -> ExternalRecordReviewsResponse:
        scope = await self.memberships.link_scope(clinician_id, clinic_id)
        patients = sorted(scope.patient_ids)
        links = await asyncio.to_thread(self.access.for_clinician, clinician_id)
        selected = patients[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]
        items = []
        if selected:
            names = await self._read(
                lambda db: db.table("patients")
                .select("id,first_name,last_name")
                .in_("id", selected)
                .limit(PAGE_SIZE)
            )
            by_id = {str(row["id"]): row for row in names.data or []}
            results = await asyncio.gather(
                *(self._patient(patient, links.for_patient(patient)) for patient in selected)
            )
            for patient, result in zip(selected, results, strict=True):
                if result["pending_count"]:
                    name = by_id.get(patient, {})
                    items.append(
                        ExternalRecordReviewItem(
                            patient_id=UUID(patient),
                            patient_name=" ".join(
                                str(name.get(key) or "") for key in ("first_name", "last_name")
                            ).strip()
                            or "Assigned patient",
                            **scope.tag(patient),
                            **result,
                        )
                    )
        return ExternalRecordReviewsResponse(
            items=items,
            retrieved_at=datetime.now(UTC),
            page=page,
            page_size=PAGE_SIZE,
            assigned_patients=len(patients),
            patients_examined=len(selected),
            has_more=page * PAGE_SIZE < len(patients),
            candidate_limit=CANDIDATE_LIMIT,
            citation_limit=CITATION_LIMIT,
        )

    async def _patient(self, patient_id: str, access: PatientAccess) -> dict[str, Any]:
        # Inner source joins exclude local/private reports and withdrawn artifacts.
        # Never select values, excerpts, reviewer notes, import actors or private messages.
        # Only candidates whose every source this clinician's teams may see are counted: a
        # document routed to another care team never adds to this clinician's workload.
        result = await self._read(
            lambda db: db.table("clinical_facts")
            .select(
                "id,evidence_citations!inner(source_provenances!inner(artifact_type,captured_at,withdrawn_at))",
                count="exact",  # type: ignore[arg-type]
            )
            .eq("patient_id", patient_id)
            .eq("review_state", "pending_review")
            .in_("reconciliation_state", ["not_started", "deferred"])
            .in_("evidence_citations.source_provenances.artifact_type", list(SOURCE_TYPES))
            .is_("evidence_citations.source_provenances.withdrawn_at", "null")
            .order("created_at")
            .order("id")
            .limit(CANDIDATE_LIMIT)
            .limit(CITATION_LIMIT, foreign_table="evidence_citations")
        )
        if result.count is None:
            raise ExternalServiceError("External record reviews", "Pending count unavailable")
        rows = cast(list[dict[str, Any]], result.data or [])
        total = result.count
        allowed = await asyncio.to_thread(
            self.access.visible_fact_ids, access, [row["id"] for row in rows]
        )
        rows = [row for row in rows if str(row["id"]) in allowed]
        tail_visible = 0
        tail_complete = True
        if total > CANDIDATE_LIMIT:
            tail_visible, tail_complete = await self._visible_tail(patient_id, access, total)
        visible_total = len(rows) + tail_visible
        times, complete = self._source_times(rows)
        return {
            "pending_count": visible_total,
            "inspected_candidates": len(rows),
            "oldest_source_captured_at": min(times) if times else None,
            "source_times_complete": complete and tail_complete and len(rows) == visible_total,
        }

    @staticmethod
    def _tail_query(patient_id: str, start: int) -> Callable[[Client], Any]:
        def build(db: Client) -> Any:
            return (
                db.table("clinical_facts")
                .select("id,evidence_citations!inner(source_provenances!inner(artifact_type))")
                .eq("patient_id", patient_id)
                .eq("review_state", "pending_review")
                .in_("reconciliation_state", ["not_started", "deferred"])
                .in_("evidence_citations.source_provenances.artifact_type", list(SOURCE_TYPES))
                .is_("evidence_citations.source_provenances.withdrawn_at", "null")
                .order("created_at")
                .order("id")
                .range(start, start + TAIL_PAGE - 1)
            )

        return build

    async def _visible_tail(
        self, patient_id: str, access: PatientAccess, total: int
    ) -> tuple[int, bool]:
        """Visible candidates beyond the inspected page (ids only), and whether all were read."""
        visible = 0
        read = CANDIDATE_LIMIT
        for _ in range(TAIL_PAGES):
            if read >= total:
                return visible, True
            page = await self._read(self._tail_query(patient_id, read))
            ids = [row["id"] for row in cast(list[dict[str, Any]], page.data or [])]
            if not ids:
                return visible, False
            visible += len(await asyncio.to_thread(self.access.visible_fact_ids, access, ids))
            read += len(ids)
        return visible, read >= total

    @staticmethod
    def _source_times(rows: list[dict[str, Any]]) -> tuple[list[datetime], bool]:
        times: list[datetime] = []
        complete = True
        for row in rows:
            citations = row.get("evidence_citations") or []
            if not citations or len(citations) >= CITATION_LIMIT:
                complete = False
            for citation in citations:
                source = citation.get("source_provenances") or {}
                try:
                    when = datetime.fromisoformat(str(source.get("captured_at")))
                    if when.tzinfo is None:
                        raise ValueError("Source timezone unavailable")
                    times.append(when.astimezone(UTC))
                except ValueError:
                    complete = False
        return times, complete

    async def _read(self, build: Callable[[Client], Any]) -> Any:
        try:
            return await execute_async(self, build, operation="external record review lookup")
        except Exception as exc:
            raise ExternalServiceError(
                "External record reviews", "Unable to retrieve review work"
            ) from exc
