"""FHIR R4B representations of local clinical-fact provenance and audit history.

These resources are generated on demand from the immutable local lineage and
audit records. They are not written back to an external FHIR server and never
carry private reasoning, clinical-fact values, or reviewer notes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from fhir.resources.R4B.auditevent import AuditEvent
from fhir.resources.R4B.provenance import Provenance
from supabase import Client

from app.services.clinical_fact_service import ClinicalFactService

_FACT_IDENTIFIER_SYSTEM = "urn:mediagent:clinical-fact"
_AUDIT_SUBTYPE_SYSTEM = "urn:mediagent:clinical-fact-audit"
_AUDIT_EVENT_TYPE_SYSTEM = "http://terminology.hl7.org/CodeSystem/audit-event-type"
_AUDIT_EVENT_TYPE_CODE = "110110"
_OBSERVER_REFERENCE = "Device/mediagent-backend"
_AUDIT_ACTIONS = {
    "created": "C",
    "corrected": "U",
    "approved": "U",
    "rejected": "U",
    "deleted": "D",
}


class FhirAuditExportService:
    """Expose the existing review trail as validated, read-only FHIR resources."""

    def __init__(self, db: Client) -> None:
        self.db = db
        self.facts = ClinicalFactService(db)

    def export_for_fact(self, *, fact_id: UUID, patient_id: UUID) -> dict[str, Any]:
        """Build one Provenance and ordered AuditEvents for a local candidate fact."""
        lineage = self.facts.get_lineage(fact_id, patient_id)
        fact = cast(dict[str, Any], lineage["fact"])
        provenances = cast(list[dict[str, Any]], lineage["provenances"])
        target = self._fact_reference(fact_id)

        provenance = Provenance.model_validate(
            {
                "resourceType": "Provenance",
                "target": [target],
                "recorded": self._instant(fact["created_at"]),
                "agent": [{"who": {"reference": _OBSERVER_REFERENCE}}],
                "entity": [self._source_entity(source) for source in provenances],
            }
        ).model_dump(mode="json", exclude_none=True)

        audit_rows = self._audit_rows(fact_id)
        audit_events = [
            AuditEvent.model_validate(self._audit_payload(event, target)).model_dump(
                mode="json", exclude_none=True
            )
            for event in audit_rows
        ]
        return {"provenance": provenance, "audit_events": audit_events}

    def _audit_rows(self, fact_id: UUID) -> list[dict[str, Any]]:
        result = (
            self.db.table("clinical_fact_audit_events")
            .select("*")
            .eq("fact_id", str(fact_id))
            .order("created_at")
            .execute()
        )
        return cast(list[dict[str, Any]], result.data or [])

    @staticmethod
    def _fact_reference(fact_id: UUID) -> dict[str, Any]:
        return {"identifier": {"system": _FACT_IDENTIFIER_SYSTEM, "value": str(fact_id)}}

    def _source_entity(self, source: dict[str, Any]) -> dict[str, Any]:
        imported_reference = self._imported_fhir_reference(source)
        if imported_reference:
            return {"role": "source", "what": imported_reference}
        if source.get("document_id"):
            source_reference: dict[str, Any] = {
                "reference": f"DocumentReference/{source['document_id']}"
            }
        else:
            identifier: dict[str, Any] = {"value": str(source["source_reference"])}
            source_system = str(source.get("source_system") or "")
            if source_system.startswith(("https://", "http://", "urn:")):
                identifier["system"] = source_system
            source_reference = {"identifier": identifier}
        return {"role": "source", "what": source_reference}

    def _imported_fhir_reference(self, source: dict[str, Any]) -> dict[str, Any] | None:
        """Prefer the original versioned FHIR resource over an internal envelope id."""
        if source.get("artifact_type") != "fhir_resource":
            return None
        prefix = "fhir_import_resources/"
        source_reference = str(source.get("source_reference") or "")
        if not source_reference.startswith(prefix):
            return None
        resource_id = source_reference.removeprefix(prefix)
        result = (
            self.db.table("fhir_import_resources")
            .select("resource_type, external_resource_id, version_id, issuer, content_hash")
            .eq("id", resource_id)
            .single()
            .execute()
        )
        imported = cast(dict[str, Any] | None, result.data)
        if not imported:
            return None
        resource_type = str(imported.get("resource_type") or "")
        external_id = str(imported.get("external_resource_id") or "")
        if resource_type and external_id:
            reference = f"{resource_type}/{external_id}"
            version_id = str(imported.get("version_id") or "")
            if version_id:
                reference = f"{reference}/_history/{version_id}"
            return {"reference": reference}
        identifier: dict[str, Any] = {"value": str(imported.get("content_hash") or resource_id)}
        issuer = str(imported.get("issuer") or "")
        if issuer.startswith(("https://", "http://", "urn:")):
            identifier["system"] = issuer
        return {"identifier": identifier}

    @staticmethod
    def _audit_payload(event: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
        event_type = str(event["event_type"])
        return {
            "resourceType": "AuditEvent",
            "type": {"system": _AUDIT_EVENT_TYPE_SYSTEM, "code": _AUDIT_EVENT_TYPE_CODE},
            "subtype": [{"system": _AUDIT_SUBTYPE_SYSTEM, "code": event_type}],
            "action": _AUDIT_ACTIONS[event_type],
            "recorded": FhirAuditExportService._instant(event["created_at"]),
            "outcome": "0",
            "agent": [
                {
                    "who": {"reference": f"Practitioner/{event['actor_id']}"},
                    "requestor": True,
                }
            ],
            "source": {"observer": {"reference": _OBSERVER_REFERENCE}},
            "entity": [{"what": target}],
        }

    @staticmethod
    def _instant(value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)
