"""Short-lived, actor-bound snapshots prevent bulk reads consuming new arrivals."""

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.config import settings
from app.core.exceptions import ValidationError
from app.models.auth import CurrentUser

_AUDIENCE = "mediagent-notification-centre"
_ISSUER = "mediagent-notification-snapshot"


def _signing_key() -> bytes:
    """Separate snapshots from login JWTs even before an independent key is set.

    Derive from either secret, so accidentally configuring the same root secret
    cannot turn notification snapshots into authentication tokens. All API
    replicas must use the same root. Never accept the legacy raw JWT key.
    """
    root = settings.notification_token_signing_secret or settings.supabase_jwt_secret
    return hmac.digest(
        root.encode("utf-8"), b"mediagent:notification-centre:snapshot:v1", hashlib.sha256
    )


def issue_token(actor: CurrentUser, purpose: str, data: Any) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(actor.id),
            "role": actor.role,
            "purpose": purpose,
            "data": data,
            "aud": _AUDIENCE,
            "iss": _ISSUER,
            "iat": now,
            "exp": now + timedelta(minutes=15),
        },
        _signing_key(),
        algorithm="HS256",
    )


def read_token(actor: CurrentUser, purpose: str, token: str) -> Any:
    try:
        payload = jwt.decode(
            token,
            _signing_key(),
            algorithms=["HS256"],
            audience=_AUDIENCE,
            issuer=_ISSUER,
            options={"require": ["sub", "role", "purpose", "data", "exp", "iat"]},
        )
        if (payload["sub"], payload["role"], payload["purpose"]) != (
            str(actor.id),
            actor.role,
            purpose,
        ):
            raise ValueError("Snapshot scope mismatch")
        return payload["data"]
    except (jwt.PyJWTError, ValueError, KeyError):
        raise ValidationError(
            "Notification view expired or invalid. Refresh and try again."
        ) from None
