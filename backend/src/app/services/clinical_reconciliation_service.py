"""Conservative, clinician-controlled projection of candidate facts.

The service deliberately has no bulk path. It validates the candidate and
selected fields before invoking the database transaction that changes local
clinical truth and records the append-only reconciliation event.
"""

from __future__ import annotations

import re
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.core.exceptions import NotFoundError, ValidationError
from app.models.reconciliation import ReconciliationDecision, ReconciliationDecisionRequest
from app.services.external_patient_binding_service import ExternalPatientBindingService


class ClinicalReconciliationService:
    """Match and reconcile one pending external candidate at a time."""

    PROJECTABLE_FACT_TYPES = frozenset({"medication", "condition", "allergy"})
    _TARGET_TABLE = {
        "medication": "medications",
        "condition": "conditions",
        "allergy": "allergies",
    }
    _FIELDS = {
        "medication": frozenset(
            {
                "name",
                "generic_name",
                "rxcui",
                "dosage",
                "frequency",
                "route",
                "start_date",
                "end_date",
                "instructions",
                "is_active",
            }
        ),
        "condition": frozenset({"name", "icd10_code", "status", "notes"}),
        "allergy": frozenset({"allergen", "reaction", "severity"}),
    }

    def __init__(self, db: Client) -> None:
        self.db = db

    def preview(self, *, fact_id: UUID, patient_id: UUID) -> dict[str, Any]:
        fact = self._fact(fact_id=fact_id, patient_id=patient_id)
        candidate = self._candidate_fields(fact)
        fact_type = str(fact["fact_type"])
        matches = self._matches(fact=fact, candidate=candidate)
        return {
            "fact_id": str(fact_id),
            "fact_type": fact_type,
            "projectable": fact_type in self.PROJECTABLE_FACT_TYPES,
            "candidate_fields": candidate,
            "available_fields": sorted(candidate),
            "matches": matches,
        }

    def decide(
        self,
        *,
        fact_id: UUID,
        patient_id: UUID,
        actor_id: UUID,
        request: ReconciliationDecisionRequest,
    ) -> dict[str, Any]:
        fact = self._fact(fact_id=fact_id, patient_id=patient_id)
        if fact.get("review_state") != "pending_review":
            raise ValidationError("Only pending imported facts can be reconciled")
        if fact.get("reconciliation_state") not in {None, "not_started", "deferred"}:
            raise ValidationError("Reconciled clinical facts are immutable evidence")

        fact_type = str(fact["fact_type"])
        projectable = fact_type in self.PROJECTABLE_FACT_TYPES
        if request.decision in {ReconciliationDecision.ADD, ReconciliationDecision.UPDATE}:
            if not projectable:
                raise ValidationError(
                    "This external record is evidence-only and cannot change local truth"
                )
            self._require_external_binding_if_fhir(fact=fact, patient_id=patient_id)
        elif request.decision is ReconciliationDecision.MARK_REVIEWED and projectable:
            raise ValidationError(
                "Use add, update, keep existing, defer, or reject for a projectable fact"
            )

        candidate = self._candidate_fields(fact)
        allowed = self._FIELDS.get(fact_type, frozenset())
        selected = set(request.selected_fields)
        if not selected.issubset(allowed):
            raise ValidationError("Selected fields are not allowed for this candidate type")
        if request.decision is ReconciliationDecision.ADD:
            selected = set(candidate)
        patch = {field: candidate[field] for field in selected if field in candidate}
        if (
            request.decision in {ReconciliationDecision.ADD, ReconciliationDecision.UPDATE}
            and not patch
        ):
            raise ValidationError("No selected candidate fields can be applied")

        result = self.db.rpc(
            "apply_clinical_fact_reconciliation",
            {
                "p_fact_id": str(fact_id),
                "p_actor_id": str(actor_id),
                "p_decision": request.decision.value,
                "p_target_id": str(request.target_id) if request.target_id else None,
                "p_patch": patch,
                "p_selected_fields": sorted(selected),
                "p_note": request.note.strip() if request.note else None,
                "p_idempotency_key": str(request.idempotency_key),
            },
        ).execute()
        data = result.data
        if isinstance(data, list):
            data = data[0] if data else None
        if not isinstance(data, dict):
            raise ValidationError("Could not record reconciliation decision")
        return data

    def _require_external_binding_if_fhir(self, *, fact: dict[str, Any], patient_id: UUID) -> None:
        """Require explicit identity confirmation before a FHIR fact changes a chart."""
        citations = cast(
            list[dict[str, Any]],
            self.db.table("evidence_citations")
            .select("provenance_id")
            .eq("fact_id", str(fact["id"]))
            .execute()
            .data
            or [],
        )
        provenance_ids = [
            str(item["provenance_id"]) for item in citations if item.get("provenance_id")
        ]
        if not provenance_ids:
            return
        provenance = cast(
            list[dict[str, Any]],
            self.db.table("source_provenances")
            .select("source_reference")
            .in_("id", provenance_ids)
            .execute()
            .data
            or [],
        )
        resource_ids = [
            str(item["source_reference"]).removeprefix("fhir_import_resources/")
            for item in provenance
            if isinstance(item.get("source_reference"), str)
            and str(item["source_reference"]).startswith("fhir_import_resources/")
        ]
        if not resource_ids:
            return
        resource = cast(
            list[dict[str, Any]],
            self.db.table("fhir_import_resources")
            .select("import_id")
            .in_("id", resource_ids)
            .limit(1)
            .execute()
            .data
            or [],
        )
        if resource:
            ExternalPatientBindingService(self.db).assert_import_bound(
                import_id=UUID(str(resource[0]["import_id"])), patient_id=patient_id
            )

    def _fact(self, *, fact_id: UUID, patient_id: UUID) -> dict[str, Any]:
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

    def _matches(self, *, fact: dict[str, Any], candidate: dict[str, Any]) -> list[dict[str, Any]]:
        fact_type = str(fact["fact_type"])
        if fact_type not in self.PROJECTABLE_FACT_TYPES:
            return []
        patient_id = str(fact["patient_id"])
        table_name = self._TARGET_TABLE[fact_type]
        rows = cast(
            list[dict[str, Any]],
            self.db.table(table_name).select("*").eq("patient_id", patient_id).execute().data or [],
        )

        prior = self._prior_external_match(fact=fact, table_name=table_name)
        if prior:
            return [
                {
                    "target_type": fact_type,
                    "target_id": str(prior["id"]),
                    "match_reason": "Previously reconciled version of this external resource",
                    "record": prior,
                }
            ]

        matches: list[dict[str, Any]] = []
        for row in rows:
            reason = self._match_reason(fact_type=fact_type, candidate=candidate, record=row)
            if reason:
                matches.append(
                    {
                        "target_type": fact_type,
                        "target_id": str(row["id"]),
                        "match_reason": reason,
                        "record": row,
                    }
                )
        return matches

    def _prior_external_match(
        self, *, fact: dict[str, Any], table_name: str
    ) -> dict[str, Any] | None:
        source_key = fact.get("external_source_key")
        if not source_key:
            return None
        result = (
            self.db.table("clinical_facts")
            .select("reconciliation_target_id, reconciliation_target_type")
            .eq("patient_id", str(fact["patient_id"]))
            .eq("external_source_key", str(source_key))
            .execute()
        )
        links = cast(list[dict[str, Any]], result.data or [])
        target_id = next(
            (
                str(link["reconciliation_target_id"])
                for link in links
                if link.get("reconciliation_target_type") == str(fact["fact_type"])
                and link.get("reconciliation_target_id")
            ),
            None,
        )
        if not target_id:
            return None
        target = (
            self.db.table(table_name)
            .select("*")
            .eq("id", target_id)
            .eq("patient_id", str(fact["patient_id"]))
            .single()
            .execute()
            .data
        )
        return cast(dict[str, Any] | None, target)

    @staticmethod
    def _normal(value: Any) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip().lower())

    def _match_reason(
        self, *, fact_type: str, candidate: dict[str, Any], record: dict[str, Any]
    ) -> str | None:
        if fact_type == "medication":
            if candidate.get("rxcui") and candidate.get("rxcui") == record.get("rxcui"):
                return "Exact RxNorm concept"
            if self._normal(candidate.get("name")) == self._normal(record.get("name")):
                return "Normalized medication name"
            if candidate.get("generic_name") and self._normal(
                candidate.get("generic_name")
            ) == self._normal(record.get("generic_name")):
                return "Normalized generic name"
        elif fact_type == "condition":
            if candidate.get("icd10_code") and candidate.get("icd10_code") == record.get(
                "icd10_code"
            ):
                return "Exact ICD-10 code"
            if self._normal(candidate.get("name")) == self._normal(record.get("name")):
                return "Normalized condition name"
        elif fact_type == "allergy" and self._normal(candidate.get("allergen")) == self._normal(
            record.get("allergen")
        ):
            candidate_reaction = self._normal(candidate.get("reaction"))
            local_reaction = self._normal(record.get("reaction"))
            if candidate_reaction and local_reaction and candidate_reaction != local_reaction:
                return "Normalized allergen; reaction differs (review conflict)"
            return "Normalized allergen"
        return None

    def _candidate_fields(self, fact: dict[str, Any]) -> dict[str, Any]:
        value = cast(dict[str, Any], fact.get("value") or {})
        fact_type = str(fact["fact_type"])
        if fact_type == "medication":
            dosage = value.get("dosage")
            if isinstance(dosage, list):
                dosage = "; ".join(str(item) for item in dosage if item)
            candidate = {
                "name": value.get("name"),
                "generic_name": value.get("generic_name"),
                "rxcui": value.get("rxcui"),
                "dosage": dosage,
                "frequency": value.get("frequency"),
                "route": value.get("route"),
                "start_date": value.get("start_date"),
                "end_date": value.get("end_date"),
                "instructions": value.get("instructions"),
                "is_active": value.get("is_active"),
            }
        elif fact_type == "condition":
            candidate = {
                "name": value.get("name"),
                "icd10_code": value.get("icd10_code"),
                "status": value.get("status") or value.get("clinical_status"),
                "notes": value.get("notes"),
            }
        elif fact_type == "allergy":
            reactions = value.get("reactions")
            reaction = value.get("reaction")
            if not reaction and isinstance(reactions, list):
                reaction = "; ".join(str(item) for item in reactions if item)
            candidate = {
                "allergen": value.get("allergen"),
                "reaction": reaction,
                "severity": value.get("severity"),
            }
        else:
            return {}
        return {key: item for key, item in candidate.items() if item not in (None, "", [])}
