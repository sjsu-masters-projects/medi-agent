"""Small JWT helpers shared by authentication services."""

from typing import Any

import jwt


def decode_unverified_claims(token: str) -> dict[str, Any]:
    """Decode claims for non-authoritative UI/session fallbacks.

    Callers must never use this helper to authorize a request. Verified access
    tokens are handled by :mod:`app.core.security`.
    """
    return jwt.decode(token, options={"verify_signature": False})
