"""No real mail: transport boundaries, minimal copy and frozen retry payloads."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from postgrest.exceptions import APIError

from app.clients.resend import ResendClient
from app.core.exceptions import (
    AuthorizationError,
    ExternalServiceError,
    ServiceUnavailableError,
    ValidationError,
)
from app.models.auth import CurrentUser
from app.services.email_invitation_service import EmailInvitationService
from app.services.email_service import (
    PROVIDER_STATUS,
    EmailDeliveryService,
    EmailService,
    EmailSetupPendingError,
    email_rpc,
    idempotency_key,
)
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
        audience="patient",
    )
    assert "<script>" not in content.html and "&lt;b&gt;" in content.html
    assert "a=1&amp;b=2" in content.html
    assert "Clinic <b>unsafe</b>" in content.text
    assert "#F3EEE6" in content.html and "#147465" in content.html
    assert "#2563EB" not in content.html and "MediAgent Pro" not in content.text


CLINICIAN_BLUE = "#2563EB"  # clinician-portal --color-primary


def test_clinician_email_uses_clinician_brand():
    content = render_email(
        "Review work available",
        ["Open the portal."],
        action_url="https://clinic.example.com/alerts",
        action_label="Open alerts",
        audience="clinician",
        locale="es-MX",  # clinicians always receive English
        note="You can change optional notices in Email preferences.",
    )
    assert CLINICIAN_BLUE in content.html and "#1E293B" in content.html
    assert 'MediAgent <span class="accent" style="color:#2563EB">Pro</span>' in content.html
    assert f'bgcolor="{CLINICIAN_BLUE}"' in content.html and 'lang="en-US"' in content.html
    assert "#147465" not in content.html and "#F3EEE6" not in content.html
    assert "MediAgent Pro is a master's-project prototype" in content.text
    assert "Button not working" in content.html


def test_clinician_verification_code_is_clinician_branded():
    content = verification_email(
        "654321", "https://clinic.example.com/settings", "en-US", audience="clinician"
    )
    assert CLINICIAN_BLUE in content.html and "#147465" not in content.html
    assert "654321" in content.text and "expires in 10 minutes" in content.text
    assert "MediAgent Pro" in content.text


# A link carrying credentials must be rejected; built at runtime so no literal
# "user:password@host" URI is committed.
CREDENTIAL_URL = "https://" + ":".join(["user", "example-only"]) + "@app.example.com"


@pytest.mark.parametrize("url", ["javascript:alert(1)", CREDENTIAL_URL, "http://app.example.com"])
def test_template_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        render_email("Update", [], action_url=url, action_label="Open", audience="patient")


def test_spanish_verification_does_not_enable_notices():
    content = verification_email(
        "123456", "https://app.example.com/profile", "es-MX", audience="patient"
    )
    assert 'lang="es-MX"' in content.html and "123456" in content.text
    assert "no activa" in content.text and "Caduca en 10 minutos" in content.text
    assert "#147465" in content.html and "#2563EB" not in content.html


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


# ── Dispatch orchestration, status reconciliation and error mapping ──────────────────

USER = str(uuid4())


class FakeDB:
    """Records every email RPC and answers from per-action handlers."""

    def __init__(self, handlers: dict[str, Any], address: str | None = "owner@example.com"):
        self.handlers, self.calls = handlers, []
        self.auth = MagicMock()
        if address is None:
            error = Exception("missing")
            error.status = 404  # type: ignore[attr-defined]
            self.auth.admin.get_user_by_id.side_effect = error
        else:
            self.auth.admin.get_user_by_id.return_value = SimpleNamespace(
                user=SimpleNamespace(email=address.upper())
            )

    def rpc(self, name: str, params: dict[str, Any]) -> Any:
        action = params.get("p_action")
        payload = params.get("p_payload") or {}
        self.calls.append((action, payload))
        handler = self.handlers.get(action, {})
        data = handler(payload) if callable(handler) else handler
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=data))

    def actions(self) -> list[str]:
        return [call[0] for call in self.calls]


def claimed_row(**extra: Any) -> dict[str, Any]:
    return {
        "id": str(uuid4()),
        "lease": str(uuid4()),
        "user_id": USER,
        "kind": "verification",
        "dedupe_key": f"verify/{uuid4()}",
        "generation": 0,
        "payload": {"from": "a@example.com", "to": ["owner@example.com"], "text": "code"},
        **extra,
    }


def delivery_service(db: FakeDB, *, sender: str = "Notices <n@example.com>") -> Any:
    service = EmailDeliveryService(db)  # type: ignore[arg-type]
    service.transport.enabled = True
    service.transport.default_from_email = sender
    service.transport.clinician_onboarding_from_email = "Onboarding <o@example.com>"
    return service


@pytest.mark.asyncio
async def test_dispatch_claims_freezes_sends_and_finishes_with_hashed_key():
    row = claimed_row()
    db = FakeDB(
        {
            "claim": {"items": [row]},
            "freeze": lambda p: {"payload": row["payload"]},
            "finish": {"state": "accepted"},
            "accepted": {"items": []},
        }
    )
    service = delivery_service(db)
    with patch.object(service.transport, "send", return_value="provider-1") as send:
        counts = await service.dispatch()
    assert db.actions() == ["claim", "freeze", "finish", "accepted"]
    assert db.calls[0][1]["kinds"] == ["verification", "notice", "invitation"]
    # The Auth address is supplied for the recheck, never read from the auth schema.
    assert db.calls[1][1]["account_email"] == "owner@example.com"
    key = send.call_args.args[1]
    assert key == idempotency_key(row) and USER not in key and row["dedupe_key"] not in key
    assert db.calls[2][1]["provider_id"] == "provider-1"
    assert counts["claimed"] == 1 and counts["accepted"] == 1


def test_idempotency_key_changes_only_with_generation():
    row = claimed_row()
    assert idempotency_key(row) == idempotency_key(dict(row))
    assert idempotency_key(row) != idempotency_key({**row, "generation": 1})


@pytest.mark.asyncio
async def test_dispatch_stopped_row_is_not_sent_or_finished():
    db = FakeDB({"claim": {"items": [claimed_row()]}, "freeze": {}, "accepted": {"items": []}})
    service = delivery_service(db)
    with patch.object(service.transport, "send") as send:
        counts = await service.dispatch()
    send.assert_not_called()
    assert "finish" not in db.actions() and counts["stopped"] == 1


@pytest.mark.asyncio
async def test_deleted_account_freezes_with_empty_address():
    db = FakeDB(
        {"claim": {"items": [claimed_row()]}, "freeze": {}, "accepted": {"items": []}},
        address=None,
    )
    await delivery_service(db).dispatch()
    assert db.calls[1][1]["account_email"] == ""


@pytest.mark.asyncio
async def test_provider_failure_leaves_row_for_retry():
    db = FakeDB(
        {
            "claim": {"items": [claimed_row()]},
            "freeze": lambda p: {"payload": {"to": ["owner@example.com"]}},
            "finish": {"state": "queued"},
            "accepted": {"items": []},
        }
    )
    service = delivery_service(db)
    with patch.object(service.transport, "send", return_value=None):
        counts = await service.dispatch()
    assert db.calls[2][1]["provider_id"] is None and counts["retry"] == 1


@pytest.mark.asyncio
async def test_one_failing_row_does_not_stop_the_batch():
    rows = [claimed_row(), claimed_row()]
    attempts = iter([RuntimeError("timeout"), {"payload": {"to": ["owner@example.com"]}}])

    def freeze(_: Any) -> Any:
        value = next(attempts)
        if isinstance(value, Exception):
            raise value
        return value

    db = FakeDB(
        {"claim": {"items": rows}, "freeze": freeze, "finish": {}, "accepted": {"items": []}}
    )
    service = delivery_service(db)
    with patch.object(service.transport, "send", return_value="provider-2"):
        counts = await service.dispatch()
    assert counts["errors"] == 1 and counts["accepted"] == 1


@pytest.mark.asyncio
async def test_missing_notification_sender_claims_only_invitations():
    db = FakeDB({"claim": {"items": []}, "accepted": {"items": []}})
    await delivery_service(db, sender="").dispatch()
    assert db.calls[0][1]["kinds"] == ["invitation"]


@pytest.mark.asyncio
async def test_send_now_claims_only_the_new_row():
    row = claimed_row()
    db = FakeDB(
        {
            "claim": {"items": [row]},
            "freeze": lambda p: {"payload": row["payload"]},
            "finish": {},
        }
    )
    service = delivery_service(db)
    with patch.object(service.transport, "send", return_value="provider-3"):
        assert await service.send_now(row["id"]) is True
    assert db.calls[0] == ("claim", {"id": row["id"], "kinds": service.kinds()})
    assert "accepted" not in db.actions()


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        ("delivered", "delivered"),
        ("opened", "delivered"),
        ("clicked", "delivered"),
        ("bounced", "bounced"),
        ("complained", "complained"),
        ("canceled", "failed"),
        ("failed", "failed"),
        ("sent", "accepted"),
        ("delivery_delayed", "accepted"),
        (None, "accepted"),
    ],
)
@pytest.mark.asyncio
async def test_status_mapping(event, expected):
    assert PROVIDER_STATUS.get(event or "", "accepted") == expected
    db = FakeDB({"claim": {"items": []}, "accepted": {"items": [{"id": "1", "provider_id": "p"}]}})
    service = delivery_service(db)
    with patch.object(service.transport, "status", return_value=event):
        await service.dispatch()
    assert db.calls[-1] == ("status", {"id": "1", "provider_id": "p", "state": expected})


@pytest.mark.asyncio
async def test_sending_only_key_stops_status_polling_once(caplog):
    from resend.exceptions import ResendError

    db = FakeDB(
        {
            "claim": {"items": []},
            "accepted": {
                "items": [{"id": "1", "provider_id": "p"}, {"id": "2", "provider_id": "q"}]
            },
        }
    )
    service = delivery_service(db)
    denied = ResendError(401, "restricted_api_key", "restricted", "use a full key")
    with patch("app.clients.resend.resend.Emails.get", side_effect=denied) as get:
        await service.dispatch()
        await service.dispatch()
    assert get.call_count == 1
    assert "status" not in db.actions()
    assert caplog.text.count("full-access provider key") == 1


@pytest.mark.parametrize(
    ("hint", "error", "text"),
    [
        ("invitation_invalid", ValidationError, "invalid or has expired"),
        ("invitation_wrong_account", AuthorizationError, "different email address"),
        ("existing_membership", ValidationError, "already belongs to a clinic"),
        ("synthetic_address", ValidationError, "Demo login addresses"),
        ("verify_first", ValidationError, "Verify your email"),
        ("admin_required", AuthorizationError, "clinic admin"),
    ],
)
@pytest.mark.asyncio
async def test_operation_errors_map_to_accurate_messages(hint, error, text):
    db = MagicMock()
    db.rpc.return_value.execute.side_effect = APIError(
        {"code": "22023", "message": "x", "hint": hint, "details": None}
    )
    with pytest.raises(error) as raised:
        await email_rpc(db, "op", {})
    assert text in raised.value.message


@pytest.mark.parametrize("code", ["PGRST202", "42883", "PGRST205"])
@pytest.mark.asyncio
async def test_missing_schema_is_setup_pending(code):
    db = MagicMock()
    db.rpc.return_value.execute.side_effect = APIError(
        {"code": code, "message": "missing", "hint": None, "details": None}
    )
    with pytest.raises(EmailSetupPendingError) as raised:
        await email_rpc(db, "op", {})
    assert isinstance(raised.value, ServiceUnavailableError)


@pytest.mark.asyncio
async def test_transport_errors_are_sanitized(caplog):
    db = MagicMock()
    db.rpc.return_value.execute.side_effect = TimeoutError("owner@example.com timed out")
    with pytest.raises(ExternalServiceError):
        await email_rpc(db, "op", {})
    assert "owner@example.com" not in caplog.text


@pytest.mark.asyncio
async def test_preferences_report_unavailable_until_migrated():
    db = FakeDB({})
    db.rpc = MagicMock()  # type: ignore[method-assign]
    db.rpc.return_value.execute.side_effect = APIError(
        {"code": "PGRST202", "message": "missing", "hint": None, "details": None}
    )
    actor = CurrentUser(id=uuid4(), email="owner@example.com", role="patient")
    value = await EmailService(db, actor).preferences()  # type: ignore[arg-type]
    assert value.available is False and value.verified is False


@pytest.mark.asyncio
async def test_challenge_sends_only_this_accounts_new_row():
    outbox = str(uuid4())
    db = FakeDB({})
    db.rpc = MagicMock()  # type: ignore[method-assign]
    responses = [
        {"email": "owner@example.com", "verified": False, "synthetic": False, "preferences": {}},
        {"status": "queued", "outbox_id": outbox},
    ]
    db.rpc.return_value.execute.side_effect = [SimpleNamespace(data=r) for r in responses]
    db.table = MagicMock()  # type: ignore[attr-defined]
    db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = SimpleNamespace(
        data={"preferred_language": "es-MX"}
    )
    actor = CurrentUser(id=uuid4(), email="owner@example.com", role="patient")
    with (
        patch("app.services.email_service.ResendClient") as transport,
        patch("app.services.email_service.EmailDeliveryService") as delivery,
    ):
        transport.return_value.enabled = True
        transport.return_value.default_from_email = "n@example.com"
        transport.return_value.payload.return_value = {"to": ["owner@example.com"]}
        delivery.return_value.send_now = AsyncMock(return_value=True)
        result = await EmailService(db, actor).challenge()  # type: ignore[arg-type]
    assert result == {"status": "queued"}
    delivery.return_value.send_now.assert_awaited_once_with(outbox)
    delivery.return_value.dispatch.assert_not_called()
    # The address comes from Auth and every account call carries it.
    params = db.rpc.call_args_list[-1].args[1]
    assert params["p_payload"]["account_email"] == "owner@example.com"
    content = transport.return_value.payload.call_args.args[0]
    assert "#147465" in content.html and "Caduca en 10 minutos" in content.text


@pytest.mark.asyncio
async def test_clinician_challenge_uses_clinician_brand():
    db = FakeDB({})
    db.rpc = MagicMock()  # type: ignore[method-assign]
    responses = [
        {"email": "dr@example.com", "verified": False, "synthetic": False, "preferences": {}},
        {"status": "queued", "outbox_id": str(uuid4())},
    ]
    db.rpc.return_value.execute.side_effect = [SimpleNamespace(data=r) for r in responses]
    actor = CurrentUser(id=uuid4(), email="dr@example.com", role="clinician")
    with (
        patch("app.services.email_service.ResendClient") as transport,
        patch("app.services.email_service.EmailDeliveryService") as delivery,
    ):
        transport.return_value.enabled = True
        transport.return_value.default_from_email = "n@example.com"
        transport.return_value.payload.return_value = {"to": ["dr@example.com"]}
        delivery.return_value.send_now = AsyncMock(return_value=True)
        await EmailService(db, actor).challenge()  # type: ignore[arg-type]
    content = transport.return_value.payload.call_args.args[0]
    assert CLINICIAN_BLUE in content.html and "#147465" not in content.html
    assert "MediAgent Pro" in content.text and "/settings" in content.text


@pytest.mark.asyncio
async def test_clinician_invitation_uses_clinician_brand():
    service = EmailInvitationService(MagicMock())
    service.operation = AsyncMock(return_value={"status": "pending"})  # type: ignore[method-assign]
    with patch("app.services.email_invitation_service.ResendClient") as transport:
        transport.return_value.deliverable.return_value = True
        transport.return_value.payload.return_value = {}
        await service.create(uuid4(), "dr@example.com", "clinician", "Demo Clinic")
    content = transport.return_value.payload.call_args.args[0]
    assert CLINICIAN_BLUE in content.html and "#147465" not in content.html
    assert "MediAgent Pro" in content.text and "expires in seven days" in content.text


def test_notice_links_carry_no_identifiers():
    service = EmailDeliveryService(MagicMock())
    conversation = str(uuid4())
    for role, path in (("patient", "/notifications"), ("clinician", "/alerts")):
        with patch("app.services.email_service.settings") as config:
            config.patient_portal_url = "https://app.example.com"
            config.clinician_portal_url = "https://clinic.example.com"
            payload = service._payload(
                {
                    "role": role,
                    "locale": "en-US",
                    "email": "owner@example.com",
                    "event": {
                        "event_type": "message_received",
                        "category": "messages",
                        "source_id": conversation,
                        "metadata": {"conversation_id": conversation},
                    },
                }
            )
        assert conversation not in payload["html"] and conversation not in payload["text"]
        assert f"example.com{path}" in payload["text"]
        clinician = role == "clinician"
        assert (CLINICIAN_BLUE in payload["html"]) is clinician
        assert ("#147465" in payload["html"]) is not clinician
        assert ("MediAgent Pro" in payload["text"]) is clinician


def test_dedicated_code_secret_is_preferred():
    actor = CurrentUser(id=uuid4(), email="a@example.com", role="patient")
    service = EmailService(MagicMock(), actor)
    with patch("app.services.email_service.settings") as config:
        config.email_code_hmac_secret = ""
        config.supabase_jwt_secret = "jwt-secret"
        fallback = service._hash("123456")
        config.email_code_hmac_secret = "dedicated-secret"
        dedicated = service._hash("123456")
    assert fallback != dedicated
