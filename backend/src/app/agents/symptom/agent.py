"""Symptom Analysis Agent — extracts structured symptom data and response text."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from app.agents.base import AgentInput, AgentOutput, BaseAgent
from app.agents.symptom.graph import build_symptom_graph
from app.clients.model_router import ModelRouter, get_router
from app.core.exceptions import AgentError
from app.models.enums import Language


class SymptomInput(AgentInput):
    patient_id: UUID
    message: str = Field(..., min_length=1)
    language: Language = Language.EN
    history: list[dict[str, Any]] = Field(default_factory=list)
    patient_context: dict[str, Any] = Field(default_factory=dict)


class SymptomOutput(AgentOutput):
    symptom_report: dict[str, Any] | None = None
    response_text: str | None = None
    follow_up_question: str | None = None
    flagged_for_adr: bool = False


class SymptomAgent(BaseAgent[SymptomInput, SymptomOutput]):
    def __init__(self, router: ModelRouter | None = None) -> None:
        super().__init__(name="symptom")
        self.router = router or get_router()

    async def process(self, agent_input: SymptomInput) -> SymptomOutput:
        self._log_start(agent_input)

        try:
            graph = build_symptom_graph(self.router)
            final_state = await graph.ainvoke(
                {
                    "message": agent_input.message,
                    "language": agent_input.language.value,
                    "history": agent_input.history,
                    "patient_context": agent_input.patient_context,
                }
            )

            if final_state.get("error"):
                raise AgentError(str(final_state.get("error")))

            response_text = str(final_state.get("assistant_response", "")).strip()
            if not response_text:
                response_text = "I logged your symptom for your care team to review."

            symptom_report = final_state.get("symptom_report") or None
            output = SymptomOutput(
                agent_id=agent_input.agent_id,
                status="success",
                symptom_report=symptom_report,
                response_text=response_text,
                follow_up_question=final_state.get("follow_up_question"),
                flagged_for_adr=bool(final_state.get("flagged_for_adr", False)),
                result={
                    "patient_id": str(agent_input.patient_id),
                },
            )
            self._log_success(output)
            return output
        except Exception as exc:
            self._log_error(exc)
            raise AgentError(f"Symptom agent failed: {exc}") from exc
