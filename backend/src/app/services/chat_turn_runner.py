"""Server-owned Nora turns.

A turn's execution is an ``asyncio`` task owned by this process-level registry, not by the
websocket that began it. Sockets are *viewers*: they subscribe to the events of the running
turn for their patient and session and may come and go (reload, phone lock, app switch,
network blip) without affecting the turn. The task ends only by completing with its lease,
by failing on a real model or database error, or at its deadline.

Registry lifetime: a run is removed in the ``finally`` of its own task. A viewer is removed
when its socket handler exits or its send fails. Neither can outlive its owner.
Another instance, or a restarted one, has an empty registry: those sockets read the turn
from the database (``recover``) instead.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)

Send = Callable[[dict[str, Any]], Awaitable[bool]]
Key = tuple[str, str]

MAX_QUEUED_EVENTS = 2000
FLUSH_SECONDS = 5.0
_CLOSE: dict[str, Any] = {"type": "__close__"}


class TurnViewer:
    """One socket's view of a patient/session. Events are queued, so a slow or dead socket
    never delays the turn that produces them."""

    def __init__(self, send: Send) -> None:
        self._send = send
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None
        self.closed = False
        self._on_close: Callable[[TurnViewer], None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.get_running_loop().create_task(self._pump())

    def push(self, event: dict[str, Any]) -> None:
        if self.closed:
            return
        if self._queue.qsize() >= MAX_QUEUED_EVENTS:
            # A socket this far behind recovers the saved turn instead.
            self.close()
            return
        self._queue.put_nowait(event)

    async def _pump(self) -> None:
        while True:
            event = await self._queue.get()
            try:
                if event is _CLOSE:
                    return
                try:
                    delivered = await self._send(event)
                except Exception:
                    delivered = False
                if not delivered:
                    self.close()
                    return
            finally:
                self._queue.task_done()

    async def flush(self) -> None:
        if self.closed or self._task is None:
            return
        join = asyncio.ensure_future(self._queue.join())
        try:
            await asyncio.wait(
                {join, self._task}, timeout=FLUSH_SECONDS, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            join.cancel()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self._on_close:
            self._on_close(self)
        # Drop anything unsent; the pump may be mid-send, so cancel rather than wait.
        if self._task is not None and not self._task.done():
            self._task.cancel()


class TurnRun:
    def __init__(self, turn_id: str, key: Key, origin: TurnViewer | None) -> None:
        self.turn_id, self.key, self.origin = turn_id, key, origin
        self.task: asyncio.Task[Any] | None = None
        self.status_event: dict[str, Any] | None = None
        self.start_event: dict[str, Any] | None = None
        self.draft: list[str] = []
        self.result: Any = None


class TurnRunner:
    def __init__(self) -> None:
        self._runs: dict[str, TurnRun] = {}
        self._by_key: dict[Key, TurnRun] = {}
        self._viewers: dict[Key, set[TurnViewer]] = {}

    # -- viewers -----------------------------------------------------------------
    def attach(self, key: Key, send: Send) -> TurnViewer:
        """Register a socket as a viewer; it immediately receives the running turn, if any."""
        viewer = TurnViewer(send)
        viewer._on_close = lambda v: self._detach(key, v)
        self._viewers.setdefault(key, set()).add(viewer)
        viewer.start()
        run = self._by_key.get(key)
        if run is not None:
            self._snapshot(run, viewer)
        return viewer

    def _detach(self, key: Key, viewer: TurnViewer) -> None:
        group = self._viewers.get(key)
        if group is not None:
            group.discard(viewer)
            if not group:
                del self._viewers[key]

    def _snapshot(self, run: TurnRun, viewer: TurnViewer) -> None:
        """Late subscribers get the status and the draft so far, then live events."""
        if run.status_event:
            viewer.push(run.status_event)
        if run.start_event:
            viewer.push(run.start_event)
        if run.draft:
            viewer.push({"type": "assistant_chunk", "content": "".join(run.draft)})

    # -- runs --------------------------------------------------------------------
    def active(self, key: Key) -> TurnRun | None:
        return self._by_key.get(key)

    def start(
        self,
        turn_id: str,
        key: Key,
        body: Callable[[TurnRun], Coroutine[Any, Any, Any]],
        origin: TurnViewer | None = None,
    ) -> TurnRun:
        run = TurnRun(turn_id, key, origin)
        self._runs[turn_id] = run
        self._by_key[key] = run
        run.task = asyncio.get_running_loop().create_task(self._supervise(run, body))
        return run

    async def _supervise(
        self, run: TurnRun, body: Callable[[TurnRun], Coroutine[Any, Any, Any]]
    ) -> None:
        try:
            run.result = await body(run)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # the body reports its own failures; this is the last net
            logger.error("Server-owned chat turn crashed: %s", type(exc).__name__)
        finally:
            viewers = list(self._viewers.get(run.key, ()))
            await asyncio.gather(*(v.flush() for v in viewers), return_exceptions=True)
            self._runs.pop(run.turn_id, None)
            if self._by_key.get(run.key) is run:
                del self._by_key[run.key]

    def publish(self, run: TurnRun, event: dict[str, Any], *, origin_only: bool = False) -> None:
        kind = event.get("type")
        if kind == "chat_turn":
            run.status_event = event
        elif kind == "assistant_start":
            run.start_event, run.draft = event, []
        elif kind == "assistant_chunk":
            run.draft.append(str(event.get("content") or ""))
        elif kind == "assistant_complete":
            run.start_event, run.draft = None, []
        if origin_only:
            if run.origin is not None:
                run.origin.push(event)
            return
        for viewer in list(self._viewers.get(run.key, ())):
            viewer.push(event)

    # -- shutdown ----------------------------------------------------------------
    @property
    def running(self) -> int:
        return len(self._runs)

    async def drain(self, timeout: float = 8.0) -> None:
        """Wait for running turns; whatever is left is reconciled by its saved deadline."""
        tasks = [r.task for r in self._runs.values() if r.task is not None]
        if not tasks:
            return
        _, pending = await asyncio.wait(tasks, timeout=timeout)
        if pending:
            logger.warning(
                "%d chat turn(s) unfinished at shutdown; deadline will reconcile", len(pending)
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)


turn_runner = TurnRunner()
