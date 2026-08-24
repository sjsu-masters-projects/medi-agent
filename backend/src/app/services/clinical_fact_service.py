"""Clinical-fact registry with explicit review gates and immutable audit events."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.core.exceptions import NotFoundError, ValidationError
from app.models.clinical_fact import (
    ClinicalFactCreate,
    ClinicalFactReviewState,
    EvidenceCitationCreate,
)


class ClinicalFactService:
    """Persist candidate facts without allowing extraction output to self-approve."""

    def __init__(self, db: Client) -> None:
        self.db = db

    def create_candidate(self, candidate: ClinicalFactCreate, *, actor_id: UUID) -> dict[str, Any]:
        """Register a fact as pending review with provenance, citations, and an audit event."""
        fact_payload = {
            "patient_id": str(candidate.patient_id),
            "fact_type": candidate.fact_type,
            "subject_type": candidate.subject_type,
            "subject_id": str(candidate.subject_id) if candidate.subject_id else None,
            "value": candidate.value,
            "confidence_score": candidate.confidence_score,
            "confidence_band": candidate.confidence_band.value,
            "uncertainty": candidate.uncertainty,
            "review_state": ClinicalFactReviewState.PENDING_REVIEW.value,
        }
        fact = self._insert_one("clinical_facts", fact_payload, "clinical fact")
        fact_id = UUID(str(fact["id"]))

        provenance_payload = candidate.provenance.model_dump(mode="json", exclude_none=True)
        provenance_payload["captured_at"] = (
            candidate.provenance.captured_at or datetime.now(UTC)
        ).isoformat()
        provenance = self._insert_one("source_provenances", provenance_payload, "source provenance")
        provenance_id = UUID(str(provenance["id"]))

        for citation in candidate.citations:
            self._create_citation(fact_id, provenance_id, citation)

        self._audit(
            fact_id=fact_id,
            actor_id=actor_id,
            event_type="created",
            event_data={"review_state": ClinicalFactReviewState.PENDING_REVIEW.value},
        )
        return fact

    def approve(
        self, fact_id: UUID, patient_id: UUID, *, reviewer_id: UUID, note: str | None = None
    ) -> dict[str, Any]:
        """Explicitly approve a pending candidate; no other transition implies approval."""
        fact = self._get_fact(fact_id, patient_id)
        self._require_pending(fact)
        return self._set_review_state(
            fact_id,
            patient_id,
            reviewer_id=reviewer_id,
            review_state=ClinicalFactReviewState.APPROVED,
            note=note,
            event_type="approved",
        )

    def reject(
        self, fact_id: UUID, patient_id: UUID, *, reviewer_id: UUID, note: str
    ) -> dict[str, Any]:
        """Reject a pending candidate and retain the decision in the audit trail."""
        if not note.strip():
            raise ValidationError("A rejection note is required")
        fact = self._get_fact(fact_id, patient_id)
        self._require_pending(fact)
        return self._set_review_state(
            fact_id,
            patient_id,
            reviewer_id=reviewer_id,
            review_state=ClinicalFactReviewState.REJECTED,
            note=note,
            event_type="rejected",
        )

    def correct(
        self,
        fact_id: UUID,
        patient_id: UUID,
        *,
        actor_id: UUID,
        value: dict[str, Any],
        note: str,
    ) -> dict[str, Any]:
        """Correct a candidate and return it to pending review, preserving before/after values."""
        if not note.strip():
            raise ValidationError("A correction note is required")
        fact = self._get_fact(fact_id, patient_id)
        if fact.get("review_state") == ClinicalFactReviewState.DELETED.value:
            raise ValidationError("Deleted clinical facts cannot be corrected")

        updated = self._update_one(
            "clinical_facts",
            {
                "value": value,
                "review_state": ClinicalFactReviewState.PENDING_REVIEW.value,
                "reviewed_by": None,
                "reviewed_at": None,
                "review_note": None,
            },
            fact_id,
            patient_id,
        )
        self._audit(
            fact_id=fact_id,
            actor_id=actor_id,
            event_type="corrected",
            event_data={"before": fact.get("value", {}), "after": value, "note": note.strip()},
        )
        return updated

    def delete(
        self, fact_id: UUID, patient_id: UUID, *, actor_id: UUID, note: str
    ) -> dict[str, Any]:
        """Soft-delete a fact so provenance and audit history remain queryable."""
        if not note.strip():
            raise ValidationError("A deletion note is required")
        fact = self._get_fact(fact_id, patient_id)
        if fact.get("review_state") == ClinicalFactReviewState.DELETED.value:
            raise ValidationError("Clinical fact is already deleted")

        updated = self._update_one(
            "clinical_facts",
            {"review_state": ClinicalFactReviewState.DELETED.value},
            fact_id,
            patient_id,
        )
        self._audit(
            fact_id=fact_id,
            actor_id=actor_id,
            event_type="deleted",
            event_data={"previous_review_state": fact.get("review_state"), "note": note.strip()},
        )
        return updated

    def list_approved(self, patient_id: UUID) -> list[dict[str, Any]]:
        """Return only explicitly approved facts for clinical-display consumers."""
        result = (
            self.db.table("clinical_facts")
            .select("*")
            .eq("patient_id", str(patient_id))
            .eq("review_state", ClinicalFactReviewState.APPROVED.value)
            .order("created_at", desc=True)
            .execute()
        )
        return cast(list[dict[str, Any]], result.data or [])

    def get_lineage(self, fact_id: UUID, patient_id: UUID) -> dict[str, Any]:
        """Trace a candidate from the fact through citations to its original artifact."""
        fact = self._get_fact(fact_id, patient_id)
        citation_result = (
            self.db.table("evidence_citations").select("*").eq("fact_id", str(fact_id)).execute()
        )
        citations = cast(list[dict[str, Any]], citation_result.data or [])
        provenance_ids = sorted(
            {str(row["provenance_id"]) for row in citations if row.get("provenance_id")}
        )
        provenances: list[dict[str, Any]] = []
        if provenance_ids:
            provenance_result = (
                self.db.table("source_provenances").select("*").in_("id", provenance_ids).execute()
            )
            provenances = cast(list[dict[str, Any]], provenance_result.data or [])
        return {"fact": fact, "citations": citations, "provenances": provenances}

    def list_facts_for_document(self, document_id: UUID, patient_id: UUID) -> list[dict[str, Any]]:
        """Trace an original document artifact to every non-deleted fact it supports."""
        source_result = (
            self.db.table("source_provenances")
            .select("id")
            .eq("document_id", str(document_id))
            .execute()
        )
        source_rows = cast(list[dict[str, Any]], source_result.data or [])
        provenance_ids = [str(row["id"]) for row in source_rows if row.get("id")]
        if not provenance_ids:
            return []
        citation_result = (
            self.db.table("evidence_citations")
            .select("fact_id")
            .in_("provenance_id", provenance_ids)
            .execute()
        )
        citation_rows = cast(list[dict[str, Any]], citation_result.data or [])
        fact_ids = [str(row["fact_id"]) for row in citation_rows if row.get("fact_id")]
        if not fact_ids:
            return []
        result = (
            self.db.table("clinical_facts")
            .select("*")
            .eq("patient_id", str(patient_id))
            .in_("id", fact_ids)
            .execute()
        )
        return [
            row
            for row in cast(list[dict[str, Any]], result.data or [])
            if row.get("review_state") != ClinicalFactReviewState.DELETED.value
        ]

    def _create_citation(
        self,
        fact_id: UUID,
        provenance_id: UUID,
        citation: EvidenceCitationCreate,
    ) -> None:
        self._insert_one(
            "evidence_citations",
            {
                "fact_id": str(fact_id),
                "provenance_id": str(provenance_id),
                "excerpt": citation.excerpt,
                "location": citation.location,
            },
            "evidence citation",
        )

    def _set_review_state(
        self,
        fact_id: UUID,
        patient_id: UUID,
        *,
        reviewer_id: UUID,
        review_state: ClinicalFactReviewState,
        note: str | None,
        event_type: str,
    ) -> dict[str, Any]:
        reviewed_at = datetime.now(UTC).isoformat()
        updated = self._update_one(
            "clinical_facts",
            {
                "review_state": review_state.value,
                "reviewed_by": str(reviewer_id),
                "reviewed_at": reviewed_at,
                "review_note": note.strip() if note else None,
            },
            fact_id,
            patient_id,
        )
        self._audit(
            fact_id=fact_id,
            actor_id=reviewer_id,
            event_type=event_type,
            event_data={"review_state": review_state.value, "note": note.strip() if note else None},
        )
        return updated

    def _get_fact(self, fact_id: UUID, patient_id: UUID) -> dict[str, Any]:
        result = (
            self.db.table("clinical_facts")
            .select("*")
            .eq("id", str(fact_id))
            .eq("patient_id", str(patient_id))
            .single()
            .execute()
        )
        fact = cast(dict[str, Any] | None, result.data)
        if not fact:
            raise NotFoundError("Clinical fact", str(fact_id))
        return fact

    def _require_pending(self, fact: dict[str, Any]) -> None:
        if fact.get("review_state") != ClinicalFactReviewState.PENDING_REVIEW.value:
            raise ValidationError("Only pending clinical facts can be reviewed")

    def _insert_one(self, table: str, payload: dict[str, Any], resource: str) -> dict[str, Any]:
        result = self.db.table(table).insert(payload).execute()
        rows = cast(list[dict[str, Any]], result.data or [])
        if not rows:
            raise ValidationError(f"Could not create {resource}")
        return rows[0]

    def _update_one(
        self,
        table: str,
        payload: dict[str, Any],
        fact_id: UUID,
        patient_id: UUID,
    ) -> dict[str, Any]:
        result = (
            self.db.table(table)
            .update(payload)
            .eq("id", str(fact_id))
            .eq("patient_id", str(patient_id))
            .execute()
        )
        rows = cast(list[dict[str, Any]], result.data or [])
        if not rows:
            raise NotFoundError("Clinical fact", str(fact_id))
        return rows[0]

    def _audit(
        self,
        *,
        fact_id: UUID,
        actor_id: UUID,
        event_type: str,
        event_data: dict[str, Any],
    ) -> None:
        self._insert_one(
            "clinical_fact_audit_events",
            {
                "fact_id": str(fact_id),
                "actor_id": str(actor_id),
                "event_type": event_type,
                "event_data": event_data,
            },
            "clinical fact audit event",
        )
