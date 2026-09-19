"""Decide whose records a tool may read — from the session, never from the model.

**This is the only thing protecting patient rows from a tool.** Row-level security does
not help here: every policy in migration 002 is written against `auth.uid()`
(`patients_own_select ... USING (id = auth.uid())`), and tools run with the service-role
client, which has no `auth.uid()` and bypasses RLS by design. Routers are safe because
FastAPI authenticates first and `_ensure_chat_access` refuses a patient reading another
patient. A tool has none of that: no request, no `CurrentUser`, no dependency chain. Its
caller is a model.

So the patient is read from authenticated session state and nowhere else. No tool takes a
patient identifier as an argument, because an argument is something a model can choose —
and a model that can name the patient can name a different one. `require_patient_id` is
deliberately single-argument for exactly that reason, and a test pins the signature.

Absence raises rather than defaulting. A tool that quietly reads "no patient" would either
return nothing (confusing) or, with a permissive query, return everyone's rows.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

PATIENT_ID_STATE_KEY = "patient_id"
"""Session-state key naming the patient this conversation is about.

Durable rather than `temp:`-scoped: the subject of a conversation is a property of the
whole session, not of one turn, and every tool on every turn must resolve the same person.
"""


class PatientScopeError(RuntimeError):
    """A tool tried to read patient data without an authenticated patient in scope."""


def require_patient_id(tool_context: Any) -> str:
    """Return the patient this session is about, or raise.

    Takes only the tool context. There is no parameter a model could supply, override or
    be prompt-injected into supplying — the identifier is not part of the tool's surface.
    """
    state = getattr(tool_context, "state", None)
    raw = None if state is None else state.get(PATIENT_ID_STATE_KEY)

    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise PatientScopeError(
            "No authenticated patient is in session scope; refusing to read patient data."
        )

    try:
        # Validated rather than passed through: a malformed identifier reaching a query
        # is how a filter silently stops filtering.
        return str(UUID(str(raw).strip()))
    except (ValueError, AttributeError, TypeError) as error:
        # The value itself is never logged. It arrived claiming to identify a patient, and
        # a log store has weaker access control than the database it was headed for.
        logger.error("Patient identifier in session scope is not a UUID; refusing the read")
        raise PatientScopeError(
            "The patient identifier in session scope is not a valid UUID."
        ) from error
