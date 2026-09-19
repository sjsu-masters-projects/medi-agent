"""Bucket a model failure into a stable label for metrics and dashboards.

Lifted out of the triage graph module so it survives the removal of that runtime. It has
no framework imports and never did — it reads an exception and returns a string, and the
callers that need it are a router and an agent runtime, neither of which should have to
import the other to classify a timeout.

The buckets are deliberately coarse and stable. A dashboard that distinguishes "quota
exhausted" from "endpoint missing" answers a question someone can act on; one that
reports the exception class of the week answers none.
"""

from __future__ import annotations


def categorize_llm_failure(exc: BaseException) -> str:
    """Return a stable label for why a model call failed."""
    name = type(exc).__name__
    text = f"{name}: {exc}".lower()
    if "credentials" in text or "permissiondenied" in name.lower() or "403" in text:
        return "auth_error"
    if "notfound" in name.lower() or "404" in text:
        return "endpoint_not_found"
    if "timeout" in name.lower() or "deadline" in text or "timed out" in text:
        return "timeout"
    if "429" in text or "quota" in text or "resourceexhausted" in name.lower():
        return "quota_exceeded"
    if "validation" in name.lower() or "json" in name.lower() or "parse" in text:
        return "parse_error"
    if "connection" in name.lower() or "network" in name.lower():
        return "network_error"
    return "unknown_error"
