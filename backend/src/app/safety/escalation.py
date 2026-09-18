"""Urgency escalation that can only ever move in the safe direction.

The rule this module enforces: an override may raise urgency, never lower it. The
previous implementation could only promote `routine` to `urgent` and had no way to reach
`emergency`, so a message carrying a danger sign that the model had read as routine could
be nudged one step and no further.
"""

from __future__ import annotations

from app.safety.triage_floor import (
    SafetyVerdict,
    UrgencyType,
    contains_adverse_effect_signal,
    deterministic_safety_floor,
)

_URGENCY_RANK: dict[str, int] = {"routine": 0, "urgent": 1, "emergency": 2}


def is_escalation(current: str, proposed: str) -> bool:
    """Whether `proposed` is strictly more urgent than `current`."""
    return _URGENCY_RANK.get(proposed, 0) > _URGENCY_RANK.get(current, 0)


def apply_safety_override(
    *,
    intent: str,
    urgency: str,
    reason: str,
    message: str,
) -> tuple[str, UrgencyType, str]:
    """Return the classification after deterministic escalation.

    Two rules, in order:

    1. If the deterministic floor applies to this message, it wins outright — the floor
       is the authority on emergencies regardless of what the model decided.
    2. Otherwise an adverse-effect signal raises `routine` to `urgent`.

    Never returns a urgency lower than the one passed in.
    """
    floor = deterministic_safety_floor(message)
    if floor is not None and is_escalation(urgency, floor.urgency):
        return floor.intent, floor.urgency, floor.reason

    if urgency == "emergency" or not contains_adverse_effect_signal(message):
        return intent, _as_urgency(urgency), reason

    if intent == "medication_question" and is_escalation(urgency, "urgent"):
        return intent, "urgent", "Potential medication side-effect pattern detected"

    if is_escalation(urgency, "urgent"):
        return intent, "urgent", f"{reason} + adverse-effect signal forced urgent"

    return intent, _as_urgency(urgency), reason


def verdict_to_tuple(verdict: SafetyVerdict) -> tuple[str, UrgencyType, str]:
    return verdict.intent, verdict.urgency, verdict.reason


def _as_urgency(value: str) -> UrgencyType:
    if value in ("routine", "urgent", "emergency"):
        return value  # type: ignore[return-value]
    return "routine"
