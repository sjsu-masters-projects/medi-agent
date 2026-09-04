"""Security-sensitive SMART launch helper tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from app.config import settings
from app.core.exceptions import ExternalServiceError, ValidationError
from app.services.smart_launch_service import SmartLaunchService


def test_code_challenge_is_s256_and_state_digest_is_not_reversible() -> None:
    assert (
        SmartLaunchService._code_challenge("verifier")
        == "iMnq5o6zALKXGivsnlom_0F5_WYda32GHkxlV7mq7hQ"
    )
    assert SmartLaunchService._digest("state") != "state"
    assert len(SmartLaunchService._digest("state")) == 64


def test_issuer_requires_https_base_url_and_allowlist() -> None:
    assert (
        SmartLaunchService._validate_issuer("https://launch.smarthealthit.org/v/r4/fhir/")
        == "https://launch.smarthealthit.org/v/r4/fhir"
    )
    with pytest.raises(ValidationError, match="HTTPS"):
        SmartLaunchService._validate_issuer("http://sandbox.example/fhir")
    with pytest.raises(ValidationError, match="base URL"):
        SmartLaunchService._validate_issuer("https://sandbox.example/fhir?bad=true")
    with pytest.raises(ValidationError, match="not enabled"):
        SmartLaunchService._validate_issuer("https://sandbox.example/fhir")


def test_pagination_cannot_escape_discovered_issuer() -> None:
    bundle = {"link": [{"relation": "next", "url": "https://attacker.example/Bundle?page=2"}]}

    with pytest.raises(ExternalServiceError, match="Rejected pagination"):
        SmartLaunchService._next_bundle_url(bundle, "https://sandbox.example/fhir")


def test_expiry_handles_past_and_future_timestamps() -> None:
    past = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    future = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()

    assert SmartLaunchService._expired(past)
    assert not SmartLaunchService._expired(future)


def test_token_response_rejects_invalid_expiry_scope_and_audience() -> None:
    with pytest.raises(ExternalServiceError, match="expiry"):
        SmartLaunchService._validate_token_response(
            {"access_token": "token"}, issuer="https://sandbox.example"
        )
    with pytest.raises(ExternalServiceError, match="scope"):
        SmartLaunchService._validate_token_response(
            {"access_token": "token", "expires_in": 300, "scope": "patient/Observation.read"},
            issuer="https://sandbox.example",
        )
    with pytest.raises(ExternalServiceError, match="audience"):
        SmartLaunchService._validate_token_response(
            {"access_token": "token", "expires_in": 300, "aud": "https://other.example"},
            issuer="https://sandbox.example",
        )
    with pytest.raises(ExternalServiceError, match="scope is malformed"):
        SmartLaunchService._validate_token_response(
            {"access_token": "token", "expires_in": 300, "scope": ["patient/Patient.read"]},
            issuer="https://sandbox.example",
        )
    with pytest.raises(ExternalServiceError, match="audience is malformed"):
        SmartLaunchService._validate_token_response(
            {"access_token": "token", "expires_in": 300, "aud": ["https://sandbox.example"]},
            issuer="https://sandbox.example",
        )


def test_ehr_launch_encrypts_opaque_context_and_uses_ehr_scope(monkeypatch) -> None:
    key = Fernet.generate_key().decode()
    db = MagicMock()
    insert = db.table.return_value.insert.return_value
    insert.execute.return_value = SimpleNamespace(data=[{"id": str(uuid4())}])
    service = SmartLaunchService(db)
    monkeypatch.setattr(settings, "smart_client_id", "sandbox-client")
    monkeypatch.setattr(settings, "smart_state_encryption_key", key)
    monkeypatch.setattr(settings, "smart_redirect_uri", "https://api.example/smart/callback")
    monkeypatch.setattr(settings, "smart_allowed_issuers", "https://sandbox.example/fhir")
    monkeypatch.setattr(settings, "smart_scopes", "patient/Patient.read patient/Condition.read")
    monkeypatch.setattr(service, "_require_assignment", lambda *_: None)
    monkeypatch.setattr(
        service,
        "_discover",
        lambda _: {
            "authorization_endpoint": "https://sandbox.example/authorize",
            "token_endpoint": "https://sandbox.example/token",
        },
    )

    result = service.start_launch(
        clinician_id=uuid4(),
        patient_id=uuid4(),
        issuer="https://sandbox.example/fhir",
        launch_context="opaque-ehr-launch-handle",
    )

    payload = db.table.return_value.insert.call_args.args[0]
    assert payload["launch_context"] != "opaque-ehr-launch-handle"
    assert (
        Fernet(key.encode()).decrypt(payload["launch_context"].encode()).decode()
        == "opaque-ehr-launch-handle"
    )
    assert payload["requested_scopes"] == "launch patient/Patient.read patient/Condition.read"
    query = parse_qs(urlparse(result["authorization_url"]).query)
    assert query["launch"] == ["opaque-ehr-launch-handle"]
    assert query["scope"] == ["launch patient/Patient.read patient/Condition.read"]
    assert "launch/patient" not in query["scope"][0]


def test_standalone_launch_uses_patient_and_encounter_context_scopes(monkeypatch) -> None:
    monkeypatch.setattr(settings, "smart_scopes", "patient/Patient.read patient/Condition.read")

    assert SmartLaunchService._requested_scopes(None) == (
        "launch/patient launch/encounter patient/Patient.read patient/Condition.read"
    )


def test_standalone_sandbox_issuer_is_allowed_separately_from_ehr_issuers(monkeypatch) -> None:
    monkeypatch.setattr(settings, "smart_allowed_issuers", "https://ehr.example/fhir")
    monkeypatch.setattr(
        settings, "smart_standalone_issuer", "https://sandbox.example/standalone/fhir"
    )

    assert (
        SmartLaunchService._validate_issuer("https://sandbox.example/standalone/fhir/")
        == "https://sandbox.example/standalone/fhir"
    )


def test_provider_error_consumes_the_bound_launch_state(monkeypatch) -> None:
    db = MagicMock()
    service = SmartLaunchService(db)
    session = {"id": str(uuid4()), "pkce_verifier_ciphertext": "not-used"}
    monkeypatch.setattr(service, "_load_active_session", lambda _: session)

    with pytest.raises(ValidationError, match="invalid_request"):
        service.handle_callback(state="state", code=None, error="invalid_request")

    db.table.assert_called_with("smart_launch_sessions")
    update_payload = db.table.return_value.update.call_args.args[0]
    assert isinstance(update_payload["consumed_at"], str)
