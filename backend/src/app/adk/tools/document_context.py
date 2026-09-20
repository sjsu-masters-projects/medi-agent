"""Expose a server-selected document summary to the Care Coordinator.

The model cannot supply a document identifier. The websocket route first verifies
document ownership, then places a small, already patient-facing summary in temporary
session state for this turn. This tool only reads that server-populated state.
"""

from __future__ import annotations

from typing import Any

from app.adk.tools.scoping import (
    DOCUMENT_CONTEXT_STATE_KEY,
    PatientScopeError,
    require_patient_id,
)


def get_active_document_context(tool_context: Any) -> dict[str, Any]:
    """Return the selected document's bounded summary for this chat turn.

    The current patient is still required even though no query occurs here. That
    prevents an accidentally unscoped agent invocation from treating arbitrary
    session state as clinical context.

    Args:
        tool_context: Supplied by the runtime; not part of the model's request.
    """
    try:
        require_patient_id(tool_context)
    except PatientScopeError:
        return {"error": "No patient record is available in this conversation."}

    state = getattr(tool_context, "state", None)
    context = None if state is None else state.get(DOCUMENT_CONTEXT_STATE_KEY)
    if not isinstance(context, dict):
        return {"error": "No document is selected for this conversation."}

    document_id = str(context.get("id") or "").strip()
    file_name = str(context.get("file_name") or "").strip()
    summary = str(context.get("summary") or "").strip()
    parse_status = str(context.get("parse_status") or "none").strip()
    if not document_id or not file_name:
        return {"error": "The selected document context is unavailable."}
    if not summary:
        return {
            "document_id": document_id,
            "file_name": file_name,
            "document_type": str(context.get("document_type") or "other"),
            "summary": "",
            "parse_status": parse_status,
            "notice": "The selected document does not have a usable summary yet.",
        }

    return {
        "document_id": document_id,
        "file_name": file_name,
        "document_type": str(context.get("document_type") or "other"),
        "summary": summary,
        "parse_status": parse_status,
    }
