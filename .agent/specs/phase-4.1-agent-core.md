# Phase 4.1: Agent Core - Implementation Spec

> **Production-Grade AI Agent Infrastructure**  
> **Estimated Effort**: 16-20 hours  
> **Priority**: P0 (Blocks Phase 4.2-4.4)

---

## Overview

Build the foundational infrastructure for all AI agents in MediAgent:
- Abstract base class following SOLID principles
- LLM client services (Gemini Flash + Pro with thinking mode)
- LangGraph state management patterns
- Error handling, retry logic, and observability
- Comprehensive testing framework

---

## Architecture

```
agents/
├── base.py              # BaseAgent ABC + shared types
├── __init__.py          # Export all agents
├── ingestion/           # Phase 4: Document parsing agent
│   ├── __init__.py
│   ├── agent.py         # IngestionAgent class
│   ├── graph.py         # LangGraph state + nodes
│   └── prompts.py       # System/user prompt templates
└── ...                  # Future agents (triage, pharma, etc.)

clients/
├── gemini.py            # GeminiClient (Flash + Pro + thinking mode)
├── medgemma.py          # MedGemmaClient (for evaluation)
└── __init__.py

core/
├── exceptions.py        # Custom agent exceptions
└── observability.py     # Logging, tracing, metrics
```

---

## Task Breakdown

### **Task 4.1.1: Create BaseAgent Abstract Class** (2 hours)

**File**: `backend/src/app/agents/base.py`

**Requirements**:
- Follow SOLID principles (especially Open/Closed)
- All agents must extend this base class
- Type-safe with full mypy compliance
- Async-first design

**Implementation**:

```python
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
    async def process(self, input: TInput) -> TOutput:
        """Process input and return output.

        This is the main entry point for the agent.
        Must be implemented by all subclasses.

        Args:
            input: Agent-specific input (extends AgentInput)

        Returns:
            Agent-specific output (extends AgentOutput)

        Raises:
            AgentError: If processing fails
        """
        pass

    async def __call__(self, input: TInput) -> TOutput:
        """Allow agent to be called directly: agent(input)."""
        return await self.process(input)

    def _log_start(self, input: TInput) -> None:
        """Log agent execution start."""
        self.logger.info(
            f"Agent {self.name} started",
            extra={
                "agent": self.name,
                "input_type": type(input).__name__,
                "user_id": getattr(input, "user_id", None),
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
```

**Tests**: `backend/tests/unit/agents/test_base_agent.py`
- Test abstract class cannot be instantiated
- Test concrete implementation works
- Test logging methods
- Test generic type constraints

---

### **Task 4.1.2: Create GeminiClient Service** (4 hours)

**File**: `backend/src/app/clients/gemini.py`

**Requirements**:
- Support Gemini 3.0 Flash (fast, cheap)
- Support Gemini 3.0 Pro (reasoning, thinking mode)
- Retry logic with exponential backoff
- Rate limiting
- Structured output support
- Vision support (for document parsing)
- Streaming support (for chat)

**Implementation**:

