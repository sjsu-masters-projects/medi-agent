"""Triage Agent — classifies intent/urgency and generates safe patient chat responses."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from app.agents.base import AgentInput, AgentOutput, BaseAgent
from app.agents.triage.graph import build_triage_graph
from app.clients.model_router import ModelRouter, get_router
from app.core.exceptions import AgentError
from app.models.enums import Language


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
