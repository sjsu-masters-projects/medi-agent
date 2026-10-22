from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ExternalServiceError
from app.services.a2a_retry_worker import A2ARetryWorker
from app.services.chat_safety_service import ChatSafetyService


@pytest.mark.asyncio
async def test_record_passes_only_server_patient_and_stable_turn_identity():
    db = MagicMock()
    db.rpc().execute.return_value = SimpleNamespace(data={"alert_id": "turn"})
    result = await ChatSafetyService(db).record_turn(
        "patient", {"turn_id": "turn", "content": "Synthetic"}
    )
    assert result == {"alert_id": "turn"}
    db.rpc.assert_called_with(
        "record_chat_safety_turn",
        {
            "p_patient_id": "patient",
            "p_turn_id": "turn",
            "p_payload": {"turn_id": "turn", "content": "Synthetic"},
        },
    )


@pytest.mark.asyncio
async def test_empty_delivery_response_is_failure_not_a_sent_alert():
    db = MagicMock()
    db.rpc().execute.return_value = SimpleNamespace(data=None)
    with pytest.raises(ExternalServiceError):
        await ChatSafetyService(db).deliver_pending()


@pytest.mark.asyncio
async def test_worker_redrives_safety_without_an_adr_task():
    worker = A2ARetryWorker(MagicMock())
    worker._safety_service.deliver_pending = AsyncMock(return_value=[])
    worker._service.process_due_retries = AsyncMock(
        side_effect=lambda _limit: worker._stop_event.set()
        or {
            "scanned": 0,
        }
    )
    await worker._run_loop()
    worker._safety_service.deliver_pending.assert_awaited_once_with({"limit": 25})


@pytest.mark.asyncio
async def test_safety_delivery_failure_does_not_disable_other_retries_or_log_content(caplog):
    worker = A2ARetryWorker(MagicMock())
    worker._safety_service.deliver_pending = AsyncMock(
        side_effect=RuntimeError("private synthetic content")
    )
    await worker._deliver_safety_alerts()
    assert "pending records retained" in caplog.text
    assert "private synthetic content" not in caplog.text


@pytest.mark.asyncio
async def test_audit_is_retried_once_and_reports_failure_without_raising():
    db = MagicMock()
    db.rpc().execute.side_effect = [
        RuntimeError("Synthetic outage"),
        SimpleNamespace(data={"ok": 1}),
    ]
    service = ChatSafetyService(db)
    assert await service.record_audit_safely("patient", "turn", {"outcome": "urgency_raised"})
    db.rpc().execute.side_effect = RuntimeError("Synthetic outage")
    assert not await service.record_audit_safely("patient", "turn", {})


@pytest.mark.parametrize(
    ("message", "model", "final", "expected"),
    [
        ("I took my metformin twice", "routine", "urgent", "urgent_medication_error"),
        ("tomé dos veces mi metformina", "routine", "urgent", "urgent_medication_error"),
        ("I have crushing chest pain", "urgent", "emergency", "emergency_symptom_keyword"),
        ("I have a rash after this pill", "routine", "urgent", "adverse_effect_signal"),
        ("I took my metformin twice", "urgent", "urgent", None),
        ("What time does the clinic open?", "routine", "routine", None),
    ],
)
def test_override_rule_id_names_the_rule_that_raised_urgency(message, model, final, expected):
    from app.safety.escalation import override_rule_id

    assert override_rule_id(message, model, final) == expected
