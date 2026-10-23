"""SAFE-002: every place the safety floor or override can act has an audit path.

The guard lists every source file that calls the floor or an override. A new call site fails
this test until it is added here with the way its decisions reach `chat_turn_safety_audits`
(or a reason it needs none), so a path cannot raise urgency without a durable trace.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from tests.unit.intake.test_service import service

from app.models.symptom_intake import IntakeStart
from app.services.chat_safety_service import (
    ChatSafetyService,
    drain_background_audits,
    floor_audit_payload,
    utterance_audit_turn_id,
)

SRC = Path(__file__).resolve().parents[3] / "src/app"
CALL = re.compile(
    r"\b(deterministic_safety_floor|apply_safety_override|evaluate_intake_safety"
    r"|override_rule_id|floor_guidance)\("
)

# file -> how its decisions are audited, or why it does not need an audit.
CALL_SITES = {
    "adk/chat_runtime.py": "typed, document and worker chat: classification carries override_rule; "
    "routers/chat.py::_process_chat_message audits it (record_audit_safely)",
    "adk/plugins/safety_floor.py": "halts a run only after routers/chat.py already audited the "
    "floor halt in _send_safety_turn; the plugin itself persists nothing",
    "routers/chat.py": "floor halts: _send_safety_turn (record_floor_audit_safely); "
    "raised urgency: _process_chat_message (record_audit_safely)",
    "safety/escalation.py": "defines the override; its result is audited by chat_runtime/chat.py",
    "safety/intake_gate.py": "defines the intake floor; callers audit (chat.py, symptom intake)",
    "safety/symptom_offer.py": "reads the floor to suppress an offer; decides nothing",
    "safety/triage_floor.py": "defines the floor",
    "services/ai_evaluation.py": "offline synthetic evaluation; no patient turn",
    "services/chat_turn_service.py": "display guidance for a recovered turn; the turn itself was "
    "audited when it ran",
    "services/symptom_intake_service.py": "start and interrupt call _audit_floor "
    "(schedule_floor_audit)",
    "services/voice_live.py": "spoken floor hit: on_safety_floor hook -> routers/voice.py "
    "audit_floor (schedule_floor_audit)",
}


def test_every_floor_or_override_call_site_is_accounted_for() -> None:
    found = {
        str(path.relative_to(SRC)) for path in SRC.rglob("*.py") if CALL.search(path.read_text())
    }
    assert found == set(CALL_SITES), (
        "A safety-floor or override call site changed. Add it to CALL_SITES with its audit path: "
        f"{sorted(found ^ set(CALL_SITES))}"
    )


def test_the_audited_call_sites_really_reference_the_audit_writers() -> None:
    expectations = {
        "routers/chat.py": ("record_floor_audit_safely", "record_audit_safely"),
        "services/symptom_intake_service.py": ("schedule_floor_audit",),
        "services/voice_live.py": ("_on_safety_floor",),
        "routers/voice.py": ("schedule_floor_audit",),
    }
    for relative, needles in expectations.items():
        text = (SRC / relative).read_text()
        for needle in needles:
            assert needle in text, f"{relative} no longer calls {needle}"


def test_a_floor_audit_payload_holds_rule_version_urgency_and_outcome_only() -> None:
    assert floor_audit_payload("urgent_medication_error", "urgent") == {
        "safety_rule": "urgent_medication_error",
        "rule_version": "triage-floor/1",
        "model_urgency": "routine",
        "final_urgency": "urgent",
        "outcome": "urgency_raised",
        "escalation_required": True,
    }


def test_a_voice_audit_id_is_stable_per_patient_and_utterance() -> None:
    first = utterance_audit_turn_id("p1", "u1")
    assert UUID(first) and first == utterance_audit_turn_id("p1", "u1")
    assert first != utterance_audit_turn_id("p2", "u1")
    assert first != utterance_audit_turn_id("p1", "u2")


@pytest.mark.asyncio
async def test_an_audit_outage_neither_raises_nor_blocks_the_caller() -> None:
    db = MagicMock()
    db.rpc().execute.side_effect = RuntimeError("synthetic outage")
    service_ = ChatSafetyService(db)
    assert (
        await service_.record_floor_audit_safely(
            "p", str(uuid4()), "urgent_medication_error", "urgent"
        )
        is False
    )
    service_.schedule_floor_audit("p", str(uuid4()), "urgent_medication_error", "urgent")
    await drain_background_audits()  # completes without raising


@pytest.mark.asyncio
async def test_a_scheduled_audit_calls_the_idempotent_rpc_with_server_identity() -> None:
    db = MagicMock()
    db.rpc().execute.return_value = SimpleNamespace(data={"turn_id": "t"})
    db.rpc.reset_mock()
    ChatSafetyService(db).schedule_floor_audit("p", "t", "emergency_symptom_keyword", "emergency")
    await drain_background_audits()
    name, args = db.rpc.call_args.args
    assert name == "record_chat_turn_safety_audit"
    assert args["p_patient_id"] == "p" and args["p_turn_id"] == "t"
    assert args["p_payload"]["safety_rule"] == "emergency_symptom_keyword"
    assert "content" not in args["p_payload"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("I cannot breathe", "emergency_symptom_keyword"),
        ("I took my metformin twice", "urgent_medication_error"),
    ],
)
async def test_symptom_intake_start_audits_a_floor_halt(monkeypatch, text, rule) -> None:
    svc = service()
    source_id = str(uuid4())
    svc._source = AsyncMock(
        return_value={"id": source_id, "content": text, "language": "en-US", "session_id": "d"}
    )
    monkeypatch.setattr(
        ChatSafetyService, "record_safely", AsyncMock(return_value={"persistence_status": "saved"})
    )
    audit = AsyncMock(return_value=True)
    monkeypatch.setattr(ChatSafetyService, "record_audit_safely", audit)

    result = await svc.start(IntakeStart(source_message_id=uuid4(), session_id="d"))
    await drain_background_audits()

    assert result["status"] == "interrupted_safety"
    _patient, turn_id, payload = audit.await_args.args
    assert turn_id == source_id
    assert payload["safety_rule"] == rule and payload["outcome"] == "urgency_raised"
    assert text not in str(payload)


@pytest.mark.asyncio
async def test_symptom_intake_interrupt_audits_and_survives_an_audit_outage(monkeypatch) -> None:
    svc = service()
    intake_id = str(uuid4())
    svc._call = AsyncMock(return_value={"intake_id": intake_id, "status": "interrupted_safety"})
    svc.describe = MagicMock(return_value={"status": "interrupted_safety"})
    audit = AsyncMock(side_effect=RuntimeError("synthetic outage"))
    monkeypatch.setattr(ChatSafetyService, "record_audit_safely", audit)
    from app.safety.intake_gate import evaluate_intake_safety

    decision = evaluate_intake_safety("I want to kill myself", "en-US")
    assert decision is not None
    result = await svc.interrupt({"id": intake_id, "revision": 1}, {}, decision)
    await drain_background_audits()

    assert result["status"] == "interrupted_safety"  # the patient's answer is unaffected
    assert audit.await_args.args[1] == intake_id
    assert audit.await_args.args[2]["safety_rule"] == "emergency_mental_health_keyword"
