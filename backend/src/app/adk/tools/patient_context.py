"""Read the current patient's own clinical context.

**The patient is never an argument.** It is resolved from authenticated session state by
`require_patient_id`, so the declaration the model sees carries no patient identifier at
all — ADK strips framework-injected parameters like `tool_context` from the schema. A
model that cannot name a patient cannot name the wrong one.

That matters more here than it looks: this reads through the service-role client, which
bypasses the `auth.uid()`-based row-level security in migration 002. There is no database
filter behind this function, so the `patient_id` it passes to the query *is* the boundary.
"""

from __future__ import annotations

import logging
from typing import Any

from app.adk.tools.scoping import PatientScopeError, require_patient_id
from app.clients.supabase import get_admin_client
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)


def _service(db: Any | None = None) -> ChatService:
    """Build the context reader. Injectable so a test can prove what it was asked for."""
    return ChatService(db if db is not None else get_admin_client())


async def get_patient_context(tool_context: Any) -> dict[str, Any]:
    """Get this patient's active medications, conditions, recent symptoms and care team.

    Use this before answering anything that depends on what the patient is taking or
    being treated for. It returns only this patient's own record.

    Args:
        tool_context: Supplied by the runtime; not part of the model's request.
    """
    try:
        patient_id = require_patient_id(tool_context)
    except PatientScopeError as error:
        # Surfaced as a readable result rather than an exception: the model should say it
        # cannot see the record, not have its turn ended by a stack trace.
        logger.warning("Refused a patient-context read: %s", error)
        return {"error": "No patient record is available in this conversation."}

    context = await _service().get_context(patient_id)

    # Deliberately reshaped rather than returned verbatim: `get_context` also carries a
    # pre-attached `document` blob for the chat route, which is not this tool's concern
    # and would put document text into a context read the model did not ask for.
    return {
        "medications": context.get("medications", []),
        "conditions": context.get("conditions", []),
        "recent_symptoms": context.get("recent_symptoms", []),
        "care_teams": context.get("care_teams", []),
    }
