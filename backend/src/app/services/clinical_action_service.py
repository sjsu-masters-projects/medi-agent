"""Server-enforced approval and idempotency gate for clinical actions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.models.clinical_action import (
    ActionEnvelopeCreate,
    ApprovalDecisionCreate,
    ApprovalDecisionType,
    ClinicalActionState,
    ClinicalRecommendationCreate,
)


class ClinicalActionService:
    """Keep recommendation, approval, execution, and audit transitions together."""

    def __init__(self, db: Client) -> None:
        self.db = db

    def propose(
        self, recommendation: ClinicalRecommendationCreate, *, actor_id: UUID | None = None
    ) -> dict[str, Any]:
        if actor_id is not None:
            self._require_assignment(actor_id, recommendation.patient_id)
        created = self._insert(
            "clinical_recommendations",
            {
                **recommendation.model_dump(mode="json"),
                "proposed_by": str(actor_id) if actor_id else None,
                "state": ClinicalActionState.PENDING_APPROVAL.value,
            },
            "clinical recommendation",
        )
        self._audit(
            UUID(str(created["id"])),
            actor_id,
            "proposed",
            {"action_type": recommendation.action_type},
        )
        return created

    def decide(
        self,
        recommendation_id: UUID,
        *,
        reviewer_id: UUID,
        decision: ApprovalDecisionCreate,
    ) -> dict[str, Any]:
        recommendation = self._get_recommendation(recommendation_id)
        patient_id = UUID(str(recommendation["patient_id"]))
        self._require_assignment(reviewer_id, patient_id)
        if recommendation.get("state") != ClinicalActionState.PENDING_APPROVAL.value:
            raise ValidationError("Only pending recommendations can be decided")
        if str(recommendation.get("proposed_by") or "") == str(reviewer_id):
            raise AuthorizationError("A clinician cannot approve their own recommendation")

        state = (
            ClinicalActionState.APPROVED
            if decision.decision is ApprovalDecisionType.APPROVE
            else ClinicalActionState.REJECTED
        )
        self._insert(
            "approval_decisions",
            {
                "recommendation_id": str(recommendation_id),
                "reviewer_id": str(reviewer_id),
                "decision": decision.decision.value,
                "note": decision.note.strip(),
                "edited_payload": decision.edited_payload,
            },
            "approval decision",
        )
        updated = self._update_recommendation(
            recommendation_id,
            {
                "state": state.value,
                **(
                    {"proposed_payload": decision.edited_payload} if decision.edited_payload else {}
                ),
            },
        )
        self._audit(
            recommendation_id,
            reviewer_id,
            state.value,
            {"note": decision.note.strip(), "edited": decision.edited_payload is not None},
        )
        return updated

    def get_or_create_envelope(
        self,
        recommendation_id: UUID,
        *,
        clinician_id: UUID,
        envelope: ActionEnvelopeCreate,
    ) -> dict[str, Any]:
        recommendation = self._get_recommendation(recommendation_id)
        self._require_assignment(clinician_id, UUID(str(recommendation["patient_id"])))
        if recommendation.get("state") != ClinicalActionState.APPROVED.value:
            raise ValidationError("Clinical action requires an approved recommendation")
        existing = (
            self.db.table("action_envelopes")
            .select("*")
            .eq("recommendation_id", str(recommendation_id))
            .eq("idempotency_key", envelope.idempotency_key)
            .execute()
        )
        rows = cast(list[dict[str, Any]], existing.data or [])
        if rows:
            return rows[0]
        created = self._insert(
            "action_envelopes",
            {
                "recommendation_id": str(recommendation_id),
                "idempotency_key": envelope.idempotency_key,
                "state": ClinicalActionState.APPROVED.value,
            },
            "action envelope",
        )
        self._audit(
            recommendation_id, clinician_id, "execution_requested", {"envelope_id": created["id"]}
        )
        return created

    def record_outcome(
        self,
        envelope_id: UUID,
        *,
        clinician_id: UUID,
        outcome: dict[str, Any],
        succeeded: bool,
    ) -> dict[str, Any]:
        envelope = self._get_envelope(envelope_id)
        recommendation = self._get_recommendation(UUID(str(envelope["recommendation_id"])))
        self._require_assignment(clinician_id, UUID(str(recommendation["patient_id"])))
        if envelope.get("state") in {
            ClinicalActionState.EXECUTED.value,
            ClinicalActionState.FAILED.value,
        }:
            return envelope
        state = ClinicalActionState.EXECUTED if succeeded else ClinicalActionState.FAILED
        result = (
            self.db.table("action_envelopes")
            .update(
                {
                    "state": state.value,
                    "outcome": outcome,
                    "executed_by": str(clinician_id),
                    "executed_at": datetime.now(UTC).isoformat(),
                }
            )
            .eq("id", str(envelope_id))
            .execute()
        )
        rows = cast(list[dict[str, Any]], result.data or [])
        if not rows:
            raise NotFoundError("Action envelope", str(envelope_id))
        self._update_recommendation(UUID(str(recommendation["id"])), {"state": state.value})
        self._audit(
            UUID(str(recommendation["id"])), clinician_id, state.value, {"outcome": outcome}
        )
        return rows[0]

    def _require_assignment(self, clinician_id: UUID, patient_id: UUID) -> None:
        response = (
            self.db.table("care_teams")
            .select("id")
            .eq("clinician_id", str(clinician_id))
            .eq("patient_id", str(patient_id))
            .eq("status", "active")
            .execute()
        )
        if not response.data:
            raise AuthorizationError("You are not assigned to this patient")

    def _get_recommendation(self, recommendation_id: UUID) -> dict[str, Any]:
        response = (
            self.db.table("clinical_recommendations")
            .select("*")
            .eq("id", str(recommendation_id))
            .single()
            .execute()
        )
        record = cast(dict[str, Any] | None, response.data)
        if not record:
            raise NotFoundError("Clinical recommendation", str(recommendation_id))
        return record

    def _get_envelope(self, envelope_id: UUID) -> dict[str, Any]:
        response = (
            self.db.table("action_envelopes")
            .select("*")
            .eq("id", str(envelope_id))
            .single()
            .execute()
        )
        record = cast(dict[str, Any] | None, response.data)
        if not record:
            raise NotFoundError("Action envelope", str(envelope_id))
        return record

    def _update_recommendation(
        self, recommendation_id: UUID, payload: dict[str, Any]
    ) -> dict[str, Any]:
        response = (
            self.db.table("clinical_recommendations")
            .update(payload)
            .eq("id", str(recommendation_id))
            .execute()
        )
        rows = cast(list[dict[str, Any]], response.data or [])
        if not rows:
            raise NotFoundError("Clinical recommendation", str(recommendation_id))
        return rows[0]

    def _audit(
        self,
        recommendation_id: UUID,
        actor_id: UUID | None,
        event_type: str,
        event_data: dict[str, Any],
    ) -> None:
        self._insert(
            "clinical_action_audit_records",
            {
                "recommendation_id": str(recommendation_id),
                "actor_id": str(actor_id) if actor_id else None,
                "event_type": event_type,
                "event_data": event_data,
            },
            "clinical action audit record",
        )

    def _insert(self, table: str, payload: dict[str, Any], resource: str) -> dict[str, Any]:
        response = self.db.table(table).insert(payload).execute()
        rows = cast(list[dict[str, Any]], response.data or [])
        if not rows:
            raise ValidationError(f"Could not create {resource}")
        return rows[0]
