"""Credentials must not survive into a log record.

The WebSocket fix stops today's leak by moving the token into a header. This filter is
the net under the next one: the access logger writes whole request paths, so any future
route that accepts a secret as a query parameter would publish it silently.
"""

from __future__ import annotations

import logging

import pytest

from app.core.log_redaction import CredentialRedactingFilter, install_credential_redaction, redact


def _record(msg: str, args: object = None) -> logging.LogRecord:
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,
        exc_info=None,
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/ws/chat/p1?token=abc.def.ghi", "/ws/chat/p1?token=[REDACTED]"),
        ("/x?access_token=abc", "/x?access_token=[REDACTED]"),
        ("/x?refresh_token=abc", "/x?refresh_token=[REDACTED]"),
        ("/x?ticket=abc", "/x?ticket=[REDACTED]"),
        ("/x?api_key=abc", "/x?api_key=[REDACTED]"),
    ],
)
def test_sensitive_values_are_replaced(raw: str, expected: str) -> None:
    assert redact(raw) == expected


def test_the_parameter_name_survives_so_a_leak_stays_visible() -> None:
    """Scrubbing the whole parameter would hide that a token was sent at all."""
    assert redact("/ws/chat/p1?token=secret") == "/ws/chat/p1?token=[REDACTED]"


def test_only_the_value_up_to_the_next_separator_is_replaced() -> None:
    assert redact("/ws/chat/p1?token=secret&context=doc:1") == (
        "/ws/chat/p1?token=[REDACTED]&context=doc:1"
    )


def test_matching_is_case_insensitive() -> None:
    assert redact("/x?TOKEN=secret") == "/x?TOKEN=[REDACTED]"


def test_unrelated_text_is_untouched() -> None:
    assert redact("/api/v1/chat/history/p1") == "/api/v1/chat/history/p1"


def test_a_token_shaped_value_is_fully_removed() -> None:
    """A dotted, padded value must not survive once it is in a credential parameter."""
    token = "header.payload.signature=="

    assert token not in redact(f"/ws/chat/p1?token={token}")


def test_the_filter_scrubs_the_message() -> None:
    record = _record("connected /ws/chat/p1?token=secret")

    CredentialRedactingFilter().filter(record)

    assert "secret" not in str(record.msg)


def test_the_filter_scrubs_tuple_arguments() -> None:
    """The access logger passes the path as an argument, not inside the message.

    Filtering only `record.msg` would therefore miss every URL it writes, which is the
    one case this filter exists for.
    """
    record = _record('%s - "%s"', ("1.2.3.4", "GET /ws/chat/p1?token=secret HTTP/1.1"))

    CredentialRedactingFilter().filter(record)

    assert "secret" not in record.getMessage()
    assert "[REDACTED]" in record.getMessage()


def test_the_filter_scrubs_dict_arguments() -> None:
    # `logging` only unwraps a mapping when it arrives as a one-element tuple, which is
    # how `logger.info("%(path)s", {...})` actually delivers it.
    record = _record("%(path)s", ({"path": "/ws/chat/p1?token=secret"},))

    CredentialRedactingFilter().filter(record)

    assert "secret" not in record.getMessage()


def test_the_filter_keeps_the_record() -> None:
    """Redaction must never drop a log line — that would trade a leak for blindness."""
    assert CredentialRedactingFilter().filter(_record("nothing sensitive")) is True


def test_install_attaches_to_the_access_logger_explicitly() -> None:
    """Filters on the root logger do not apply to records from named child loggers."""
    access = logging.getLogger("uvicorn.access")
    before = len(access.filters)

    install_credential_redaction()

    try:
        assert len(access.filters) == before + 1
        assert any(isinstance(f, CredentialRedactingFilter) for f in access.filters)
    finally:
        for log_filter in list(access.filters):
            if isinstance(log_filter, CredentialRedactingFilter):
                access.removeFilter(log_filter)
        root = logging.getLogger("")
        for log_filter in list(root.filters):
            if isinstance(log_filter, CredentialRedactingFilter):
                root.removeFilter(log_filter)
