"""Summarization Agent — generates SOAP notes via LangGraph + Gemini 3.1 Pro Preview.

This agent is triggered on-demand when a clinician views a patient's deep dive
and clicks "Generate SOAP Note". It aggregates all recent patient data and
produces a structured clinical SOAP note stored in the soap_notes table.

Usage:
    agent = SummarizationAgent()
    output = await agent(SummarizationInput(
        user_id=clinician_uuid,
        patient_id=patient_uuid,
        lookback_days=30,
    ))
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from supabase import Client

from app.agents.base import AgentInput, AgentOutput, BaseAgent
from app.agents.summarization.graph import build_summarization_graph
from app.core.exceptions import AgentError

logger = logging.getLogger(__name__)


class SummarizationInput(AgentInput):
    """Input for the Summarization Agent."""

    patient_id: UUID
    lookback_days: int = 30


class SummarizationOutput(AgentOutput):
    """Output from the Summarization Agent."""

    soap_note_id: str | None = None
    soap_note: dict[str, Any] | None = None


class SummarizationAgent(BaseAgent[SummarizationInput, SummarizationOutput]):
    """Generates AI SOAP notes from patient data using LangGraph.

    SOLID:
    - Single Responsibility: only orchestrates the summarization pipeline
    - Open/Closed: extend graph nodes to add new data sources without modifying this class
    - Dependency Inversion: receives Supabase client as constructor dependency
    """

    def __init__(self, db: Client) -> None:
        super().__init__(name="summarization")
        self.db = db

    async def process(self, agent_input: SummarizationInput) -> SummarizationOutput:
        """Run the LangGraph summarization pipeline.

        Args:
            agent_input: Contains patient_id, clinician_id (user_id), lookback_days

        Returns:
            SummarizationOutput with generated SOAP note and DB ID

        Raises:
            AgentError: If the graph execution fails
        """
        self._log_start(agent_input)

        try:
            graph = build_summarization_graph(self.db)

            initial_state = {
                "patient_id": str(agent_input.patient_id),
                "clinician_id": str(agent_input.user_id),
                "lookback_days": agent_input.lookback_days,
            }

            final_state = await graph.ainvoke(initial_state)

            if final_state.get("error"):
                raise AgentError(f"Summarization failed: {final_state['error']}")

            output = SummarizationOutput(
                agent_id=agent_input.agent_id,
                status="success",
                soap_note_id=final_state.get("stored_note_id"),
                soap_note=final_state.get("soap_note"),
                result={
                    "note_id": final_state.get("stored_note_id"),
                    "patient_id": str(agent_input.patient_id),
                },
            )

            self._log_success(output)
            return output

        except AgentError:
            raise
        except Exception as exc:
            self._log_error(exc)
            raise AgentError(f"Summarization agent failed: {exc}") from exc
