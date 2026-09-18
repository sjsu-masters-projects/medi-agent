"""Bucketing a model failure into something a dashboard can answer a question with.

Migrated from the triage agent's tests, which were this function's only coverage. It now
lives in `app.core.llm_failures` because a router and an agent runtime both need it and
neither should import the other to classify a timeout.

The buckets are coarse on purpose. "Quota exhausted" and "endpoint missing" lead to
different actions; the exception class of the week leads to none.
"""

from __future__ import annotations

import pytest

from app.core.llm_failures import categorize_llm_failure


def _named(name: str, message: str) -> Exception:
    """An exception whose *class name* carries the signal, as the SDKs' do."""
    error_type = type(name, (Exception,), {})
    return error_type(message)


def test_missing_credentials_are_an_auth_error() -> None:
    exc = RuntimeError(
        "Your default credentials were not found. To set up Application Default Credentials"
    )

    assert categorize_llm_failure(exc) == "auth_error"


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError("403 forbidden"),
        _named("PermissionDenied", "caller lacks permission"),
    ],
)
def test_refused_calls_are_an_auth_error(exc: Exception) -> None:
    assert categorize_llm_failure(exc) == "auth_error"


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError("404 model not found"),
        _named("NotFound", "no such endpoint"),
    ],
)
def test_a_missing_endpoint_is_not_reported_as_an_outage(exc: Exception) -> None:
    """A retired model id and a capacity problem need different responses."""
    assert categorize_llm_failure(exc) == "endpoint_not_found"


@pytest.mark.parametrize(
    "exc",
    [
        _named("TimeoutError", "deadline exceeded"),
        RuntimeError("the request timed out"),
    ],
)
def test_a_deadline_is_a_timeout(exc: Exception) -> None:
    assert categorize_llm_failure(exc) == "timeout"


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError("429 quota exceeded"),
        _named("ResourceExhausted", "out of capacity"),
    ],
)
def test_exhausted_capacity_is_reported_as_quota(exc: Exception) -> None:
    assert categorize_llm_failure(exc) == "quota_exceeded"


@pytest.mark.parametrize(
    "exc",
    [
        _named("ValidationError", "schema mismatch"),
        RuntimeError("could not parse the response"),
    ],
)
def test_an_unreadable_answer_is_a_parse_error(exc: Exception) -> None:
    """Distinct from an outage: the model answered, we could not read it."""
    assert categorize_llm_failure(exc) == "parse_error"


def test_a_dropped_connection_is_a_network_error() -> None:
    assert categorize_llm_failure(_named("ConnectionError", "reset by peer")) == "network_error"


def test_anything_unrecognised_falls_through_to_unknown() -> None:
    """The bucket must be total: an unclassified failure still has to be counted."""
    assert categorize_llm_failure(RuntimeError("totally novel issue")) == "unknown_error"


def test_the_message_is_read_as_well_as_the_class() -> None:
    """The SDKs put the signal in either place, so both are consulted."""
    assert categorize_llm_failure(RuntimeError("HTTP 429 from upstream")) == "quota_exceeded"
    assert categorize_llm_failure(_named("ResourceExhausted", "")) == "quota_exceeded"
