"""Review eligibility for document-backed care-plan evidence, not parsing."""

from typing import Any, cast
from uuid import UUID

from supabase import Client


def eligible_fact_ids(db: Client, patient_id: UUID, fact_ids: list[str]) -> set[str]:
    """Require a local source and reject any unaccepted document citation."""
    if not fact_ids:
        return set()
    citations = cast(
        list[dict[str, Any]],
        db.table("evidence_citations")
        .select("fact_id, source_provenances!inner(artifact_type, document_id, withdrawn_at)")
        .in_("fact_id", fact_ids)
        .execute()
        .data
        or [],
    )
    document_ids = list(
        {
            str(source["document_id"])
            for row in citations
            if (source := row.get("source_provenances")) and source.get("document_id")
        }
    )
    documents = (
        cast(
            list[dict[str, Any]],
            db.table("documents")
            .select("id, uploaded_by_role, review_status")
            .eq("patient_id", str(patient_id))
            .in_("id", document_ids)
            .execute()
            .data
            or [],
        )
        if document_ids
        else []
    )
    accepted = {
        str(doc["id"])
        for doc in documents
        if doc.get("uploaded_by_role") == "clinician"
        or (doc.get("uploaded_by_role") == "patient" and doc.get("review_status") == "approved")
    }
    eligible: set[str] = set()
    blocked: set[str] = set()
    for row in citations:
        source = row.get("source_provenances") or {}
        fact_id = str(row["fact_id"])
        if source.get("artifact_type") == "document":
            if source.get("withdrawn_at") or str(source.get("document_id")) not in accepted:
                blocked.add(fact_id)
            else:
                eligible.add(fact_id)
        elif source.get("artifact_type") == "clinician_entry" and not source.get("withdrawn_at"):
            eligible.add(fact_id)
    return eligible - blocked
