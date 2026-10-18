import time
from types import SimpleNamespace

import jwt
import pytest

from app.core.exceptions import AuthenticationError
from app.services.auth_service import AuthService


def _token(exp: int) -> str:
    return jwt.encode({"exp": exp, "sub": "u"}, "k", algorithm="HS256")


def _session(**kwargs):
    base = {
        "access_token": "not-a-jwt",
        "refresh_token": "r",
        "expires_at": None,
        "expires_in": None,
    }
    return SimpleNamespace(**{**base, **kwargs})


def test_uses_provider_expires_at():
    assert AuthService._resolve_expires_at(_session(expires_at=1_900_000_000)) == 1_900_000_000


@pytest.mark.parametrize("missing", [None, 0])
def test_falls_back_to_expires_in(missing):
    before = int(time.time())
    value = AuthService._resolve_expires_at(_session(expires_at=missing, expires_in=3600))
    assert before + 3600 <= value <= int(time.time()) + 3600


def test_falls_back_to_access_token_exp():
    token = _token(1_950_000_000)
    assert AuthService._resolve_expires_at(_session(access_token=token)) == 1_950_000_000


def test_never_returns_zero():
    with pytest.raises(AuthenticationError):
        AuthService._resolve_expires_at(_session())


def test_format_session_includes_derived_expiry():
    response = SimpleNamespace(
        session=_session(access_token=_token(1_950_000_000)),
        user=SimpleNamespace(
            id="11111111-1111-1111-1111-111111111111",
            email="a@example.com",
            app_metadata={"user_role": "patient"},
            created_at="2026-01-01",
        ),
    )
    out = AuthService._format_session(response, expected_role="patient")
    assert out["tokens"]["expires_at"] == 1_950_000_000
