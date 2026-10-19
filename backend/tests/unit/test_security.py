from types import SimpleNamespace

import pytest
from jwt import PyJWTError as JWTError

from app.core import security


def test_decode_supabase_token_supports_hs256(monkeypatch):
    monkeypatch.setattr(
        security,
        "settings",
        SimpleNamespace(supabase_url="https://demo.supabase.co", supabase_jwt_secret="test-secret"),
    )
    monkeypatch.setattr(security.jwt, "get_unverified_header", lambda _token: {"alg": "HS256"})

    captured: dict[str, object] = {}

    def fake_decode(token, key, algorithms, audience, issuer, leeway):
        captured["token"] = token
        captured["key"] = key
        captured["algorithms"] = algorithms
        captured["audience"] = audience
        captured["issuer"] = issuer
        captured["leeway"] = leeway
        return {"sub": "11111111-1111-1111-1111-111111111111", "user_role": "clinician"}

    monkeypatch.setattr(security.jwt, "decode", fake_decode)

    payload = security._decode_supabase_token("token-value")

    assert payload["user_role"] == "clinician"
    assert captured["key"] == "test-secret"
    assert captured["algorithms"] == ["HS256"]
    assert captured["audience"] == "authenticated"
    assert captured["issuer"] == "https://demo.supabase.co/auth/v1"


def test_decode_supabase_token_supports_es256_via_jwks(monkeypatch):
    monkeypatch.setattr(
        security,
        "settings",
        SimpleNamespace(supabase_url="https://demo.supabase.co", supabase_jwt_secret="unused"),
    )
    monkeypatch.setattr(
        security.jwt,
        "get_unverified_header",
        lambda _token: {"alg": "ES256", "kid": "key-123"},
    )
    monkeypatch.setattr(security, "_find_jwks_key", lambda kid: {"kid": kid, "kty": "EC"})
    monkeypatch.setattr(security.PyJWK, "from_dict", lambda key, algorithm: key)

    captured: dict[str, object] = {}

    def fake_decode(token, key, algorithms, audience, issuer, leeway):
        captured["token"] = token
        captured["key"] = key
        captured["algorithms"] = algorithms
        captured["audience"] = audience
        captured["issuer"] = issuer
        captured["leeway"] = leeway
        return {"sub": "22222222-2222-2222-2222-222222222222", "user_role": "patient"}

    monkeypatch.setattr(security.jwt, "decode", fake_decode)

    payload = security._decode_supabase_token("token-value")

    assert payload["user_role"] == "patient"
    assert captured["algorithms"] == ["ES256"]
    assert isinstance(captured["key"], dict)
    assert captured["issuer"] == "https://demo.supabase.co/auth/v1"


def test_decode_supabase_token_rejects_unknown_alg(monkeypatch):
    monkeypatch.setattr(security.jwt, "get_unverified_header", lambda _token: {"alg": "none"})

    with pytest.raises(JWTError, match="Unsupported token signing algorithm"):
        security._decode_supabase_token("token-value")


def _hs256_token(exp_offset_seconds: int) -> str:
    import time

    import jwt

    return jwt.encode(
        {
            "aud": "authenticated",
            "exp": int(time.time()) + exp_offset_seconds,
            "iss": "https://demo.supabase.co/auth/v1",
            "sub": "11111111-1111-1111-1111-111111111111",
        },
        "test-secret",
        algorithm="HS256",
    )


def test_decode_supabase_token_allows_30_seconds_of_clock_skew(monkeypatch):
    monkeypatch.setattr(
        security,
        "settings",
        SimpleNamespace(supabase_url="https://demo.supabase.co", supabase_jwt_secret="test-secret"),
    )

    # Expired 10 seconds ago: inside the leeway, still accepted.
    assert security._decode_supabase_token(_hs256_token(-10))["sub"].startswith("1111")

    # Expired 2 minutes ago: beyond the leeway, rejected.
    with pytest.raises(JWTError):
        security._decode_supabase_token(_hs256_token(-120))
