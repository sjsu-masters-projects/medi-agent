"""No real mail: transport boundaries, minimal copy and frozen retry payloads."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.clients.resend import ResendClient
from app.models.auth import CurrentUser
from app.services.email_service import EmailDeliveryService, EmailService
from app.services.email_templates import render_email, verification_email


@pytest.mark.parametrize(
    "address",
    ["morgan@accounts.mediagent.live", "x@ACCOUNTS.MEDIAGENT.LIVE", "bad\n@example.com", "bad"],
)
def test_undeliverable_addresses(address):
    assert not ResendClient.deliverable(address)


def test_template_escapes_data_and_has_plaintext():
    content = render_email(
        "Update <script>",
        ["Clinic <b>unsafe</b>"],
        action_url="https://app.example.com/profile?a=1&b=2",
        action_label="Open",
    )
    assert "<script>" not in content.html and "&lt;b&gt;" in content.html
    assert "a=1&amp;b=2" in content.html
    assert "Clinic <b>unsafe</b>" in content.text
    assert "#F3EEE6" in content.html and "#147465" in content.html


@pytest.mark.parametrize(
    "url", ["javascript:alert(1)", "https://" + "user:example-only" + "@app.example.com", "http://app.example.com"]
)
def test_template_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        render_email("Update", [], action_url=url, action_label="Open")


def test_spanish_verification_does_not_enable_notices():
    content = verification_email("123456", "https://app.example.com/profile", "es-MX")
    assert 'lang="es-MX"' in content.html and "123456" in content.text
    assert "no activa" in content.text


def test_transport_requires_provider_id_and_redacts_errors(caplog):
    client = ResendClient()
    client.enabled = True
    payload = {"from": "accounts@example.com", "to": ["demo@example.com"]}
    with patch("app.clients.resend.resend.Emails.send", return_value={}) as send:
        assert client.send(payload, "stable-key") is None
        send.assert_called_once_with(payload, {"idempotency_key": "stable-key"})
    with patch(
        "app.clients.resend.resend.Emails.send",
        side_effect=Exception("secret-token demo@example.com"),
    ):
        assert client.send(payload, "stable-key") is None
    assert "secret-token" not in caplog.text and "demo@example.com" not in caplog.text


def test_transport_acceptance_not_delivery():
    client = ResendClient()
    client.enabled = True
    with patch("app.clients.resend.resend.Emails.send", return_value={"id": "provider-id"}):
        assert (
            client.send({"from": "a@example.com", "to": ["b@example.com"]}, "key") == "provider-id"
        )


def test_frozen_payload_reused_without_retranslation():
    service = EmailDeliveryService(MagicMock())
    payload = {"from": "sender@example.com", "to": ["owner@example.com"], "text": "Frozen"}
    assert service._payload({"payload": payload, "locale": "es-MX"}) == payload


def test_event_email_omits_clinical_metadata():
    service = EmailDeliveryService(MagicMock())
    with patch("app.services.email_service.settings") as config:
        config.patient_portal_url = "https://app.example.com"
        row = {
            "role": "patient",
            "locale": "es-MX",
            "email": "owner@example.com",
            "event": {
                "event_type": "care_plan_published",
                "category": "care_plans",
                "patient_id": str(uuid4()),
                "metadata": {"diagnosis": "private-diagnosis", "dose": "500mg"},
            },
        }
        payload = service._payload(row)
    assert "private-diagnosis" not in payload["html"] and "500mg" not in payload["text"]
    assert "plan de cuidado" in payload["subject"]


def test_verification_hash_scoped_to_actor():
    a = EmailService(MagicMock(), CurrentUser(id=uuid4(), email="a@example.com", role="patient"))
    b = EmailService(MagicMock(), CurrentUser(id=uuid4(), email="b@example.com", role="patient"))
    assert a._hash("123456") != b._hash("123456")
