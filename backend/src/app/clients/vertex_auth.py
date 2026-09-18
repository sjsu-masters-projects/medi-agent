"""Application Default Credentials as a bearer token that stays current.

Vertex's OpenAI-compatible surface authenticates with a Google access token rather than
an API key. A token lasts an hour, which is shorter than a long ingestion job, an
evaluation run, or the lifetime of a process serving requests — so a token captured once
at construction turns into authentication errors partway through, at the point where the
work is most expensive to lose.

This returns a callable instead of a string for that reason: the caller asks for a token
per request and gets a refreshed one whenever the current one has expired.
"""

from __future__ import annotations

from collections.abc import Callable

_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def google_adc_bearer() -> Callable[[], str]:
    """Return a callable yielding a current Google access token.

    Raises immediately if credentials cannot be resolved. Failing at startup is the point:
    a provider that constructs successfully and then fails on every call looks like an
    outage at the model rather than a missing credential on this machine.
    """
    import google.auth
    from google.auth.transport.requests import Request

    credentials, _project = google.auth.default(scopes=[_CLOUD_PLATFORM_SCOPE])
    request = Request()

    def token() -> str:
        if not credentials.valid:
            # `google-auth` ships `py.typed` but leaves `refresh` unannotated.
            credentials.refresh(request)  # type: ignore[no-untyped-call]
        return str(credentials.token)

    token()
    return token
