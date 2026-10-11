"""
Unit-level conftest — overrides the root conftest for pure unit tests.

This conftest is picked up for all tests/ in the unit directory and
is intentionally minimal — no FastAPI client, no real Supabase settings.
"""

import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest

from app.core.job_logging import LOGGER_NAME


class JobLogCapture(logging.Handler):
    """Collects the scheduled-job lines, parsed exactly as Cloud Logging would read them."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    @property
    def lines(self) -> list[dict[str, Any]]:
        return [json.loads(record.getMessage()) for record in self.records]


@pytest.fixture
def job_logs() -> Iterator[JobLogCapture]:
    """Capture what the scheduled-job logger writes while the test runs."""
    capture = JobLogCapture()
    job_logger = logging.getLogger(LOGGER_NAME)
    job_logger.addHandler(capture)
    try:
        yield capture
    finally:
        job_logger.removeHandler(capture)
