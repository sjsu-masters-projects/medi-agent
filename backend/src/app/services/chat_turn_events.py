"""Viewing a worker-run turn without a stream (OPS-006 phase 2).

A worker turn runs in another service, so no socket is attached to it in memory. Its progress
is the ordered ``chat_turn_events`` log. A socket (or the HTTP read) is a *viewer*: it polls the
log from the database, which works from any instance and after any reconnect (rule 1, 19), and
translates events into the messages the portal already understands. Phase 3 replaces the poll
with one server-sent stream that reads the same table.

Viewer tasks are tracked in a :class:`TurnWatchSet` (strong references, cancelled when the socket
closes or the server stops: rule 16) and are bounded in number (rule 14). A viewer never changes a
turn.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

from supabase import Client

from app.core.db_pools import run_events_db
from app.core.exceptions import ExternalServiceError, ServiceUnavailableError
from app.core.structured_logging import log_event, turn_context
from app.services.chat_turn_pipeline import serialize_chat_message
from app.services.chat_turn_service import public_turn

logger = logging.getLogger(__name__)

READ_TIMEOUT_SECONDS = 8
# Short enough that a sentence written by the worker reaches a listening patient quickly, long
# enough that an idle viewer costs about one small indexed read a second.
POLL_ACTIVE_SECONDS = 0.3
POLL_MAX_IDLE_SECONDS = 1.0
STATUS_CHECK_EVERY = 6  # idle polls between checks of the turn row (a terminal event may be absent)
MAX_WATCHERS = 200
BATCH = 200
TERMINAL = {"completed", "failed", "interrupted"}
Send = Callable[[dict[str, Any]], Awaitable[bool]]


class TurnEventReader:
    """Read-only access to a turn's events, messages and status. Each call is bounded."""

    def __init__(self, db: Client) -> None:
        self.db = db

    async def _run(self, query: Any) -> list[dict[str, Any]]:
        try:
            response = await asyncio.wait_for(
                run_events_db(query.execute), timeout=READ_TIMEOUT_SECONDS
            )
        except TimeoutError:
            raise ExternalServiceError("Chat", "Turn events are unavailable.") from None
        return [row for row in (response.data or []) if isinstance(row, dict)]

    async def events_after(self, turn_id: str, after_seq: int) -> list[dict[str, Any]]:
        """Events with seq > after_seq, oldest first. On the first read (after_seq = 0) only the
        newest draft is returned, with every other event, so a late viewer gets the draft so far
        without replaying each checkpoint."""
        base = self.db.table("chat_turn_events").select("seq,type,payload").eq("turn_id", turn_id)
        if after_seq > 0:
            return await self._run(base.gt("seq", after_seq).order("seq").limit(BATCH))
        others = await self._run(base.neq("type", "draft").order("seq").limit(BATCH))
        drafts = await self._run(
            self.db.table("chat_turn_events")
            .select("seq,type,payload")
            .eq("turn_id", turn_id)
            .eq("type", "draft")
            .order("seq", desc=True)
            .limit(1)
        )
        return sorted(others + drafts, key=lambda row: int(row["seq"]))

    async def turn(self, patient_id: str, turn_id: str) -> dict[str, Any] | None:
        rows = await self._run(
            self.db.table("chat_turns")
            .select(
                "id,client_message_id,status,attempt,deadline_at,failure_code,"
                "actions_started,dismissed_at,assistant_message_id,via_worker,session_id"
            )
            .eq("id", turn_id)
            .eq("patient_id", patient_id)
            .limit(1)
        )
        return rows[0] if rows else None

    async def message(self, patient_id: str, message_id: str) -> dict[str, Any] | None:
        rows = await self._run(
            self.db.table("chat_messages")
            .select("*")
            .eq("id", message_id)
            .eq("patient_id", patient_id)
            .limit(1)
        )
        return rows[0] if rows else None


