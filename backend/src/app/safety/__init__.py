"""Deterministic patient-safety rules, independent of any agent runtime.

Everything here decides authority or safety, so it is code rather than a prompt, and it
is kept out of the agent packages on purpose: the runtime can be replaced without the
safety rules moving. See `.agent/ARCHITECTURE.md` — deterministic rules run before
probabilistic routing for emergencies, self-harm, allergy conflicts and duplicate therapy.
"""

from __future__ import annotations

from app.safety.escalation import apply_safety_override, is_escalation, verdict_to_tuple
from app.safety.triage_copy import TRIAGE_COPY
from app.safety.triage_floor import (
    ADVERSE_EFFECT_KEYWORDS,
    EMERGENCY_KEYWORDS,
    MENTAL_HEALTH_EMERGENCY_KEYWORDS,
    IntentType,
    SafetyVerdict,
    UrgencyType,
    contains_adverse_effect_signal,
    deterministic_safety_floor,
    matches_any,
)

__all__ = [
    "ADVERSE_EFFECT_KEYWORDS",
    "EMERGENCY_KEYWORDS",
    "MENTAL_HEALTH_EMERGENCY_KEYWORDS",
    "TRIAGE_COPY",
    "IntentType",
    "SafetyVerdict",
    "UrgencyType",
    "apply_safety_override",
    "contains_adverse_effect_signal",
    "deterministic_safety_floor",
    "is_escalation",
    "matches_any",
    "verdict_to_tuple",
]
