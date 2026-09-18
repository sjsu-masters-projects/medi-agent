"""Keep credentials out of log records, whatever a route does with them.

Moving the WebSocket token into a header stops today's leak. This stops the next one:
the access log writes whole request paths, so any future route that accepts a secret as a
query parameter would publish it again, silently and without anyone reviewing a log line.

This is defence in depth, not the fix. A credential in a URL is still wrong even when the
log is scrubbed, because it also reaches proxies, browser history and `Referer` headers,
none of which this filter can reach.
"""

from __future__ import annotations

import logging
import re
from typing import Any

_SENSITIVE_QUERY_KEYS = ("token", "access_token", "refresh_token", "ticket", "api_key", "key")

_REDACTION = "[REDACTED]"

# Matches `token=<value>` up to the next separator. Deliberately narrow: it rewrites only
# the value, so a redacted line still shows which parameter was present and where.
_PATTERN = re.compile(
    r"((?:" + "|".join(_SENSITIVE_QUERY_KEYS) + r")=)[^&\s\"'<>]+",
    re.IGNORECASE,
)


def redact(text: str) -> str:
    """Replace the value of any sensitive query parameter in `text`."""
    return _PATTERN.sub(r"\1" + _REDACTION, text)


def _redact_value(value: Any) -> Any:
    return redact(value) if isinstance(value, str) else value


class CredentialRedactingFilter(logging.Filter):
    """Scrub sensitive query values from a record before a handler formats it.

    The message and its arguments are treated separately because the access logger passes
    the request path as an argument rather than interpolating it into the message, so
    filtering only `record.msg` would miss every URL it writes.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)

        if isinstance(record.args, dict):
            record.args = {key: _redact_value(value) for key, value in record.args.items()}
        elif isinstance(record.args, tuple):
            record.args = tuple(_redact_value(value) for value in record.args)

        return True


def install_credential_redaction(logger_names: tuple[str, ...] = ("uvicorn.access",)) -> None:
    """Attach the filter to the access logger and the root logger.

    Filters on a logger do not apply to records from its children, so the access logger is
    named explicitly rather than relying on the root filter to catch it.
    """
    log_filter = CredentialRedactingFilter()
    for name in (*logger_names, ""):
        logging.getLogger(name).addFilter(log_filter)
