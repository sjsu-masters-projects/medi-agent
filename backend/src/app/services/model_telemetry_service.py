"""Record what every model call cost and how it ended.

`GenerationTelemetry` is produced on every generation and then thrown away: the router
returned `response.text` and dropped the envelope beside it. So the figures the routing
table was chosen on — latency per workload, which model actually served, how often an
answer is truncated, what it costs — stopped being collected the moment the decision was
made. This writes them to `model_invocation_events` (migration 035).

**Best effort, on purpose.** Unlike an authorization denial, which is a security record
and is therefore awaited, a telemetry row is operational and happens on every turn.
Awaiting it would let a stalled database spend a patient's latency budget on bookkeeping,
so the write is scheduled in the background and a lost row is an acceptable outcome. A
failure never reaches the caller; it is logged at ERROR so it surfaces in alerting.

**No patient data.** No identifiers, no prompt, no response text — see migration 035. A
row here is about the model and the budget, and must never become another place a record
leaks from.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
from typing import Any

from app.clients.supabase import get_admin_client
from app.models.generation import GenerationTelemetry

logger = logging.getLogger(__name__)

_TABLE = "model_invocation_events"

# A generation must not wait on its own bookkeeping. Generous enough for a healthy insert,
# short enough that a stalled database cannot hold a background task open indefinitely.
_TELEMETRY_TIMEOUT_SECONDS = 5.0

# Column limits from migration 035. Enforced here so an over-long value is trimmed rather
# than rejected by the database, which would lose the whole row over one field.
_WORKLOAD_LIMIT = 60
_PROVIDER_LIMIT = 60
_MODEL_LIMIT = 120
_REASON_LIMIT = 40

# `asyncio.create_task` keeps only a weak reference, so a task with no other referent can
# be garbage collected mid-flight. Holding them here is what makes "fire and forget"
# actually run to completion.
_pending: set[asyncio.Task[bool]] = set()


async def _insert_row(payload: dict[str, Any]) -> None:
    """Write one row. Separated so tests can substitute an in-memory sink."""
    client = get_admin_client()
    await asyncio.to_thread(client.table(_TABLE).insert(payload).execute)


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed[:limit] if trimmed else None


async def record_invocation(
    *,
    workload: str,
    provider: str,
    model: str,
    latency_ms: int,
    succeeded: bool,
    finish_reason: str | None = None,
    error_code: str | None = None,
    usage: Mapping[str, int] | None = None,
    retries: int = 0,
    fallback_path: Sequence[str] | None = None,
) -> bool:
    """Append one invocation record. Returns True when the row was written."""
    tokens = dict(usage or {})
    payload: dict[str, Any] = {
        "workload": _truncate(workload, _WORKLOAD_LIMIT) or "unknown",
        "provider": _truncate(provider, _PROVIDER_LIMIT) or "unknown",
        "model": _truncate(model, _MODEL_LIMIT) or "unknown",
        "succeeded": succeeded,
        "finish_reason": _truncate(finish_reason, _REASON_LIMIT),
        "error_code": _truncate(error_code, _REASON_LIMIT),
        "latency_ms": max(0, int(latency_ms)),
        "input_tokens": tokens.get("input_tokens"),
        "output_tokens": tokens.get("output_tokens"),
        # Thinking is billed inside the completion total, so a reasoning model given the
        # same budget as a plain one has less of it left for the answer. Recorded
        # separately so that is visible rather than inferred.
        "reasoning_tokens": tokens.get("reasoning_tokens"),
        "retries": max(0, int(retries)),
        "fallback_path": list(fallback_path or []),
    }

    try:
        await asyncio.wait_for(_insert_row(payload), timeout=_TELEMETRY_TIMEOUT_SECONDS)
    except Exception:
        # Never surfaced to the caller: the generation succeeded, and turning a
        # bookkeeping failure into a failed answer would be a worse outcome than a
        # missing row. The workload is safe to log; nothing else here identifies anyone.
        logger.error("Could not record model telemetry for %s", workload, exc_info=True)
        return False
    return True


async def record_generation(
    *,
    workload: str,
    telemetry: GenerationTelemetry,
    succeeded: bool = True,
    error_code: str | None = None,
) -> bool:
    """Record an invocation from the envelope a provider already returned."""
    return await record_invocation(
        workload=workload,
        provider=telemetry.provider,
        model=telemetry.model,
        latency_ms=telemetry.latency_ms,
        succeeded=succeeded,
        finish_reason=telemetry.finish_reason,
        error_code=error_code,
        usage=telemetry.usage,
        retries=telemetry.retries,
        fallback_path=telemetry.fallback_path,
    )


def schedule_generation_record(
    *,
    workload: str,
    telemetry: GenerationTelemetry,
    succeeded: bool = True,
    error_code: str | None = None,
) -> asyncio.Task[bool] | None:
    """Record in the background, so the caller's latency budget is not spent on it.

    Returns the task for tests to await. Returns None when there is no running loop,
    which is how a synchronous caller gets a no-op instead of an exception.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.debug("No running loop; skipping telemetry for %s", workload)
        return None

    task = loop.create_task(
        record_generation(
            workload=workload,
            telemetry=telemetry,
            succeeded=succeeded,
            error_code=error_code,
        )
    )
    _pending.add(task)
    task.add_done_callback(_pending.discard)
    return task