class TurnWatchSet:
    """The viewer tasks of one socket."""

    _all: set[TurnWatchSet] = set()

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        TurnWatchSet._all.add(self)

    def watching(self, turn_id: str) -> bool:
        task = self._tasks.get(turn_id)
        return task is not None and not task.done()

    def start(self, turn_id: str, factory: Callable[[], Coroutine[Any, Any, None]]) -> bool:
        """Start a viewer unless this socket already watches the turn or the server is full."""
        if self.watching(turn_id):
            return False
        if sum(len(w._tasks) for w in TurnWatchSet._all) >= MAX_WATCHERS:
            log_event(
                logger,
                "turn_watch.shed",
                level=logging.WARNING,
                message="Turn viewer refused: too many viewers; the client recovers by request",
                turn_id=turn_id,
                outcome="shed",
            )
            return False
        task = asyncio.get_running_loop().create_task(self._supervise(turn_id, factory))
        self._tasks[turn_id] = task
        task.add_done_callback(functools.partial(self._finished, turn_id))
        return True

    def _finished(self, turn_id: str, task: asyncio.Task[None]) -> None:
        if self._tasks.get(turn_id) is task:
            del self._tasks[turn_id]

    @staticmethod
    async def _supervise(turn_id: str, factory: Callable[[], Coroutine[Any, Any, None]]) -> None:
        try:
            with turn_context(turn_id):
                await factory()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # a viewer failing must never reach the turn
            log_event(
                logger,
                "turn_watch.crashed",
                level=logging.WARNING,
                message="Turn viewer stopped",
                turn_id=turn_id,
                outcome=type(exc).__name__,
            )

    async def close(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        TurnWatchSet._all.discard(self)

    @classmethod
    async def close_all(cls) -> None:
        await asyncio.gather(*(w.close() for w in list(cls._all)), return_exceptions=True)


def event_to_messages(
    event: dict[str, Any], state: dict[str, Any], base: dict[str, Any]
) -> list[dict[str, Any]]:
    """Translate one logged event into portal messages. ``state`` carries what was already sent
    (``text`` and ``started``) so a draft sends only its new characters. Pure and testable."""
    kind, payload = event.get("type"), event.get("payload") or {}
    out: list[dict[str, Any]] = []
    if kind == "started":
        run = int(payload.get("run") or 0)
        if state.get("started") and run > int(state.get("run") or 0):
            # The worker lost the turn and another run took it over: its draft starts again,
            # so what this viewer showed is withdrawn rather than left to look stuck.
            out.append({"type": "assistant_reset"})
            state.update(started=False, text="", epoch=0)
        state["run"] = run
        out.append({"type": "chat_turn", "turn": public_turn({**base, "status": "processing"})})
    elif kind == "draft":
        epoch = int(payload.get("epoch") or 0)
        if epoch > int(state.get("epoch") or 0):
            if state.get("text"):
                out.append({"type": "assistant_reset"})
            state.update(epoch=epoch, text="")
        if not state.get("started"):
            out.append(
                {
                    "type": "assistant_start",
                    "intent": str(payload.get("intent") or "general"),
                    "urgency": str(payload.get("urgency") or "routine"),
                }
            )
            state["started"] = True
        content = str(payload.get("content") or "")
        sent = str(state.get("text") or "")
        # Chunks only append. A draft that does not extend what was shown is left for the final
        # reply to replace rather than shown out of order.
        if content.startswith(sent) and len(content) > len(sent):
            out.append({"type": "assistant_chunk", "content": content[len(sent) :]})
            state["text"] = content
    elif kind == "notice" and isinstance(payload.get("type"), str):
        out.append(payload)
    return out


async def watch_turn(
    reader: TurnEventReader,
    *,
    patient_id: str,
    turn: dict[str, Any],
    user_message: dict[str, Any] | None,
    send: Send,
    on_terminal: Callable[[str], Awaitable[None]] | None = None,
    max_seconds: float = 300.0,
) -> None:
    """Deliver a turn's events to one viewer until the turn ends, the viewer goes away or
    ``max_seconds`` passes (the client then recovers by request). Resumes by seq; any instance
    can run it."""
    turn_id = str(turn["id"])
    base = {**turn, **({"user_message": user_message} if user_message else {})}
    state: dict[str, Any] = {}
    last_seq, idle, deadline = 0, 0, time.monotonic() + max_seconds
    started = time.monotonic()
    while time.monotonic() < deadline:
        terminal_row = None
        try:
            events = await reader.events_after(turn_id, last_seq)
            if not events and idle and idle % STATUS_CHECK_EVERY == 0:
                row = await reader.turn(patient_id, turn_id)
                if row and row.get("status") in TERMINAL:
                    terminal_row = row
        except (ExternalServiceError, ServiceUnavailableError):
            # A busy pool or a slow read: skip this tick; the log is the truth, not the poll.
            idle += 1
            await asyncio.sleep(min(POLL_MAX_IDLE_SECONDS, 0.5 * (idle + 1)))
            continue
        finished: str | None = None
        for event in events:
            last_seq = max(last_seq, int(event["seq"]))
            kind = event.get("type")
            if kind == "completed":
                message = await reader.message(
                    patient_id, str((event.get("payload") or {}).get("message_id") or "")
                )
                if message is not None and not await send(
                    {"type": "assistant_complete", "message": serialize_chat_message(message)}
                ):
                    return
                finished = "completed"
                break
            if kind in {"failed", "interrupted"}:
                finished = str(kind)
                break
            for message in event_to_messages(event, state, base):
                if not await send(message):
                    return  # the viewer is gone; the turn is unaffected
        if finished is None and terminal_row is not None:
            finished = str(terminal_row["status"])
            if finished == "completed" and terminal_row.get("assistant_message_id"):
                message = await reader.message(
                    patient_id, str(terminal_row["assistant_message_id"])
                )
                if message is not None and not await send(
                    {"type": "assistant_complete", "message": serialize_chat_message(message)}
                ):
                    return
        if finished is not None:
            if not await send(
                {"type": "chat_turn", "turn": public_turn({**base, "status": finished})}
            ):
                return
            if on_terminal is not None:
                await on_terminal(finished)
            log_event(
                logger,
                "turn_watch.finished",
                message="Turn viewer finished",
                turn_id=turn_id,
                outcome=finished,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            return
        idle = 0 if events else idle + 1
        await asyncio.sleep(
            POLL_ACTIVE_SECONDS if events else min(POLL_MAX_IDLE_SECONDS, 0.4 + 0.2 * idle)
        )
    log_event(
        logger,
        "turn_watch.timeout",
        level=logging.WARNING,
        message="Turn viewer stopped at its time limit; the client recovers by request",
        turn_id=turn_id,
        outcome="timeout",
    )
