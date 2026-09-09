"""Backoff for the A2A retry worker.

Without it a database outage produces a traceback every poll interval for as long as the
outage lasts, burying the incident in its own logs while hammering the failed dependency.
"""

from unittest.mock import MagicMock

from app.services.a2a_retry_worker import _MAX_BACKOFF_SECONDS, A2ARetryWorker


def _worker(poll_interval_seconds: int = 15) -> A2ARetryWorker:
    return A2ARetryWorker(MagicMock(), poll_interval_seconds=poll_interval_seconds)


def test_first_failure_waits_one_poll_interval():
    assert _worker(15)._backoff_seconds(1) == 15


def test_delay_doubles_with_each_consecutive_failure():
    worker = _worker(15)

    assert [worker._backoff_seconds(n) for n in (1, 2, 3, 4)] == [15, 30, 60, 120]


def test_backoff_is_capped():
    worker = _worker(15)

    assert worker._backoff_seconds(99) == _MAX_BACKOFF_SECONDS


def test_cap_is_reached_without_overflowing_on_a_long_outage():
    """A week-long outage must not compute an astronomical delay."""
    worker = _worker(60)

    assert worker._backoff_seconds(10_000) == _MAX_BACKOFF_SECONDS


def test_cap_holds_even_when_one_interval_already_exceeds_it():
    worker = _worker(_MAX_BACKOFF_SECONDS * 2)

    assert worker._backoff_seconds(1) == _MAX_BACKOFF_SECONDS
