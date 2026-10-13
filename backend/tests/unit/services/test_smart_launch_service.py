"""Security-sensitive SMART launch helper tests."""

from __future__ import annotations

import base64
import json
import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet

from app.config import Settings, settings
from app.core.exceptions import AuthorizationError, ExternalServiceError, ValidationError
from app.services.smart_launch_service import (
    SmartLaunchService,
    SmartProviderAuthorizationError,
    sanitize_provider_error,
)

SANDBOX_SIM_CODE = "WzMsIiIsIiIsIkFVVE8iLDAsMCwwLCIiLCIiLCIiLCIiLCIiLCIiLCIiLDAsMSwiIl0"
SANDBOX_STANDALONE_ISSUER = f"https://launch.smarthealthit.org/v/r4/sim/{SANDBOX_SIM_CODE}/fhir"


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
    assert query["aud"] == ["https://sandbox.example/fhir"]
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


def _configure_launch(monkeypatch, *, standalone_issuer: str = SANDBOX_STANDALONE_ISSUER) -> None:
    monkeypatch.setattr(settings, "smart_client_id", "sandbox-client")
    monkeypatch.setattr(settings, "smart_state_encryption_key", Fernet.generate_key().decode())
    monkeypatch.setattr(settings, "smart_redirect_uri", "https://api.example/smart/callback")
    monkeypatch.setattr(
        settings, "smart_allowed_issuers", "https://launch.smarthealthit.org/v/r4/fhir"
    )
    monkeypatch.setattr(settings, "smart_standalone_issuer", standalone_issuer)
    monkeypatch.setattr(settings, "smart_scopes", "patient/Patient.read patient/Condition.read")


def test_default_standalone_issuer_encodes_a_patient_standalone_sandbox_launch() -> None:
    issuer = Settings.model_fields["smart_standalone_issuer"].default
    assert issuer == SANDBOX_STANDALONE_ISSUER
    segment = issuer.split("/sim/", 1)[1].split("/", 1)[0]
    options = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
    # The sandbox launcher expects a positional array; index 0 is the launch type
    # (3 = patient-standalone), 14 the client type (0 = public), 15 PKCE (1 = auto).
    assert isinstance(options, list)
    assert options[0] == 3
    assert options[14] == 0
    assert options[15] == 1


def test_standalone_launch_uses_configured_sim_issuer_without_launch_handle(monkeypatch) -> None:
    _configure_launch(monkeypatch)
    db = MagicMock()
    db.table.return_value.insert.return_value.execute.return_value = SimpleNamespace(
        data=[{"id": str(uuid4())}]
    )
    http = MagicMock()
    sim_base = SANDBOX_STANDALONE_ISSUER.removesuffix("/fhir")
    http.get.return_value.json.return_value = {
        "authorization_endpoint": f"{sim_base}/auth/authorize",
        "token_endpoint": f"{sim_base}/auth/token",
    }
    service = SmartLaunchService(db, http_client=http)
    monkeypatch.setattr(service, "_require_assignment", lambda *_: None)

    result = service.start_launch(clinician_id=uuid4(), patient_id=uuid4(), issuer=None)

    http.get.assert_called_once_with(f"{SANDBOX_STANDALONE_ISSUER}/.well-known/smart-configuration")
    authorization_url = urlparse(result["authorization_url"])
    assert authorization_url.path == f"/v/r4/sim/{SANDBOX_SIM_CODE}/auth/authorize"
    query = parse_qs(authorization_url.query)
    assert "launch" not in query
    assert query["aud"] == [SANDBOX_STANDALONE_ISSUER]
    assert query["client_id"] == ["sandbox-client"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["scope"][0].split()[:2] == ["launch/patient", "launch/encounter"]
    payload = db.table.return_value.insert.call_args.args[0]
    assert payload["issuer"] == SANDBOX_STANDALONE_ISSUER
    assert payload["launch_context"] is None


def test_standalone_launch_without_issuer_requires_configuration(monkeypatch) -> None:
    _configure_launch(monkeypatch, standalone_issuer="  ")
    service = SmartLaunchService(MagicMock(), http_client=MagicMock())
    monkeypatch.setattr(service, "_require_assignment", lambda *_: None)

    with pytest.raises(ValidationError, match="standalone launch is not configured"):
        service.start_launch(clinician_id=uuid4(), patient_id=uuid4(), issuer=None)


def test_ehr_launch_without_issuer_is_rejected(monkeypatch) -> None:
    _configure_launch(monkeypatch)
    service = SmartLaunchService(MagicMock(), http_client=MagicMock())
    monkeypatch.setattr(service, "_require_assignment", lambda *_: None)

    with pytest.raises(ValidationError, match="requires the EHR issuer"):
        service.start_launch(
            clinician_id=uuid4(), patient_id=uuid4(), issuer=None, launch_context="opaque"
        )


def test_provider_error_description_is_logged_and_surfaced_sanitized(monkeypatch, caplog) -> None:
    db = MagicMock()
    service = SmartLaunchService(db)
    monkeypatch.setattr(service, "_load_active_session", lambda _: {"id": str(uuid4())})

    with (
        caplog.at_level(logging.WARNING, logger="app.services.smart_launch_service"),
        pytest.raises(SmartProviderAuthorizationError) as raised,
    ):
        service.handle_callback(
            state="state",
            code=None,
            error="invalid_request",
            error_description="Invalid launch options: SyntaxError: Unexpected end of JSON input",
        )

    expected = "invalid_request: Invalid launch options: SyntaxError: Unexpected end of JSON input"
    assert raised.value.provider_detail == expected
    assert isinstance(raised.value, ValidationError)
    record = next(r for r in caplog.records if "authorization server returned" in r.message)
    assert record.levelno == logging.WARNING
    assert expected in record.getMessage()
    assert record.smart_provider_error == expected
    update_payload = db.table.return_value.update.call_args.args[0]
    assert isinstance(update_payload["consumed_at"], str)


def test_provider_error_is_logged_even_when_state_is_not_live(monkeypatch, caplog) -> None:
    service = SmartLaunchService(MagicMock())

    def reject(_: str) -> dict[str, str]:
        raise AuthorizationError("SMART launch state is invalid or expired")

    monkeypatch.setattr(service, "_load_active_session", reject)

    with (
        caplog.at_level(logging.WARNING, logger="app.services.smart_launch_service"),
        pytest.raises(AuthorizationError),
    ):
        service.handle_callback(
            state="state", code=None, error="access_denied", error_description="User denied"
        )

    assert any("access_denied: User denied" in r.getMessage() for r in caplog.records)


def test_provider_error_sanitizer_strips_markup_opaque_values_and_length() -> None:
    opaque = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signaturepart"
    detail = sanitize_provider_error(
        "invalid_request<script>",
        f"Bad <b>request</b>\r\n code={opaque} {'x ' * 200}",
    )

    assert detail.startswith("invalid_requestscript: Bad b request /b code [redacted]")
    assert "<" not in detail and ">" not in detail and "\n" not in detail
    assert opaque not in detail
    assert len(detail) <= 200
    assert detail.endswith("...")
    assert sanitize_provider_error(None, None) == "unspecified"
    assert sanitize_provider_error("access_denied", None) == "access_denied"