```python
"""Gemini LLM client with retry, rate limiting, and structured output."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, TypeVar

import google.generativeai as genai
from google.generativeai.types import GenerateContentResponse, GenerationConfig
from pydantic import BaseModel

from app.config import settings
from app.core.exceptions import LLMError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class GeminiClient:
    """Production-grade Gemini client.

    Features:
    - Automatic retry with exponential backoff
    - Rate limiting
    - Structured output (Pydantic models)
    - Vision support (images + PDFs)
    - Thinking mode (Pro only)
    - Streaming

    Example:
        client = GeminiClient(model="gemini-3.0-flash")
        response = await client.generate(
            prompt="Explain this medical document",
            image=document_bytes
        )
    """

    def __init__(
        self,
        model: str = "gemini-3.0-flash",
        api_key: str | None = None,
        max_retries: int = 3,
        timeout: int = 60,
    ) -> None:
        """Initialize Gemini client.

        Args:
            model: Model name (gemini-3.0-flash or gemini-3.0-pro)
            api_key: Google API key (defaults to settings.GOOGLE_API_KEY)
            max_retries: Max retry attempts on failure
            timeout: Request timeout in seconds
        """
        self.model_name = model
        self.max_retries = max_retries
        self.timeout = timeout

        # Configure API
        genai.configure(api_key=api_key or settings.GOOGLE_API_KEY)
        self.model = genai.GenerativeModel(model)

        logger.info(f"Initialized GeminiClient with model={model}")

    async def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        image: bytes | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        thinking_mode: bool = False,
    ) -> str:
        """Generate text completion.

        Args:
            prompt: User prompt
            system_instruction: System instruction (optional)
            image: Image bytes for vision tasks (optional)
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Max output tokens
            thinking_mode: Enable thinking mode (Pro only)

        Returns:
            Generated text

        Raises:
            LLMError: If generation fails after retries
        """
        if thinking_mode and "pro" not in self.model_name:
            raise ValueError("Thinking mode requires gemini-3.0-pro")

        config = GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )

        # Build content parts
        parts = [prompt]
        if image:
            parts.append({"mime_type": "image/jpeg", "data": image})

        # Retry logic
        for attempt in range(self.max_retries):
            try:
                response: GenerateContentResponse = await asyncio.wait_for(
                    self.model.generate_content_async(
                        parts,
                        generation_config=config,
                        system_instruction=system_instruction,
                    ),
                    timeout=self.timeout,
                )

                if not response.text:
                    raise LLMError("Empty response from Gemini")

                return response.text

            except asyncio.TimeoutError:
                logger.warning(f"Gemini timeout (attempt {attempt + 1}/{self.max_retries})")
                if attempt == self.max_retries - 1:
                    raise LLMError("Gemini request timed out")
                await asyncio.sleep(2**attempt)  # Exponential backoff

            except Exception as e:
                logger.error(f"Gemini error (attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt == self.max_retries - 1:
                    raise LLMError(f"Gemini generation failed: {e}") from e
                await asyncio.sleep(2**attempt)

        raise LLMError("Gemini generation failed after all retries")

    async def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        system_instruction: str | None = None,
        image: bytes | None = None,
        temperature: float = 0.7,
    ) -> T:
        """Generate structured output (Pydantic model).

        Args:
            prompt: User prompt
            response_model: Pydantic model class for output
            system_instruction: System instruction (optional)
            image: Image bytes for vision tasks (optional)
            temperature: Sampling temperature

        Returns:
            Parsed Pydantic model instance

        Raises:
            LLMError: If generation or parsing fails
        """
        # Add JSON schema to prompt
        schema = response_model.model_json_schema()
        enhanced_prompt = f"""{prompt}

Respond with valid JSON matching this schema:
{schema}

JSON response:"""

        response_text = await self.generate(
            prompt=enhanced_prompt,
            system_instruction=system_instruction,
            image=image,
            temperature=temperature,
        )

        # Parse JSON response
        try:
            # Extract JSON from markdown code blocks if present
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            return response_model.model_validate_json(response_text)
        except Exception as e:
            raise LLMError(f"Failed to parse structured output: {e}") from e

    async def generate_stream(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.7,
    ):
        """Generate streaming response (for chat).

        Args:
            prompt: User prompt
            system_instruction: System instruction (optional)
            temperature: Sampling temperature

        Yields:
            Text chunks as they arrive

        Raises:
            LLMError: If streaming fails
        """
        config = GenerationConfig(temperature=temperature)

        try:
            response = await self.model.generate_content_async(
                prompt,
                generation_config=config,
                system_instruction=system_instruction,
                stream=True,
            )

            async for chunk in response:
                if chunk.text:
                    yield chunk.text

        except Exception as e:
            raise LLMError(f"Gemini streaming failed: {e}") from e
```

**Tests**: `backend/tests/unit/clients/test_gemini_client.py`
- Test basic generation
- Test structured output
- Test retry logic
- Test timeout handling
- Test vision support
- Mock Gemini API responses

---

### **Task 4.1.3: Create MedGemmaClient Service** (2 hours)

**File**: `backend/src/app/clients/medgemma.py`

**Requirements**:
- Support MedGemma model (for evaluation)
- Same interface as GeminiClient
- Can be swapped in for A/B testing

**Implementation**:

