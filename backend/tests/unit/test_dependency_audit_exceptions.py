"""Guards that keep each accepted dependency-audit exception in ci.yml valid."""

from __future__ import annotations

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
CI = BACKEND.parent / ".github" / "workflows" / "ci.yml"
OTEL_EXCEPTION = "GHSA-xcq7-p3pf-p88h"


def _locked_packages(name: str) -> set[str]:
    lines = (BACKEND / name).read_text().splitlines()
    return {
        match.group(1).lower()
        for line in lines
        if (match := re.match(r"^([A-Za-z0-9_.-]+)==", line))
    }


def test_tracestate_exception_holds_only_while_inbound_headers_are_never_extracted() -> None:
    """The OpenTelemetry tracestate flaw needs a propagator reading inbound request headers."""
    if OTEL_EXCEPTION not in CI.read_text():
        return
    for lock in ("requirements.txt", "requirements-dev.txt"):
        packages = _locked_packages(lock)
        assert not {
            p
            for p in packages
            if p.startswith(("opentelemetry-instrumentation", "opentelemetry-propagator"))
        }, (
            f"{lock} now installs OpenTelemetry instrumentation; remove the {OTEL_EXCEPTION} audit exception "
            "and upgrade opentelemetry-api to 1.45.1 or later instead."
        )
    for source in (BACKEND / "src").rglob("*.py"):
        text = source.read_text()
        assert "opentelemetry" not in text, (
            f"{source.relative_to(BACKEND)} imports OpenTelemetry; the {OTEL_EXCEPTION} audit exception no longer holds."
        )


def test_tracestate_exception_is_removed_once_the_fixed_release_is_locked() -> None:
    """Drop the exception as soon as the lock carries a patched opentelemetry-api."""
    if OTEL_EXCEPTION not in CI.read_text():
        return
    match = re.search(
        r"^opentelemetry-api==(\d+)\.(\d+)\.(\d+)", (BACKEND / "requirements.txt").read_text(), re.M
    )
    assert match is not None
    assert tuple(int(part) for part in match.groups()) < (1, 45, 1), (
        f"opentelemetry-api is patched; remove the {OTEL_EXCEPTION} exception from ci.yml."
    )
