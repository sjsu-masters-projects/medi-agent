"""Triage Agent — classifies intent/urgency and generates safe patient chat responses."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID

from pydantic import Field

from app.agents.base import AgentInput, AgentOutput, BaseAgent
from app.agents.triage.graph import (
    TriageState,
    _apply_safety_override,
    _build_context,
    _classify_with_llm,
    _classify_with_rules,
    _emergency_response,
    _fallback_response,
    _route_for_intent,
    build_triage_graph,
    categorize_llm_failure,
)
from app.agents.triage.prompts import (
    CHAT_RESPONSE_SYSTEM_INSTRUCTION,
    build_triage_response_prompt,
)
from app.clients.model_router import ModelRouter, TaskType, get_router
from app.core.exceptions import AgentError
from app.core.observability import record_chat_fallback
from app.models.enums import Language

logger = logging.getLogger(__name__)


class TriageInput(AgentInput):
    """Input contract for triage processing."""

    patient_id: UUID
    message: str = Field(..., min_length=1)
    language: Language = Language.EN
    history: list[dict[str, Any]] = Field(default_factory=list)
    patient_context: dict[str, Any] = Field(default_factory=dict)
    document_context: dict[str, Any] | None = None
    conversation_state: dict[str, Any] = Field(default_factory=dict)


class TriageOutput(AgentOutput):
    """Output contract for triage processing."""

    intent: str | None = None
    urgency: str | None = None
    response_text: str | None = None
    escalation_required: bool = False
    route: str = "triage"


class TriageAgent(BaseAgent[TriageInput, TriageOutput]):
    """Classifies and responds to patient chat messages."""

    def __init__(self, router: ModelRouter | None = None) -> None:
        super().__init__(name="triage")
        self.router = router or get_router()

    async def process(self, agent_input: TriageInput) -> TriageOutput:
        """Run triage graph for the incoming patient message."""
        self._log_start(agent_input)

        try:
            graph = build_triage_graph(self.router)

            final_state = await graph.ainvoke(
                {
                    "patient_id": str(agent_input.patient_id),
                    "user_id": str(agent_input.user_id),
                    "language": agent_input.language.value,
                    "message": agent_input.message,
                    "history": agent_input.history,
                    "patient_context": agent_input.patient_context,
                    "document_context": agent_input.document_context,
                    "conversation_state": agent_input.conversation_state,
                }
            )

            response_text = str(final_state.get("assistant_response", "")).strip()
            if not response_text:
                response_text = "I received your message and noted it for your care team."

            output = TriageOutput(
                agent_id=agent_input.agent_id,
                status="success",
                intent=str(final_state.get("intent", "general")),
                urgency=str(final_state.get("urgency", "routine")),
                response_text=response_text,
                escalation_required=bool(final_state.get("escalation_required", False)),
                route=str(final_state.get("route", "triage")),
                result={
                    "patient_id": str(agent_input.patient_id),
                },
                metadata={
                    "classification_reason": str(final_state.get("classification_reason", "")),
                },
            )

            self._log_success(output)
            return output
        except Exception as exc:
            self._log_error(exc)
            raise AgentError(f"Triage agent failed: {exc}") from exc

    async def process_stream(
        self,
        agent_input: TriageInput,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Streaming variant: yields classification first, then response token chunks.

        Yields:
            {"type": "classification", "intent": ..., "urgency": ..., "route": ...,
             "escalation_required": bool, "classification_reason": str}
            {"type": "chunk", "content": str}        (zero or more)
            {"type": "complete", "response_text": str, "fallback_used": bool}

        On unrecoverable error, raises AgentError so the caller can apply L3 fallback.
        """
        self._log_start(agent_input)

        state: TriageState = {
            "patient_id": str(agent_input.patient_id),
            "user_id": str(agent_input.user_id),
            "language": agent_input.language.value,
            "message": agent_input.message,
            "history": agent_input.history,
            "patient_context": agent_input.patient_context,
            "document_context": agent_input.document_context,
            "conversation_state": agent_input.conversation_state,
        }
        context = _build_context(state)

        if not context.message:
            yield {
                "type": "classification",
                "intent": "general",
                "urgency": "routine",
                "route": "triage",
                "escalation_required": False,
                "classification_reason": "Empty patient message",
            }
            yield {"type": "complete", "response_text": "", "fallback_used": True}
            return

        # Classification — same logic as the non-streaming graph node.
        llm_result = await _classify_with_llm(self.router, context)
        rule_result = llm_result or _classify_with_rules(context)
        result = _apply_safety_override(rule_result, context.message)

        intent = result.intent
        urgency = result.urgency
        route = _route_for_intent(intent)
        escalation_required = urgency in {"urgent", "emergency"}

        yield {
            "type": "classification",
            "intent": intent,
            "urgency": urgency,
            "route": route,
            "escalation_required": escalation_required,
            "classification_reason": result.reason,
        }

        # Emergency: deterministic localized template, no LLM.
        if urgency == "emergency":
            template = _emergency_response(context.language, intent=intent)
            yield {"type": "chunk", "content": template}
            yield {"type": "complete", "response_text": template, "fallback_used": False}
            return

        # Streaming response generation.
        accumulated: list[str] = []
        fallback_used = False
        any_chunk_yielded = False
        try:
            client = self.router.get_client(TaskType.CHAT_RESPONSE)
            prompt = build_triage_response_prompt(
                message=context.message,
                intent=intent,
                urgency=urgency,
                language=context.language,
                history=context.history,
                patient_context=context.patient_context,
                document_context=context.document_context,
                conversation_state=context.conversation_state,
            )
            stream = client.generate_stream(
                prompt=prompt,
                system_instruction=CHAT_RESPONSE_SYSTEM_INSTRUCTION,
                temperature=0.35,
            )
            async for chunk in stream:
                if not chunk:
                    continue
                accumulated.append(chunk)
                any_chunk_yielded = True
                yield {"type": "chunk", "content": chunk}
        except Exception as exc:
            fallback_reason = categorize_llm_failure(exc)
            record_chat_fallback(layer="L2_response_stream", reason=fallback_reason)
            logger.warning(
                "Triage streaming response failed; using fallback: %s",
                exc,
                extra={
                    "chat_fallback_layer": "L2_response_stream",
                    "chat_fallback_reason": fallback_reason,
                },
            )
            fallback_used = True

        full_text = "".join(accumulated).strip()
        if not full_text and not any_chunk_yielded:
            # Total LLM failure with nothing rendered yet — emit fallback template.
            fallback_used = True
            full_text = _fallback_response(
                language=context.language,
                intent=intent,
                urgency=urgency,
                message=context.message,
            )
            yield {"type": "chunk", "content": full_text}
        elif not full_text and any_chunk_yielded:
            # Stream raised after only whitespace — keep what user already saw.
            full_text = "".join(accumulated)

        yield {
            "type": "complete",
            "response_text": full_text,
            "fallback_used": fallback_used,
        }