```python
"""MedGemma client for medical task evaluation."""

from __future__ import annotations

import logging
from typing import TypeVar

from pydantic import BaseModel

from app.clients.gemini import GeminiClient
from app.core.exceptions import LLMError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class MedGemmaClient:
    """MedGemma client for medical tasks.

    Uses same interface as GeminiClient for easy A/B testing.
    MedGemma is Google's medical-specialized model based on Gemma 3.

    Example:
        # Swap GeminiClient for MedGemmaClient
        client = MedGemmaClient()
        response = await client.generate(prompt="Diagnose this symptom")
    """

    def __init__(
        self,
        model: str = "medgemma-3-8b",
        max_retries: int = 3,
        timeout: int = 60,
    ) -> None:
        """Initialize MedGemma client.

        Args:
            model: MedGemma model variant
            max_retries: Max retry attempts
            timeout: Request timeout in seconds
        """
        self.model_name = model
        self.max_retries = max_retries
        self.timeout = timeout

        # TODO: Replace with actual MedGemma API when available
        # For now, use Gemini as fallback
        logger.warning("MedGemma not yet implemented, falling back to Gemini")
        self._fallback_client = GeminiClient(
            model="gemini-3.0-flash",
            max_retries=max_retries,
            timeout=timeout,
        )

    async def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        image: bytes | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Generate text completion (same interface as GeminiClient)."""
        # TODO: Implement MedGemma API call
        return await self._fallback_client.generate(
            prompt=prompt,
            system_instruction=system_instruction,
            image=image,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def generate_structured(
        self,
        prompt: str,
        response_model: type[T],
        system_instruction: str | None = None,
        image: bytes | None = None,
        temperature: float = 0.7,
    ) -> T:
        """Generate structured output (same interface as GeminiClient)."""
        # TODO: Implement MedGemma API call
        return await self._fallback_client.generate_structured(
            prompt=prompt,
            response_model=response_model,
            system_instruction=system_instruction,
            image=image,
            temperature=temperature,
        )
```

**Tests**: `backend/tests/unit/clients/test_medgemma_client.py`
- Test fallback to Gemini
- Test interface compatibility with GeminiClient

---

### **Task 4.1.4: Create LangGraph State Schema** (2 hours)

**File**: `backend/src/app/agents/ingestion/graph.py`

**Requirements**:
- Type-safe state with TypedDict
- Clear state transitions
- Support for retries and error states

**Implementation**:

```python
"""LangGraph state management for Ingestion Agent."""

from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages


class IngestionState(TypedDict):
    """State for document ingestion workflow.

    State flows through these stages:
    1. receive_document → document_bytes, document_type
    2. extract_text → raw_text
    3. parse_structured → parsed_data
    4. normalize_medications → normalized_meds
    5. save_to_db → saved_ids
    6. generate_summary → summary
    """

    # Input
    document_id: str
    document_bytes: bytes
    document_type: str  # "pdf" | "image" | "text"
    patient_id: str

    # Intermediate state
    raw_text: str | None
    parsed_data: dict | None
    normalized_meds: list[dict] | None

    # Output
    saved_ids: dict[str, list[str]] | None  # {"medications": [...], "conditions": [...]}
    summary: str | None

    # Error handling
    error: str | None
    retry_count: int

    # Messages (for LangGraph message passing)
    messages: Annotated[list, add_messages]


def create_ingestion_graph() -> StateGraph:
    """Create LangGraph workflow for document ingestion.

    Workflow:
        START
          ↓
        extract_text (vision LLM)
          ↓
        parse_structured (structured output)
          ↓
        normalize_medications (RxNorm MCP)
          ↓
        save_to_db (Supabase MCP)
          ↓
        generate_summary (LLM)
          ↓
        END

    Returns:
        Compiled StateGraph
    """
    from app.agents.ingestion.agent import IngestionAgent

    # Create graph
    graph = StateGraph(IngestionState)

    # Add nodes (implemented in agent.py)
    agent = IngestionAgent()
    graph.add_node("extract_text", agent._extract_text)
    graph.add_node("parse_structured", agent._parse_structured)
    graph.add_node("normalize_medications", agent._normalize_medications)
    graph.add_node("save_to_db", agent._save_to_db)
    graph.add_node("generate_summary", agent._generate_summary)

    # Define edges
    graph.add_edge(START, "extract_text")
    graph.add_edge("extract_text", "parse_structured")
    graph.add_edge("parse_structured", "normalize_medications")
    graph.add_edge("normalize_medications", "save_to_db")
    graph.add_edge("save_to_db", "generate_summary")
    graph.add_edge("generate_summary", END)

    # Compile
    return graph.compile()
```

**Tests**: `backend/tests/unit/agents/test_ingestion_graph.py`
- Test state transitions
- Test error states
- Test graph compilation

---

### **Task 4.1.5: Create Custom Exceptions** (1 hour)

