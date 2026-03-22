"""Base agent class — all agents extend this."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Generic types for input/output
TInput = TypeVar("TInput", bound=BaseModel)
TOutput = TypeVar("TOutput", bound=BaseModel)


class AgentInput(BaseModel):
    """Base input for all agents."""

    agent_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: UUID
    session_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentOutput(BaseModel):
    """Base output for all agents."""

    agent_id: str
    status: str  # "success" | "error" | "partial"
    result: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseAgent(ABC, Generic[TInput, TOutput]):
    """Abstract base class for all AI agents.

    All agents must:
    1. Extend this class
    2. Implement process() method
    3. Use LangGraph for state management
    4. Handle errors gracefully
    5. Log all operations

    Example:
        class IngestionAgent(BaseAgent[IngestionInput, IngestionOutput]):
            async def process(self, input: IngestionInput) -> IngestionOutput:
                # Implementation
                ...
    """

    def __init__(self, name: str) -> None:
        """Initialize agent with name for logging/tracing."""
        self.name = name
        self.logger = logging.getLogger(f"agents.{name}")

    @abstractmethod
    async def process(self, agent_input: TInput) -> TOutput:
        """Process input and return output.

        This is the main entry point for the agent.
        Must be implemented by all subclasses.

        Args:
            agent_input: Agent-specific input (extends AgentInput)

        Returns:
            Agent-specific output (extends AgentOutput)

        Raises:
            AgentError: If processing fails
        """
        pass

    async def __call__(self, agent_input: TInput) -> TOutput:
        """Allow agent to be called directly: agent(input)."""
        return await self.process(agent_input)

    def _log_start(self, agent_input: TInput) -> None:
        """Log agent execution start."""
        self.logger.info(
            f"Agent {self.name} started",
            extra={
                "agent": self.name,
                "input_type": type(agent_input).__name__,
                "user_id": getattr(agent_input, "user_id", None),
            },
        )

    def _log_success(self, output: TOutput) -> None:
        """Log agent execution success."""
        self.logger.info(
            f"Agent {self.name} completed successfully",
            extra={
                "agent": self.name,
                "output_type": type(output).__name__,
                "status": getattr(output, "status", "unknown"),
            },
        )

    def _log_error(self, error: Exception) -> None:
        """Log agent execution error."""
        self.logger.error(
            f"Agent {self.name} failed",
            extra={"agent": self.name, "error": str(error)},
            exc_info=True,
        )
