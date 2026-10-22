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
from app.services.smart_launch_service import SmartLaunchService


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
        medication = fact_type == "medication"
        return {
            "fact_id": str(fact_id),
            "fact_type": fact_type,
            "projectable": self._is_projectable(fact),
            "candidate_fields": candidate,
            "available_fields": sorted(candidate),
            "matches": matches,
            "review_flags": self._medication_review_flags(fact, candidate, matches)
            if medication
            else [],
            "safety_coverage": (
                "Source text/name comparisons only. Drug interactions and therapeutic equivalence "
                "are not checked. No matching flag does not establish safety."
                if medication
                else None
            ),
        }

    def _medication_review_flags(
        self, fact: dict[str, Any], candidate: dict[str, Any], matches: list[dict[str, Any]]
    ) -> list[str]:
        """Conservative source differences, never clinical equivalence or advice."""
        flags = []
        if not matches:
            flags.append(
                "No matching local medication was found. Review identity before adding; the approved list is unchanged."
            )
        if len(matches) > 1:
            flags.append(
                "Multiple possible local matches. Review possible duplication; do not merge records automatically."
            )
        for match in matches:
            record = match["record"]
            if (
                candidate.get("rxcui")
                and record.get("rxcui")
                and candidate["rxcui"] != record["rxcui"]
            ):
                flags.append(
                    "Recorded RxNorm concepts differ. A name match does not verify ingredient, formulation or therapeutic equivalence."
                )
            for field in ("dosage", "frequency", "route", "is_active"):
                if field not in candidate or record.get(field) is None:
                    continue
                if self._normal(str(candidate[field])) != self._normal(str(record[field])):
                    label = "active status" if field == "is_active" else field
                    message = f"Recorded {label} differs between the source and a possible local match. Review the side-by-side values."
                    if message not in flags:
                        flags.append(message)
        names = {
            self._normal(str(candidate[key]))
            for key in ("name", "generic_name")
            if candidate.get(key)
        }
        allergies = cast(
            list[dict[str, Any]],
            self.db.table("allergies")
            .select("allergen")
            .eq("patient_id", str(fact["patient_id"]))
            .execute()
            .data
            or [],
        )
        if any(self._normal(str(row.get("allergen") or "")) in names for row in allergies):
            flags.append(
                "A recorded allergen name matches this candidate's recorded name. Clinician review is required; this is not a confirmed allergy assessment."
            )
        return flags

    def decide(
        self,
        *,
        fact_id: UUID,
        patient_id: UUID,
        actor_id: UUID,
        request: ReconciliationDecisionRequest,
    ) -> dict[str, Any]:
        fact = self._fact(fact_id=fact_id, patient_id=patient_id)
        replay = self._existing_decision(
            fact_id=fact_id, patient_id=patient_id, actor_id=actor_id, request=request
        )
        if replay is not None:
            return replay
        if fact.get("review_state") != "pending_review":
            raise ValidationError("Only pending imported facts can be reconciled")
        if fact.get("reconciliation_state") not in {None, "not_started", "deferred"}:
            raise ValidationError("Reconciled clinical facts are immutable evidence")

        fact_type = str(fact["fact_type"])
        projectable = self._is_projectable(fact)
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

    def _existing_decision(
        self,
        *,
        fact_id: UUID,
        patient_id: UUID,
        actor_id: UUID,
        request: ReconciliationDecisionRequest,
    ) -> dict[str, Any] | None:
        """Recover a committed decision after a lost response, before lifecycle guards."""
        rows = (
            self.db.table("clinical_fact_reconciliation_events")
            .select("*")
            .eq("fact_id", str(fact_id))
            .eq("patient_id", str(patient_id))
            .eq("actor_id", str(actor_id))
            .eq("idempotency_key", str(request.idempotency_key))
            .execute()
            .data
        )
        if not isinstance(rows, list) or not rows:
            return None
        # A committed decision is immutable, but its actor's access can be revoked.
        # Reuse the route's current-assignment gate before returning any snapshot.
        authorization = SmartLaunchService(self.db)
        with authorization.http:
            authorization.ensure_assignment(clinician_id=actor_id, patient_id=patient_id)
        event = cast(dict[str, Any], rows[0])
        if (
            event["decision"] != request.decision.value
            or (event.get("note") or None)
            != ((request.note.strip() or None) if request.note else None)
            or (
                request.decision is ReconciliationDecision.UPDATE
                and (
                    str(event.get("target_id")) != str(request.target_id)
                    or sorted(event["selected_fields"]) != sorted(set(request.selected_fields))
                )
            )
        ):
            raise ValidationError("Idempotency key belongs to another reconciliation decision")
        return {
            "fact_id": event["fact_id"],
            "event_id": event["id"],
            "decision": event["decision"],
            "target_type": event.get("target_type"),
            "target_id": event.get("target_id"),
            "target_before": event.get("target_before"),
            "target_after": event.get("target_after"),
            "replayed": True,
        }

    @classmethod
    def _is_projectable(cls, fact: dict[str, Any]) -> bool:
        # Exact absence statements remain reviewable source evidence. Do not
        # infer negation from substrings in names or mixed clinical narratives.
        if fact["fact_type"] == "allergy":
            allergen = (fact.get("value") or {}).get("allergen")
            if cls._normal(allergen) in {
                "nkda",
                "nka",
                "no known allergies",
                "no known drug allergies",
                "sin alergias conocidas",
                "sin alergias medicamentosas conocidas",
            }:
                return False
        return fact["fact_type"] in cls.PROJECTABLE_FACT_TYPES

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
        if not self._is_projectable(fact):
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

    @classmethod
    def _medication_name_key(cls, value: Any) -> str:
        """Potential name identity only; preserve ER/IR, salts and combinations."""
        name = cls._normal(value)
        name = re.sub(r"\s+\d+(?:\.\d+)?\s*(?:mcg|mg|g|ml|units?)(?=\s|$)", "", name)
        name = re.sub(r"\s+(?:tablets?|capsules?)$", "", name)
        return cls._normal(name)

    def _match_reason(
        self, *, fact_type: str, candidate: dict[str, Any], record: dict[str, Any]
    ) -> str | None:
        if fact_type == "medication":
            if candidate.get("rxcui") and candidate.get("rxcui") == record.get("rxcui"):
                return "Exact RxNorm concept"
            if (
                candidate.get("name")
                and record.get("name")
                and self._normal(candidate["name"]) == self._normal(record["name"])
            ):
                return "Normalized medication name"
            if candidate.get("generic_name") and self._normal(
                candidate.get("generic_name")
            ) == self._normal(record.get("generic_name")):
                return "Normalized generic name"
            candidate_key = self._medication_name_key(candidate.get("name"))
            if candidate_key and candidate_key == self._medication_name_key(record.get("name")):
                return "Possible name match ignoring strength/form text — verify ingredient, dose and formulation"
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
        if not self._is_projectable(fact):
            return {}
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
