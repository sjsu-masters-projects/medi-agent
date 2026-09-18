"""Record how the coordinator classified this turn, as a typed decision.

The websocket contract carries an `intent` and an `urgency` on every turn, and the portal
renders from them. A model cannot be asked for that as free prose, and it must not be
inferred from the reply text afterwards — parsing an answer to work out what question was
asked is how a label stops describing the thing it labels.

**Why a tool rather than `output_schema`.** Measured on Vertex, gpt-oss violated an
accepted JSON schema in 3 of 10 trials where Gemini violated it in 0 of 10, and its model
card lists function calling as supported. A tool call is the shape it honours. The
coordinator therefore reports its decision by calling this, and the turn still produces an
answer if it does not.

**Why the state key is not `temp:`-scoped.** Measured on adk 2.9.1: a `temp:` key is
correctly stripped before persistence, but it also never appears in
`event.actions.state_delta`, which is the only place the caller can read it during a
streaming turn. A plain key does appear there. The staleness that `temp:` would have
prevented is handled instead by the caller reading **only this turn's delta** and never
session state, so a value left over from a previous turn is not merely unlikely to be
read — there is no code path that reads it.

Nothing here decides safety. An emergency was already answered by `SafetyFloorPlugin`
before any agent ran, and escalation is re-applied deterministically at the boundary by
`app.safety.apply_safety_override`, which may raise an urgency and never lower one. So a
model that under-calls urgency cannot talk the turn down.
"""

from __future__ import annotations

import logging
from typing import Any, get_args

from app.safety import IntentType, UrgencyType

logger = logging.getLogger(__name__)

TRIAGE_DECISION_STATE_KEY = "triage_decision"
"""Session-state key the decision is written to, and read back from this turn's delta."""

VALID_INTENTS: frozenset[str] = frozenset(get_args(IntentType))
VALID_URGENCIES: frozenset[str] = frozenset(get_args(UrgencyType))
"""Derived from the shared literals rather than restated.

A second copy of these spellings would drift from `app.safety`, and the failure would be
a classification silently rejected at the boundary rather than an import error.
"""


async def submit_triage_decision(
    intent: str,
    urgency: str,
    reason: str,
    tool_context: Any,
) -> dict[str, Any]:
    """Record how you classified this patient message. Call this once, before answering.

    Args:
        intent: One of symptom, medication_question, schedule, document_question,
            mental_health, general.
        urgency: One of routine, urgent, emergency.
        reason: One short sentence on why, for the clinician record. Do not put the
            patient's own words here.
        tool_context: Supplied by the runtime; not part of your request.
    """
    normalized_intent = (intent or "").strip().lower()
    normalized_urgency = (urgency or "").strip().lower()

    invalid: list[str] = []
    if normalized_intent not in VALID_INTENTS:
        invalid.append("intent")
    if normalized_urgency not in VALID_URGENCIES:
        invalid.append("urgency")

    if invalid:
        # Returned rather than raised, and without echoing what was sent: a raised error
        # ends the turn, whereas a readable result lets the model correct itself. The
        # rejected value is not named because it arrived from a model reasoning over a
        # patient message and can carry clinical detail.
        logger.warning("Triage decision rejected: invalid %s", ", ".join(invalid))
        return {
            "error": "invalid_decision",
            "message": (
                f"The {' and '.join(invalid)} you supplied is not one of the accepted "
                "values. Call this again with an accepted value."
            ),
        }

    state = getattr(tool_context, "state", None)
    if state is None:
        # The decision is the only way this turn gets an intent and an urgency, so losing
        # it is worth a log rather than a silent success the caller cannot detect.
        logger.error("No session state available; the triage decision was not recorded")
        return {"error": "not_recorded", "message": "The decision could not be recorded."}

    state[TRIAGE_DECISION_STATE_KEY] = {
        "intent": normalized_intent,
        "urgency": normalized_urgency,
        "reason": (reason or "").strip()[:500],
    }
    return {"recorded": True}
