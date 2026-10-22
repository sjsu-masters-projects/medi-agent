"""Snapshot signing never confers authentication authority; synthetic keys only."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from pydantic import ValidationError as SettingsValidationError

from app.config import Settings
from app.core.exceptions import ValidationError
from app.models.auth import CurrentUser
from app.services import notification_centre_tokens as tokens


@pytest.fixture(params=[None, "synthetic-independent-notification-root-123456"])
def actor(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> CurrentUser:
    monkeypatch.setattr(
        tokens.settings, "supabase_jwt_secret", "synthetic-auth-root-12345678901234567890"
    )
    monkeypatch.setattr(tokens.settings, "notification_token_signing_secret", request.param)
    return CurrentUser(id=uuid4(), email="synthetic@example.com", role="clinician", aal="aal2")


def test_snapshot_round_trip_and_auth_key_isolation(actor: CurrentUser) -> None:
    ids = [str(uuid4())]
    token = tokens.issue_token(actor, "read", ids)
    assert tokens.read_token(actor, "read", token) == ids
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(
            token,
            tokens.settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )


@pytest.mark.parametrize("purpose", ["cursor", "action_cursor", "read"])
def test_purpose_is_bound(actor: CurrentUser, purpose: str) -> None:
    token = tokens.issue_token(actor, purpose, ["synthetic-id"])
    other = "cursor" if purpose == "read" else "read"
    with pytest.raises(ValidationError):
        tokens.read_token(actor, other, token)


def test_actor_and_role_are_bound(actor: CurrentUser) -> None:
    token = tokens.issue_token(actor, "read", [])
    other = actor.model_copy(update={"id": uuid4()})
    with pytest.raises(ValidationError):
        tokens.read_token(other, "read", token)
    with pytest.raises(ValidationError):
        tokens.read_token(actor.model_copy(update={"role": "patient"}), "read", token)


@pytest.mark.parametrize("invalid", ["expired", "audience", "issuer", "missing", "auth_signed"])
def test_invalid_claims_and_raw_auth_signatures_fail(actor: CurrentUser, invalid: str) -> None:
    token = tokens.issue_token(actor, "read", [])
    payload = jwt.decode(token, options={"verify_signature": False})
    key = tokens._signing_key()
    if invalid == "expired":
        payload["exp"] = datetime.now(UTC) - timedelta(seconds=1)
    elif invalid == "audience":
        payload["aud"] = "authenticated"
    elif invalid == "issuer":
        payload["iss"] = "synthetic-auth"
    elif invalid == "missing":
        del payload["data"]
    else:
        key = tokens.settings.supabase_jwt_secret.encode()
    with pytest.raises(ValidationError):
        tokens.read_token(actor, "read", jwt.encode(payload, key, algorithm="HS256"))


def test_root_rotation_invalidates_only_snapshots(
    actor: CurrentUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = tokens.issue_token(actor, "read", [])
    auth_root = tokens.settings.supabase_jwt_secret
    monkeypatch.setattr(
        tokens.settings,
        "notification_token_signing_secret",
        "synthetic-new-root-12345678901234567890",
    )
    with pytest.raises(ValidationError):
        tokens.read_token(actor, "read", token)
    assert tokens.settings.supabase_jwt_secret == auth_root
    assert tokens.read_token(actor, "read", tokens.issue_token(actor, "read", [])) == []


def test_same_configured_root_still_cannot_sign_an_auth_token(
    actor: CurrentUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        tokens.settings, "notification_token_signing_secret", tokens.settings.supabase_jwt_secret
    )
    token = tokens.issue_token(actor, "read", [])
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(
            token,
            tokens.settings.supabase_jwt_secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )


def test_independent_key_does_not_depend_on_auth_rotation(
    actor: CurrentUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        tokens.settings,
        "notification_token_signing_secret",
        "synthetic-independent-root-123456789012345",
    )
    token = tokens.issue_token(actor, "read", [])
    monkeypatch.setattr(
        tokens.settings, "supabase_jwt_secret", "synthetic-rotated-auth-root-12345678901234"
    )
    assert tokens.read_token(actor, "read", token) == []


@pytest.mark.parametrize("secret", ["", "too-short"])
def test_config_rejects_weak_explicit_root(secret: str) -> None:
    with pytest.raises(SettingsValidationError):
        Settings(
            _env_file=None,
            supabase_url="https://synthetic.invalid",
            supabase_anon_key="test",
            supabase_service_role_key="test",
            supabase_jwt_secret="test",
            notification_token_signing_secret=secret,
        )
