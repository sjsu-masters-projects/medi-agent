"""Shared safety boundary for chat and the forthcoming intake mutations."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.safety.triage_copy import TRIAGE_COPY
from app.safety.triage_floor import SafetyVerdict, deterministic_safety_floor
from app.utils.localization import resolve_locale_resource

logger = logging.getLogger(__name__)
SAFETY_RULE_VERSION = "triage-floor/1"
_COPY_KEYS = {
    "emergency_mental_health_keyword": "mental_health_emergency_response",
    "emergency_symptom_keyword": "emergency_response",
    "urgent_medication_error": "medication_error_response",
}


@dataclass(frozen=True)
class IntakeSafetyDecision:
    verdict: SafetyVerdict
    response_text: str
    rule_version: str = SAFETY_RULE_VERSION


def safety_response(verdict: SafetyVerdict, locale: str | None) -> str:
    """Reuse reviewed copy; an unknown rule must still produce emergency direction."""
    key = _COPY_KEYS.get(verdict.safety_rule)
    if key is None:
        logger.error("Safety rule has no reviewed copy: rule=%s", verdict.safety_rule)
        key = "emergency_response"
    return str(resolve_locale_resource(locale, TRIAGE_COPY)[key])


def evaluate_intake_safety(message: str, locale: str | None) -> IntakeSafetyDecision | None:
    """No match is not clinical clearance; callers must preserve unanswered red flags."""
    verdict = deterministic_safety_floor(message)
    if verdict is None:
        return None
    return IntakeSafetyDecision(verdict, safety_response(verdict, locale))
