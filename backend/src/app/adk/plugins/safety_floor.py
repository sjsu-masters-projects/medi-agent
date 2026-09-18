"""Answer an emergency deterministically, before any agent or model runs.

This is the runtime expression of the rule in `.agent/ARCHITECTURE.md`: anything that
decides safety is code. When a message trips the keyword floor, the model is not consulted
at all — not to confirm the classification, and not to phrase the reply. The patient gets
fixed, reviewed copy naming 911 or 988.

It is a plugin rather than an agent callback for one reason: a plugin is registered once
on the `Runner` and runs before any agent, so the guarantee cannot be lost by adding an
agent later or by forgetting to wire a callback onto one of them. The defect this replaces
was exactly that shape — the streaming chat path reached the floor only when the model
happened to fail.
"""

from __future__ import annotations

import logging
from typing import Any

from google.adk.plugins import BasePlugin
from google.genai import types

from app.safety import TRIAGE_COPY, SafetyVerdict, deterministic_safety_floor
from app.utils.localization import resolve_locale_resource

logger = logging.getLogger(__name__)

LOCALE_STATE_KEY = "locale"
"""Session-state key holding the patient's locale, seeded when the run starts."""

# Which reviewed response each floor rule earns. `deterministic_safety_floor` returns
# exactly these two rules today, and checks self-harm first so a message carrying both
# signals is answered with the crisis line rather than a general emergency instruction.
_COPY_KEY_BY_RULE: dict[str, str] = {
    "emergency_mental_health_keyword": "mental_health_emergency_response",
    "emergency_symptom_keyword": "emergency_response",
}

_FALLBACK_COPY_KEY = "emergency_response"


def _message_text(content: types.Content | None) -> str:
    """Flatten the incoming turn to the text the keyword floor reads."""
    if content is None or not content.parts:
        return ""
    return " ".join(part.text for part in content.parts if part.text)


def _copy_key_for(verdict: SafetyVerdict) -> str:
    key = _COPY_KEY_BY_RULE.get(verdict.safety_rule)
    if key is None:
        # A rule added to the floor without copy to match. Falling back to the general
        # emergency instruction is safe and still actionable; saying nothing is not.
        logger.error(
            "Safety rule %s has no patient copy; using the general emergency response",
            verdict.safety_rule,
        )
        return _FALLBACK_COPY_KEY
    return key


class SafetyFloorPlugin(BasePlugin):
    """Halt the run and answer directly when a message trips the emergency floor."""

    def __init__(self) -> None:
        super().__init__(name="safety_floor")

    async def before_run_callback(self, *, invocation_context: Any) -> types.Content | None:
        """Return fixed copy to halt the run, or None to let the agents proceed.

        **The return type is load-bearing and is not what ADK's prose says.** The
        docstring on `BasePlugin.before_run_callback` describes returning "an optional
        `Event`", while the annotation says `Optional[types.Content]`. Measured against a
        live runner on adk 2.9.1: returning `types.Content` halts before any agent runs,
        and returning an `Event` does **not** halt — the run proceeds into the agent
        exactly as if `None` had been returned. Returning an `Event` here would therefore
        send an emergency message to the model with no halt at all, which is the defect
        this plugin exists to prevent.
        """
        message = _message_text(getattr(invocation_context, "user_content", None))
        if not message.strip():
            return None

        verdict = deterministic_safety_floor(message)
        if verdict is None:
            return None

        session = getattr(invocation_context, "session", None)
        state = getattr(session, "state", None) or {}
        locale = state.get(LOCALE_STATE_KEY)

        localized = resolve_locale_resource(locale, TRIAGE_COPY)
        text = localized[_copy_key_for(verdict)]

        logger.warning(
            "Safety floor halted the run before any agent: rule=%s urgency=%s",
            verdict.safety_rule,
            verdict.urgency,
        )
        return types.Content(role="model", parts=[types.Part(text=text)])
