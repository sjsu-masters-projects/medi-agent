"""Persist refused access attempts.

Called from the 403 exception handler, so every `AuthorizationError` raised anywhere in
the application produces a record without each raise site having to remember to write
one.

A failure to audit must never change what the caller sees: the request was correctly
refused, and turning that 403 into a 500 would both leak that something unusual happened
and break a working denial. Failures are swallowed and logged at ERROR so they surface in
Sentry and alerting instead.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from app.clients.supabase import get_admin_client
from app.core.authorization_reasons import NO_CARE_TEAM_ASSIGNMENT, UNSPECIFIED
from app.services.authorization_denial_classifier import classify_care_team_denial

logger = logging.getLogger(__name__)

_TABLE = "authorization_denial_events"

# A denial response must not wait on the audit write. The bound is generous enough for a
# healthy insert and short enough that a stalled database cannot hold the response open.
_AUDIT_TIMEOUT_SECONDS = 5.0


async def _insert_row(payload: dict[str, Any]) -> None:
    """Write one row. Separated so tests can substitute an in-memory sink."""
    client = get_admin_client()
    await asyncio.to_thread(client.table(_TABLE).insert(payload).execute)


async def _refine(
    reason_code: str,
    actor_id: str | None,
    target_type: str | None,
    target_id: str | None,
) -> str:
    """Sharpen a generic care-team denial into its specific variant.

    Done here rather than at the raise site for two reasons: the request path stays free
    of extra queries, and the refined code never travels back to the caller — knowing a
    denial was "cross-clinic" would confirm the patient exists in another clinic.

    Any failure keeps the original code; a coarse record beats no record.
    """
    if reason_code != NO_CARE_TEAM_ASSIGNMENT:
        return reason_code
    if target_type != "patient" or not actor_id or not target_id:
        return reason_code
    try:
        return await classify_care_team_denial(get_admin_client(), actor_id, target_id)
    except Exception:
        logger.warning("Could not refine care-team denial reason", exc_info=True)
        return reason_code


def _coerce_uuid(value: str | None) -> str | None:
    """Return `value` only when it is a real UUID.

    A denial is frequently raised against whatever identifier the caller supplied, which
    may be malformed. The column is typed `uuid`, so a bad value would fail the insert
    and lose the record; drop the field instead and keep the event.
    """
    if not value:
        return None
    try:
        return str(UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        return None


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text[:limit] if len(text) > limit else text


async def record_denial(
    *,
    reason_code: str = UNSPECIFIED,
    actor_id: str | None = None,
    actor_role: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    request_method: str | None = None,
    request_path: str | None = None,
) -> bool:
    """Append one denial record. Returns True when the row was written.

    Never raises.
    """
    payload: dict[str, Any] = {
        "reason_code": _truncate(reason_code, 100) or UNSPECIFIED,
        "actor_id": _coerce_uuid(actor_id),
        "actor_role": _truncate(actor_role, 50),
        "target_type": _truncate(target_type, 50),
        "target_id": _coerce_uuid(target_id),
        "request_method": _truncate(request_method, 10),
        "request_path": _truncate(request_path, 2000),
    }

    async def _refine_then_write() -> None:
        # Refinement reads the database, so it shares the response's time budget rather
        # than adding a second unbounded wait in front of it.
        payload["reason_code"] = await _refine(
            payload["reason_code"],
            payload["actor_id"],
            payload["target_type"],
            payload["target_id"],
        )
        await _insert_row(payload)

    try:
        await asyncio.wait_for(_refine_then_write(), timeout=_AUDIT_TIMEOUT_SECONDS)
        return True
    except TimeoutError:
        logger.error(
            "Timed out auditing authorization denial after %ss (reason=%s actor=%s)",
            _AUDIT_TIMEOUT_SECONDS,
            payload["reason_code"],
            payload["actor_id"],
        )
        return False
    except Exception:
        # Deliberately broad: the caller is an exception handler already returning 403.
        logger.error(
            "Failed to audit authorization denial (reason=%s actor=%s target=%s/%s)",
            payload["reason_code"],
            payload["actor_id"],
            payload["target_type"],
            payload["target_id"],
            exc_info=True,
        )
        return False
