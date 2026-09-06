"""Clinician-facing review reads for provenance-backed SMART candidates."""

from __future__ import annotations

from collections import Counter
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.models.clinical_fact import ClinicalFactReviewState


class FhirImportReviewService:
    """Read external candidates without changing their clinical review state."""

    _FHIR_ENVELOPE_PREFIX = "fhir_import_resources/"

    def __init__(self, db: Client) -> None:
        self.db = db

    def list_facts(
        self,
        *,
        patient_id: UUID,
        review_state: ClinicalFactReviewState,
        fact_type: str | None,
        source_kind: str | None = None,
        reconciliation_state: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        offset: int,
        limit: int,
    ) -> dict[str, Any]:
        """Return one page of SMART and document candidates with source labels."""
        metadata_result = (
            self.db.table("clinical_facts")
            .select("id, fact_type, review_state, reconciliation_state, created_at")
            .eq("patient_id", str(patient_id))
            .execute()
        )
        metadata = cast(list[dict[str, Any]], metadata_result.data or [])
        sources = self._sources_for_facts(metadata)
        visible_metadata = []
        for row in metadata:
            source = sources.get(str(row.get("id")))
            if row.get("review_state") == ClinicalFactReviewState.DELETED.value or not source:
                continue
            if source_kind and source.get("source_kind") != source_kind:
                continue
            if reconciliation_state and row.get("reconciliation_state") != reconciliation_state:
                continue
            created_at = str(row.get("created_at") or "")
            if from_date and created_at[:10] < from_date:
                continue
            if to_date and created_at[:10] > to_date:
                continue
            visible_metadata.append(row)
        state_counts = Counter(str(row.get("review_state", "unknown")) for row in visible_metadata)
        fact_type_counts = Counter(str(row.get("fact_type", "unknown")) for row in visible_metadata)
        eligible_ids = [
            str(row["id"])
            for row in visible_metadata
            if row.get("review_state") == review_state.value
            and (fact_type is None or row.get("fact_type") == fact_type)
            and row.get("id")
        ]

        if not eligible_ids:
            return {
                "patient_id": str(patient_id),
                "review_state": review_state.value,
                "fact_type": fact_type,
                "facts": [],
                "total_count": 0,
                "state_counts": dict(state_counts),
                "fact_type_counts": dict(fact_type_counts),
                "offset": offset,
                "limit": limit,
            }

        page_result = (
            self.db.table("clinical_facts")
            .select("*")
            .eq("patient_id", str(patient_id))
            .eq("review_state", review_state.value)
            .in_("id", eligible_ids)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        facts = cast(list[dict[str, Any]], page_result.data or [])

        return {
            "patient_id": str(patient_id),
            "review_state": review_state.value,
            "fact_type": fact_type,
            "facts": [{**fact, "source": sources.get(str(fact.get("id")))} for fact in facts],
            "total_count": len(eligible_ids),
            "state_counts": dict(state_counts),
            "fact_type_counts": dict(fact_type_counts),
            "offset": offset,
            "limit": limit,
        }

    def _sources_for_facts(self, facts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        fact_ids = [str(row["id"]) for row in facts if row.get("id")]
        if not fact_ids:
            return {}
        citations_result = (
            self.db.table("evidence_citations")
            .select("fact_id, provenance_id")
            .in_("fact_id", fact_ids)
            .execute()
        )
        citations = cast(list[dict[str, Any]], citations_result.data or [])
        provenance_by_fact = {
            str(row["fact_id"]): str(row["provenance_id"])
            for row in citations
            if row.get("fact_id") and row.get("provenance_id")
        }
        provenance_ids = sorted(set(provenance_by_fact.values()))
        if not provenance_ids:
            return {}
        provenance_result = (
            self.db.table("source_provenances")
            .select(
                "id, source_system, source_reference, document_id, document_location, extractor_version"
            )
            .in_("id", provenance_ids)
            .execute()
        )
        provenances = cast(list[dict[str, Any]], provenance_result.data or [])
        provenance_by_id = {str(row["id"]): row for row in provenances if row.get("id")}
        envelope_ids = sorted(
            {
                str(row["source_reference"])[len(self._FHIR_ENVELOPE_PREFIX) :]
                for row in provenances
                if isinstance(row.get("source_reference"), str)
                and str(row["source_reference"]).startswith(self._FHIR_ENVELOPE_PREFIX)
            }
        )
        envelopes: list[dict[str, Any]] = []
        if envelope_ids:
            envelope_result = (
                self.db.table("fhir_import_resources")
                .select(
                    "id, import_id, issuer, resource_type, external_resource_id, version_id, mapping_warnings, validation_errors"
                )
                .in_("id", envelope_ids)
                .execute()
            )
            envelopes = cast(list[dict[str, Any]], envelope_result.data or [])
        envelope_by_id = {str(row["id"]): row for row in envelopes if row.get("id")}

        result: dict[str, dict[str, Any]] = {}
        for fact_id, provenance_id in provenance_by_fact.items():
            provenance = provenance_by_id.get(provenance_id)
            if not provenance:
                continue
            source_reference = provenance.get("source_reference")
            if isinstance(source_reference, str) and source_reference.startswith(
                self._FHIR_ENVELOPE_PREFIX
            ):
                envelope = envelope_by_id.get(source_reference[len(self._FHIR_ENVELOPE_PREFIX) :])
                if envelope:
                    result[fact_id] = {
                        "issuer": envelope.get("issuer") or provenance.get("source_system"),
                        "resource_type": envelope.get("resource_type") or "FHIR resource",
                        "external_resource_id": envelope.get("external_resource_id"),
                        "version_id": envelope.get("version_id"),
                        "mapping_warnings": envelope.get("mapping_warnings") or [],
                        "validation_errors": envelope.get("validation_errors") or [],
                        "source_kind": "smart",
                        "import_id": envelope.get("import_id"),
                    }
                continue
            if provenance.get("document_id"):
                result[fact_id] = {
                    "issuer": provenance.get("source_system") or "document ingestion",
                    "resource_type": "Document evidence",
                    "external_resource_id": provenance.get("document_id"),
                    "version_id": provenance.get("extractor_version"),
                    "mapping_warnings": [],
                    "validation_errors": [],
                    "source_kind": "document",
                }
        return result

    def get_source(self, *, fact_id: UUID, patient_id: UUID) -> dict[str, Any] | None:
        """Return the authorized original FHIR envelope or document evidence descriptor."""
        fact_result = (
            self.db.table("clinical_facts")
            .select("id")
            .eq("id", str(fact_id))
            .eq("patient_id", str(patient_id))
            .single()
            .execute()
        )
        if not fact_result.data:
            return None
        citation_result = (
            self.db.table("evidence_citations")
            .select("provenance_id")
            .eq("fact_id", str(fact_id))
            .execute()
        )
        citations = cast(list[dict[str, Any]], citation_result.data or [])
        provenance_id = next(
            (str(row["provenance_id"]) for row in citations if row.get("provenance_id")), None
        )
        if provenance_id is None:
            return None
        provenance_result = (
            self.db.table("source_provenances")
            .select(
                "source_system, source_reference, document_id, document_location, extractor_version"
            )
            .eq("id", provenance_id)
            .single()
            .execute()
        )
        provenance = cast(dict[str, Any] | None, provenance_result.data)
        if provenance is None:
            return None
        source_reference = provenance.get("source_reference")
        if not isinstance(source_reference, str) or not source_reference.startswith(
            self._FHIR_ENVELOPE_PREFIX
        ):
            return {
                "issuer": provenance.get("source_system") or "document ingestion",
                "resource_type": "Document evidence",
                "external_resource_id": provenance.get("document_id"),
                "version_id": provenance.get("extractor_version"),
                "mapping_warnings": [],
                "validation_errors": [],
                "source_kind": "document",
                "raw_resource": {
                    "resourceType": "DocumentEvidence",
                    "source_reference": source_reference,
                    "location": provenance.get("document_location") or {},
                },
            }
        envelope_result = (
            self.db.table("fhir_import_resources")
            .select(
                "import_id, issuer, resource_type, external_resource_id, version_id, mapping_warnings, validation_errors, raw_resource"
            )
            .eq("id", source_reference[len(self._FHIR_ENVELOPE_PREFIX) :])
            .single()
            .execute()
        )
        envelope = cast(dict[str, Any] | None, envelope_result.data)
        if not envelope:
            return None
        return {
            "issuer": envelope.get("issuer") or provenance.get("source_system"),
            "resource_type": envelope.get("resource_type") or "FHIR resource",
            "external_resource_id": envelope.get("external_resource_id"),
            "version_id": envelope.get("version_id"),
            "mapping_warnings": envelope.get("mapping_warnings") or [],
            "validation_errors": envelope.get("validation_errors") or [],
            "source_kind": "smart",
            "import_id": envelope.get("import_id"),
            "raw_resource": envelope.get("raw_resource") or {},
        }
