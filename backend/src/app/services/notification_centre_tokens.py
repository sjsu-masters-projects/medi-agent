"""Short-lived, actor-bound snapshots prevent bulk reads consuming new arrivals."""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.config import settings
from app.core.exceptions import ValidationError
from app.models.auth import CurrentUser

_AUDIENCE = "mediagent-notification-centre"
_ISSUER = "mediagent-notification-snapshot"


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
        settings.supabase_jwt_secret,
        algorithm="HS256",
    )


def read_token(actor: CurrentUser, purpose: str, token: str) -> Any:
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
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
