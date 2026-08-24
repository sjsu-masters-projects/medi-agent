"""Security-sensitive SMART launch helper tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import ExternalServiceError, ValidationError
from app.services.smart_launch_service import SmartLaunchService


def test_code_challenge_is_s256_and_state_digest_is_not_reversible() -> None:
    assert SmartLaunchService._code_challenge("verifier") == "iMnq5o6zALKXGivsnlom_0F5_WYda32GHkxlV7mq7hQ"
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
        SmartLaunchService._validate_token_response({"access_token": "token"}, issuer="https://sandbox.example")
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
