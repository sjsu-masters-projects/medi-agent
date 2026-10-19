"""Authenticate Cloud Tasks calls to the worker service (rule 23).

Cloud Tasks signs an OIDC token as the invoker service account, with the worker URL as its
audience. The worker accepts a request only when the token is a valid Google-signed ID token
(issuer ``accounts.google.com``) for the configured audience, issued to the configured service
account and with a verified email. Anything else is refused: 401 when there is no valid token,
403 when the token is valid but is not the expected caller. The task payload is never trusted
for authority; the worker re-reads ownership from the database.

The route exists only when ``WORKER_MODE`` is true, so the API service has no such surface.
"""

from __future__ import annotations

import hmac
import logging
import threading
import time
from typing import Any

from fastapi import Header, HTTPException
from google.auth.exceptions import GoogleAuthError
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import settings
from app.core.db_pools import run_dispatch
from app.core.structured_logging import log_event

logger = logging.getLogger(__name__)

CERTS_TTL_SECONDS = 600
CERTS_TIMEOUT_SECONDS = 5


class _CachedCertsRequest(google_requests.Request):
    """Google's signing certificates change rarely. Cache each GET for ten minutes (under a
    lock: the verification runs on pool threads) and bound the fetch so a slow endpoint cannot
    hold a worker thread for google-auth's two-minute default."""

    _lock = threading.Lock()
    _cache: dict[str, tuple[float, Any]] = {}

    def __call__(
        self,
        url: str,
        method: str = "GET",
        body: Any = None,
        headers: Any = None,
        timeout: Any = None,
        **kwargs: Any,
    ) -> Any:
        with self._lock:
            hit = self._cache.get(url)
            if hit and time.monotonic() - hit[0] < CERTS_TTL_SECONDS:
                return hit[1]
        response = super().__call__(  # type: ignore[no-untyped-call]
            url, method=method, body=body, headers=headers, timeout=CERTS_TIMEOUT_SECONDS, **kwargs
        )
        if getattr(response, "status", None) == 200:
            with self._lock:
                self._cache[url] = (time.monotonic(), response)
        return response


def _verify(token: str, audience: str) -> dict[str, Any]:
    return dict(
        id_token.verify_oauth2_token(token, _CachedCertsRequest(), audience)  # type: ignore[no-untyped-call]
    )


def _refuse(status: int, reason: str) -> HTTPException:
    log_event(
        logger,
        "task_auth.refused",
        level=logging.WARNING,
        message=f"Worker task refused: {reason}",
        outcome=reason,
        http_status=status,
    )
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return HTTPException(status_code=status, detail="Not authorized", headers=headers)


async def require_cloud_tasks_oidc(
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    if not settings.worker_mode:
        # Defence in depth: the route is not mounted on the API service at all.
        raise HTTPException(status_code=404, detail="Not found")
    audience = (settings.chat_worker_oidc_audience or settings.chat_worker_url).strip()
    expected = settings.chat_worker_invoker_sa.strip().lower()
    if not audience or not expected:
        raise _refuse(403, "not_configured")  # fail closed
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _refuse(401, "missing_token")
    try:
        claims = await run_dispatch(lambda: _verify(token.strip(), audience))
    except (ValueError, GoogleAuthError):
        # Bad signature, expired, wrong audience or wrong issuer.
        raise _refuse(401, "invalid_token") from None
    email = str(claims.get("email") or "").strip().lower()
    if claims.get("email_verified") is not True or not hmac.compare_digest(
        email.encode(), expected.encode()
    ):
        raise _refuse(403, "wrong_caller")
    return claims
