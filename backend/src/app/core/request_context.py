"""Pure ASGI middleware: one request id and trace per HTTP request and per websocket.

The id is the Cloud Trace id from ``X-Cloud-Trace-Context`` when present, so a log line
links to the request in Cloud Logging and Trace; otherwise a generated id. The context is
reset when the request or socket ends. Server-owned turn tasks copy the context when they
are created, so their lines keep the request id of the message that started them.
"""

from __future__ import annotations

import logging
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.structured_logging import end_request, log_event, start_request

logger = logging.getLogger("app.request")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        header = next(
            (
                v.decode("latin-1")
                for k, v in scope.get("headers", [])
                if k == b"x-cloud-trace-context"
            ),
            None,
        )
        tokens = start_request(header)
        started = time.monotonic()
        status: dict[str, int] = {}

        async def tracking_send(message: Message) -> None:
            if message["type"] in {"http.response.start", "websocket.accept"}:
                status["code"] = message.get("status", 101)
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        finally:
            # Only the socket's life is logged here; HTTP requests already have Cloud Run's
            # request log. A long socket is the interesting one when a turn is traced.
            if scope["type"] == "websocket":
                log_event(
                    logger,
                    "websocket.closed",
                    message="Websocket closed",
                    duration_ms=int((time.monotonic() - started) * 1000),
                    path=_route(scope),
                )
            end_request(tokens)


def _route(scope: Scope) -> str:
    """Path with the patient id removed: ids stay out of free-form fields."""
    path = str(scope.get("path", ""))
    parts = path.rstrip("/").split("/")
    return "/".join(parts[:3]) if path.startswith("/ws/") else path