**File**: `backend/src/app/core/exceptions.py` (update existing)

**Add**:

```python
class AgentError(MediAgentError):
    """Base exception for all agent errors."""
    pass


class LLMError(AgentError):
    """Raised when LLM generation fails."""
    pass


class ParsingError(AgentError):
    """Raised when document parsing fails."""
    pass


class NormalizationError(AgentError):
    """Raised when data normalization fails."""
    pass
```

---

### **Task 4.1.6: Add Observability** (2 hours)

**File**: `backend/src/app/core/observability.py`

**Requirements**:
- Structured logging
- Trace IDs for request tracking
- Metrics (latency, success rate)

**Implementation**:

```python
"""Observability utilities for agents."""

import logging
import time
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


@asynccontextmanager
async def trace_agent_execution(agent_name: str, input_data: dict[str, Any]):
    """Context manager for tracing agent execution.

    Usage:
        async with trace_agent_execution("ingestion", {"doc_id": doc_id}):
            result = await agent.process(input)
    """
    trace_id = str(uuid4())
    start_time = time.time()

    logger.info(
        f"Agent {agent_name} started",
        extra={
            "trace_id": trace_id,
            "agent": agent_name,
            "input": input_data,
        },
    )

    try:
        yield trace_id
        duration = time.time() - start_time
        logger.info(
            f"Agent {agent_name} completed",
            extra={
                "trace_id": trace_id,
                "agent": agent_name,
                "duration_ms": int(duration * 1000),
                "status": "success",
            },
        )
    except Exception as e:
        duration = time.time() - start_time
        logger.error(
            f"Agent {agent_name} failed",
            extra={
                "trace_id": trace_id,
                "agent": agent_name,
                "duration_ms": int(duration * 1000),
                "status": "error",
                "error": str(e),
            },
            exc_info=True,
        )
        raise
```

---

### **Task 4.1.7: Write Comprehensive Tests** (3 hours)

**Files**:
- `backend/tests/unit/agents/test_base_agent.py`
- `backend/tests/unit/clients/test_gemini_client.py`
- `backend/tests/unit/clients/test_medgemma_client.py`
- `backend/tests/unit/agents/test_ingestion_graph.py`

**Coverage Target**: >90%

**Test Categories**:
1. Unit tests for each component
2. Integration tests for LLM clients (mocked)
3. Graph execution tests
4. Error handling tests
5. Retry logic tests

---

### **Task 4.1.8: Update Documentation** (1 hour)

**Files to Update**:
- `backend/README.md` - Add agent development guide
- `.agent/ARCHITECTURE.md` - Update agent layer diagram
- `.agent/CODING_STANDARDS.md` - Add agent-specific standards

---

## Success Criteria

- [ ] All tests passing (>90% coverage)
- [ ] No mypy errors
- [ ] No ruff linting errors
- [ ] BaseAgent can be extended by any new agent
- [ ] GeminiClient handles retries and timeouts
- [ ] LangGraph state transitions work correctly
- [ ] Observability logs are structured and useful
- [ ] Documentation is complete and accurate

---

## Dependencies

**External**:
- `google-generativeai` - Gemini API
- `langgraph` - State management
- `pydantic` - Data validation

**Internal**:
- `app.config` - Settings
- `app.core.exceptions` - Custom exceptions
- `app.db.connection` - Database client

---

## Next Steps (Phase 4.2)

After completing 4.1, you'll have:
- ✅ BaseAgent that all agents extend
- ✅ GeminiClient for LLM calls
- ✅ LangGraph state management
- ✅ Error handling and observability

**Phase 4.2** will build the actual Ingestion Agent using this infrastructure.

---

## Estimated Timeline

| Task | Hours | Dependencies |
|------|-------|--------------|
| 4.1.1 BaseAgent | 2 | None |
| 4.1.2 GeminiClient | 4 | None |
| 4.1.3 MedGemmaClient | 2 | 4.1.2 |
| 4.1.4 LangGraph State | 2 | 4.1.1 |
| 4.1.5 Exceptions | 1 | None |
| 4.1.6 Observability | 2 | None |
| 4.1.7 Tests | 3 | All above |
| 4.1.8 Documentation | 1 | All above |
| **Total** | **17 hours** | |

---

## Notes

- Follow SOLID principles strictly
- All code must be production-grade (error handling, logging, typing)
- Use Context7 examples for LangGraph patterns
- Test everything (unit + integration)
- Document as you go
