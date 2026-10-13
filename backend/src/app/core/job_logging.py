"""One structured log line at the start and end of every scheduled job run.

Cloud Run parses a JSON object written on one stdout line into ``jsonPayload`` and reads
its ``severity`` and ``message`` fields. Each run therefore writes exactly two lines,
``scheduled_job.started`` and ``scheduled_job.finished``, with the same shape for the
reminder dispatcher (an HTTP route on the API service) and the document ingestion and
reference refresh Cloud Run Jobs, so one Cloud Logging query answers "did it work?".

The lines carry counts, identifiers of the run itself and an error *category*, never an
exception message: a database or provider error can quote the row or text it failed on.
They use their own handler rather than the root logger because the API service runs
under uvicorn, which leaves the root logger without an INFO handler, and a record at
INFO would otherwise never leave the process.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from collections.abc import Mapping
from typing import Any, Literal

from app.core.llm_failures import categorize_llm_failure
from app.core.log_redaction import CredentialRedactingFilter

LOGGER_NAME = "app.scheduled_jobs"
STARTED = "scheduled_job.started"
FINISHED = "scheduled_job.finished"

JobStatus = Literal["success", "failed", "skipped"]

logger = logging.getLogger(LOGGER_NAME)

# An error code is kept only when it looks like one: a SQLSTATE such as ``23505`` or an
# application code such as ``VALIDATION_ERROR``, never free text.
_SAFE_CODE = re.compile(r"^[A-Z0-9_]{2,40}$")


class _StdoutHandler(logging.Handler):
    """Write each record on its own stdout line, resolving ``sys.stdout`` at write time."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            sys.stdout.write(self.format(record) + "\n")
            sys.stdout.flush()
        except Exception:  # noqa: BLE001 - logging must never fail a job
            self.handleError(record)


def _install_handler() -> None:
    if any(isinstance(handler, _StdoutHandler) for handler in logger.handlers):
        return
    handler = _StdoutHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.addFilter(CredentialRedactingFilter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


_install_handler()


def sanitized_error(exc: BaseException) -> dict[str, str]:
    """A short, PHI-free description of a failure: its type and a stable category.

    The exception text is always dropped. A database (SQLSTATE) or application error code
    is kept when it has the shape of a code.
    """
    fields = {"error_type": type(exc).__name__, "error_category": categorize_llm_failure(exc)}
    code = str(getattr(exc, "code", "") or "")
    if _SAFE_CODE.fullmatch(code):
        fields["error_code"] = code
    return fields


class JobRunLog:
    """The started/finished pair for one run of one scheduled job."""

    def __init__(self, job: str, *, dry_run: bool = False) -> None:
        self.job = job
        self.dry_run = dry_run
        self.run_id: str | None = None
        self._started = time.monotonic()

    def started(self, *, run_id: str | None = None, **context: Any) -> dict[str, Any]:
        self.run_id = run_id or self.run_id
        payload = self._payload(STARTED, status=None, context=context)
        _emit(logging.INFO, payload)
        return payload

    def finished(
        self,
        status: JobStatus,
        summary: Mapping[str, Any],
        *,
        run_id: str | None = None,
        error: BaseException | None = None,
        **context: Any,
    ) -> dict[str, Any]:
        self.run_id = run_id or self.run_id
        payload = self._payload(FINISHED, status=status, context=context)
        payload["duration_ms"] = int((time.monotonic() - self._started) * 1000)
        payload["summary"] = dict(summary)
        if error is not None:
            payload.update(sanitized_error(error))
        level = {"failed": logging.ERROR, "skipped": logging.WARNING}.get(status, logging.INFO)
        _emit(level, payload)
        return payload

    def _payload(
        self, event: str, *, status: JobStatus | None, context: Mapping[str, Any]
    ) -> dict[str, Any]:
        verb = "started" if event == STARTED else f"finished: {status}"
        payload: dict[str, Any] = {
            "message": f"Scheduled job {self.job} {verb}",
            "event": event,
            "job": self.job,
            "run_id": self.run_id,
            "dry_run": self.dry_run,
            # A Job execution name, or the API service revision for an HTTP-triggered run.
            "execution": os.getenv("CLOUD_RUN_EXECUTION") or os.getenv("K_REVISION") or "local",
        }
        if status is not None:
            payload["status"] = status
        payload.update(context)
        return payload


def _emit(level: int, payload: dict[str, Any]) -> None:
    payload["severity"] = logging.getLevelName(level)
    logger.log(
        level,
        "%s",
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str),
        extra={"scheduled_job": payload},
    )
