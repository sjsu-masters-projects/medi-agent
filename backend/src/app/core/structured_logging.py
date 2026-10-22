"""Structured JSON logs for Cloud Logging, with a request and turn context.

One line is one JSON object on stdout. Cloud Run parses it into ``jsonPayload`` and reads
``severity``, ``message`` and ``logging.googleapis.com/trace``. Every line written while a
request, socket or turn is active carries the same correlation fields, so one failing Nora
turn can be followed from the logs alone:

``request_id``, ``turn_id``, ``session_hash``, ``actor_hash``, ``event``, ``outcome``,
``duration_ms``.

Patient text never enters a log. Identifiers are hashed with a salted SHA-256 prefix;
exception messages are never written (only the type and a stack of file and line
numbers), because a provider or database error can quote the text it failed on.
Lifecycle lines use :func:`log_event` with a fixed vocabulary of fields.

Outside Cloud Run the same records print as one readable line.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import sys
import traceback
import uuid
from collections.abc import Iterator
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from app.core.log_redaction import CredentialRedactingFilter, redact

TRACE_FIELD = "logging.googleapis.com/trace"

# A constant, not a secret: it only stops hashes being compared with other systems' hashes.
# The hash is for grouping log lines by actor or conversation, not for anonymising data.
_HASH_SALT = "mediagent-log-v1:"
_HASH_LENGTH = 12

_request_id: ContextVar[str | None] = ContextVar("log_request_id", default=None)
_trace: ContextVar[str | None] = ContextVar("log_trace", default=None)
_turn_id: ContextVar[str | None] = ContextVar("log_turn_id", default=None)
_task_id: ContextVar[str | None] = ContextVar("log_task_id", default=None)
_session_hash: ContextVar[str | None] = ContextVar("log_session_hash", default=None)
_actor_hash: ContextVar[str | None] = ContextVar("log_actor_hash", default=None)

# Fields a caller may attach to a record through ``extra=``. Anything else is ignored, so a
# stray ``extra={"content": ...}`` cannot reach the log.
EVENT_FIELDS = (
    "event",
    "turn_id",
    "outcome",
    "duration_ms",
    "operation",
    "reason",
    "execute",
    "attempt",
    "model",
    "fallback_used",
    "accepted",
    "late",
    "category",
    "trigger",
    "path",
    "status",
    "http_status",
    "method",
    "chat_fallback_layer",
    "chat_fallback_reason",
    "failure_category",
    "queue",
    "retry_count",
    "close_code",
    "initiator",
    "utterance_id",
    "speech_id",
    "chars",
    "frames",
)

_TRACE_HEADER = re.compile(r"^([0-9a-fA-F]{32})(?:/\d+)?(?:;o=\d)?$")


def hash_identifier(value: object) -> str:
    """A salted SHA-256 prefix: stable for grouping lines, useless for finding a person."""
    return hashlib.sha256((_HASH_SALT + str(value)).encode()).hexdigest()[:_HASH_LENGTH]


def new_request_id() -> str:
    return uuid.uuid4().hex


def parse_trace_header(header: str | None) -> str | None:
    """The 32-hex trace id of ``X-Cloud-Trace-Context`` (``TRACE_ID/SPAN_ID;o=1``)."""
    match = _TRACE_HEADER.match((header or "").strip())
    return match.group(1).lower() if match else None


def trace_resource(trace_id: str) -> str | None:
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
    if not project:
        try:
            from app.config import settings

            project = settings.google_project_id
        except Exception:  # noqa: BLE001 - logging must work before settings do
            project = ""
    # Cloud Logging links a line to its trace only with the full resource name.
    return f"projects/{project}/traces/{trace_id}" if project else None


def start_request(trace_header: str | None = None) -> tuple[Any, ...]:
    """Set the request id (and trace) for this task; returns the tokens for :func:`end_request`."""
    trace_id = parse_trace_header(trace_header)
    request_id = trace_id or new_request_id()
    return (
        _request_id.set(request_id),
        _trace.set(trace_resource(trace_id) if trace_id else None),
        _turn_id.set(None),
        _session_hash.set(None),
        _actor_hash.set(None),
        _task_id.set(None),
    )


def end_request(tokens: tuple[Any, ...]) -> None:
    for var, token in zip(
        (_request_id, _trace, _turn_id, _session_hash, _actor_hash, _task_id), tokens, strict=True
    ):
        # A token can only be reset in the context that made it; the middleware always is.
        with contextlib.suppress(ValueError):
            var.reset(token)


def set_actor(actor_id: object | None = None, session_id: object | None = None) -> None:
    if actor_id is not None:
        _actor_hash.set(hash_identifier(actor_id))
    if session_id is not None:
        _session_hash.set(hash_identifier(session_id))


def current_request_id() -> str | None:
    return _request_id.get()


def set_task_id(task_id: object | None) -> None:
    """The queue task this request is running (rule 24); reset with the request."""
    _task_id.set(str(task_id)[:200] if task_id else None)


def set_turn_id(turn_id: object | None) -> None:
    _turn_id.set(str(turn_id) if turn_id else None)


@contextlib.contextmanager
def turn_context(turn_id: object | None) -> Iterator[None]:
    """Bind ``turn_id`` for the current task. Server-owned turn tasks copy the caller's
    context when created, so the request id survives into them; the turn id is set here."""
    token = _turn_id.set(str(turn_id) if turn_id else None)
    try:
        yield
    finally:
        _turn_id.reset(token)


def current_context() -> dict[str, str]:
    values = {
        "request_id": _request_id.get(),
        "turn_id": _turn_id.get(),
        "task_id": _task_id.get(),
        "session_hash": _session_hash.get(),
        "actor_hash": _actor_hash.get(),
        TRACE_FIELD: _trace.get(),
    }
    return {key: value for key, value in values.items() if value}


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    message: str | None = None,
    **fields: Any,
) -> None:
    """One structured line. ``fields`` must come from :data:`EVENT_FIELDS` (others are dropped)."""
    extra = {key: value for key, value in fields.items() if key in EVENT_FIELDS}
    extra["event"] = event
    logger.log(level, message or event, extra=extra)


def _safe_traceback(exc_info: Any) -> str | None:
    """File, line and function of each frame; never the exception message or source text."""
    try:
        frames = traceback.extract_tb(exc_info[2])
    except Exception:  # noqa: BLE001
        return None
    return " <- ".join(f"{os.path.basename(f.filename)}:{f.lineno}:{f.name}" for f in frames[-8:])


def _scalar(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | float):
        return value
    return redact(str(value))[:200]


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "severity": "WARNING" if record.levelname == "WARN" else record.levelname,
            "message": redact(record.getMessage()),
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "logger": record.name,
        }
        payload.update(current_context())
        for key in EVENT_FIELDS:
            if getattr(record, key, None) is not None:
                payload[key] = _scalar(getattr(record, key))
        if record.exc_info:
            payload["error_type"] = getattr(record.exc_info[0], "__name__", "Exception")
            stack = _safe_traceback(record.exc_info)
            if stack:
                payload["error_stack"] = stack
        return json.dumps(payload, separators=(",", ":"), default=str)


class ReadableFormatter(logging.Formatter):
    """Local and development output: time, level, logger, message and the correlation ids."""

    def format(self, record: logging.LogRecord) -> str:
        context = current_context()
        extras = [
            f"{key}={_scalar(getattr(record, key))}"
            for key in EVENT_FIELDS
            if getattr(record, key, None) is not None and key != "turn_id"
        ]
        ids = [f"{key}={value}" for key, value in context.items() if key != TRACE_FIELD]
        suffix = f" [{' '.join(ids + extras)}]" if ids or extras else ""
        line = f"{datetime.fromtimestamp(record.created).strftime('%H:%M:%S')} "
        line += f"{record.levelname:<7} {record.name}: {redact(record.getMessage())}{suffix}"
        if record.exc_info:
            line += f" ({getattr(record.exc_info[0], '__name__', 'Exception')})"
        return line


class _StdoutHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """Resolves ``sys.stdout`` at write time so captured output keeps working."""

    def __init__(self) -> None:
        super().__init__(sys.stdout)

    def emit(self, record: logging.LogRecord) -> None:
        self.stream = sys.stdout
        super().emit(record)


_HANDLER_MARK = "_mediagent_structured"
# HTTP client libraries log full request URLs (patient and filter values). Never at INFO.
_QUIET_LOGGERS = ("httpx", "httpcore", "hpack", "urllib3", "websockets", "google_genai")


def running_on_cloud_run() -> bool:
    return bool(os.getenv("K_SERVICE") or os.getenv("CLOUD_RUN_JOB"))


def configure_logging(*, json_output: bool | None = None, level: int | str | None = None) -> None:
    """Install one root handler. JSON on Cloud Run (or ``LOG_FORMAT=json``), readable elsewhere.

    uvicorn keeps its own access and error handlers, so its access log is unchanged.
    """
    if json_output is None:
        choice = os.getenv("LOG_FORMAT", "").strip().lower()
        json_output = choice == "json" or (choice != "text" and running_on_cloud_run())
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_MARK, False):
            root.removeHandler(handler)
    handler = _StdoutHandler()
    setattr(handler, _HANDLER_MARK, True)
    handler.setFormatter(JsonFormatter() if json_output else ReadableFormatter())
    handler.addFilter(CredentialRedactingFilter())
    root.addHandler(handler)
    root.setLevel(level if level is not None else logging.INFO)
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
