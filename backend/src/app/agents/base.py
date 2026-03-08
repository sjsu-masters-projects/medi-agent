"""
BaseAgent — abstract base for all LangGraph agents.

DI for LLM client. Standardized I/O via AgentInput/AgentOutput.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentInput:
    patient_id: str
    content: Any
    context: dict | None = None
    language: str = "en"


@dataclass
class AgentOutput:
    success: bool
    data: Any
    errors: list[str] = field(default_factory=list)
    metadata: dict | None = None


class BaseAgent(ABC):
    def __init__(self, llm_client: Any, name: str = "base_agent"):
        self.llm = llm_client
        self.name = name

    @abstractmethod
    async def process(self, agent_input: AgentInput) -> AgentOutput:
        """Run this agent's graph and return structured output."""
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name!r})>"
