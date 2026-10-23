"""Persist emergency chat turns and retry independent operational alerts."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, cast
from uuid import NAMESPACE_URL, uuid4, uuid5

from supabase import Client

from app.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)

AUDIT_RULE_VERSION = "triage-floor/1"
_BACKGROUND_AUDITS: set[asyncio.Task[Any]] = set()


def floor_audit_payload(safety_rule: str, urgency: str) -> dict[str, Any]:
    """SAFE-002 audit body for a turn the deterministic floor answered. The floor ran before
    any model, so the model's urgency is `routine`. Rule id, version, urgencies and outcome
    only; never message text."""
    return {
        "safety_rule": safety_rule,
        "rule_version": AUDIT_RULE_VERSION,
        "model_urgency": "routine",
        "final_urgency": urgency,
        "outcome": "urgency_raised",
        "escalation_required": True,
    }


def utterance_audit_turn_id(patient_id: str, utterance_id: str) -> str:
    """A voice utterance has no chat turn yet; a stable id keeps the audit idempotent."""
    return str(uuid5(NAMESPACE_URL, f"mediagent:voice-utterance:{patient_id}:{utterance_id}"))


async def drain_background_audits() -> None:
    """Lets tests (and shutdown) wait for audits scheduled with `schedule_floor_audit`."""
    if _BACKGROUND_AUDITS:
        await asyncio.gather(*list(_BACKGROUND_AUDITS), return_exceptions=True)


class ChatSafetyService:
    def __init__(self, db: Client) -> None:
        self.db = db

    async def record_turn(self, patient_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """The server owns turn identity, safety rule, response and patient identity."""
        result = await asyncio.to_thread(
            self.db.rpc(
                "record_chat_safety_turn",
                {"p_patient_id": patient_id, "p_turn_id": payload["turn_id"], "p_payload": payload},
            ).execute
        )
        if not isinstance(result.data, dict):
            raise ExternalServiceError("Supabase", "Safety turn persistence unavailable")
        return cast(dict[str, Any], result.data)

    async def record_safely(self, patient_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """A storage outage cannot replace direction already shown to the patient."""
        try:
            record = await asyncio.wait_for(self.record_turn(patient_id, payload), timeout=5)
            return {**record, "persistence_status": "saved"}
        except Exception:
            logger.warning("Emergency turn persistence unavailable; direction retained")
            return self._unsaved_turn(patient_id, payload)

    @staticmethod
    def _unsaved_turn(patient_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "alert_id": payload["turn_id"],
            "persistence_status": "uncertain",
            "delivery_state": "unavailable",
            "assistant_message": {
                "id": str(uuid4()),
                "patient_id": patient_id,
                "role": "assistant",
                "content": payload["response_text"],
                "intent": payload["intent"],
                "language": payload["language"],
                "created_at": datetime.now(UTC).isoformat(),
            },
        }

    async def record_audit_safely(
        self, patient_id: str, turn_id: str, payload: dict[str, Any]
    ) -> bool:
        """SAFE-002 audit for a raised or escalated turn. Idempotent per turn id, so the one
        immediate retry (and any later redelivery of the turn) cannot duplicate a row. An
        audit outage never blocks or alters the patient's answer."""
        for _attempt in range(2):
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.db.rpc(
                            "record_chat_turn_safety_audit",
                            {
                                "p_patient_id": patient_id,
                                "p_turn_id": turn_id,
                                "p_payload": payload,
                            },
                        ).execute
                    ),
                    timeout=5,
                )
                if isinstance(result.data, dict):
                    return True
            except Exception:
                logger.warning("Safety audit persistence unavailable; turn answer unaffected")
        return False

    async def record_floor_audit_safely(
        self, patient_id: str, turn_id: str, safety_rule: str, urgency: str
    ) -> bool:
        """The audit for a floor halt on a path that does not go through the chat turn."""
        return await self.record_audit_safely(
            patient_id, turn_id, floor_audit_payload(safety_rule, urgency)
        )

    def schedule_floor_audit(
        self, patient_id: str, turn_id: str, safety_rule: str, urgency: str
    ) -> None:
        """Fire and forget: the caller's response never waits for, or fails on, the audit."""
        task = asyncio.get_running_loop().create_task(
            self.record_floor_audit_safely(patient_id, turn_id, safety_rule, urgency)
        )
        _BACKGROUND_AUDITS.add(task)
        task.add_done_callback(_BACKGROUND_AUDITS.discard)

    async def deliver_safely(self, record: dict[str, Any]) -> dict[str, Any]:
        if record["persistence_status"] != "saved":
            return {"delivery_state": "unavailable", "clinicians_notified": 0}
        try:
            delivered = await asyncio.wait_for(
                self.deliver_pending({"alert_id": record["alert_id"]}), timeout=5
            )
            if delivered:
                return delivered[0]
        except Exception:
            logger.warning("Emergency alert delivery unavailable; retained for worker retry")
        return {"delivery_state": record["delivery_state"], "clinicians_notified": 0}

    async def deliver_pending(self, options: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        options = options or {}
        result = await asyncio.to_thread(
            self.db.rpc(
                "deliver_chat_safety_alerts",
                {
                    "p_limit": min(200, max(1, int(options.get("limit", 25)))),
                    "p_alert_id": options.get("alert_id"),
                },
            ).execute
        )
        if not isinstance(result.data, list):
            raise ExternalServiceError("Supabase", "Safety alert delivery unavailable")
        return cast(list[dict[str, Any]], result.data)
