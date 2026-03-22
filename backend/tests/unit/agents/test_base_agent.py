"""Tests for BaseAgent abstract class."""

import logging
from uuid import UUID

import pytest
from pydantic import BaseModel

from app.agents.base import AgentInput, AgentOutput, BaseAgent


class TestAgentInput(BaseModel):
    """Test input model."""

    agent_id: str
    user_id: UUID
    test_data: str


class TestAgentOutput(BaseModel):
    """Test output model."""

    agent_id: str
    status: str
    result: dict[str, str] | None = None


class ConcreteAgent(BaseAgent[TestAgentInput, TestAgentOutput]):
    """Concrete implementation for testing."""

    async def process(self, agent_input: TestAgentInput) -> TestAgentOutput:
        """Process test input."""
        self._log_start(agent_input)
        output = TestAgentOutput(
            agent_id=agent_input.agent_id,
            status="success",
            result={"data": agent_input.test_data},
        )
        self._log_success(output)
        return output


class FailingAgent(BaseAgent[TestAgentInput, TestAgentOutput]):
    """Agent that always fails for testing error handling."""

    async def process(self, agent_input: TestAgentInput) -> TestAgentOutput:
        """Process test input and fail."""
        self._log_start(agent_input)
        error = ValueError("Test error")
        self._log_error(error)
        raise error


def test_cannot_instantiate_base_agent():
    """Test that BaseAgent cannot be instantiated directly."""
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        BaseAgent("test")  # type: ignore[abstract]


@pytest.mark.asyncio
async def test_concrete_agent_process():
    """Test that concrete agent can process input."""
    agent = ConcreteAgent("test_agent")
    test_input = TestAgentInput(
        agent_id="test-123",
        user_id=UUID("12345678-1234-5678-1234-567812345678"),
        test_data="hello",
    )

    output = await agent.process(test_input)

    assert output.agent_id == "test-123"
    assert output.status == "success"
    assert output.result == {"data": "hello"}


@pytest.mark.asyncio
async def test_agent_callable():
    """Test that agent can be called directly."""
    agent = ConcreteAgent("test_agent")
    test_input = TestAgentInput(
        agent_id="test-123",
        user_id=UUID("12345678-1234-5678-1234-567812345678"),
        test_data="hello",
    )

    output = await agent(test_input)

    assert output.agent_id == "test-123"
    assert output.status == "success"


def test_agent_name():
    """Test that agent name is set correctly."""
    agent = ConcreteAgent("my_agent")
    assert agent.name == "my_agent"


def test_agent_logger():
    """Test that agent has correct logger."""
    agent = ConcreteAgent("my_agent")
    assert agent.logger.name == "agents.my_agent"
    assert isinstance(agent.logger, logging.Logger)


@pytest.mark.asyncio
async def test_log_start(caplog):
    """Test that _log_start logs correctly."""
    agent = ConcreteAgent("test_agent")
    test_input = TestAgentInput(
        agent_id="test-123",
        user_id=UUID("12345678-1234-5678-1234-567812345678"),
        test_data="hello",
    )

    with caplog.at_level(logging.INFO):
        agent._log_start(test_input)

    assert "Agent test_agent started" in caplog.text


@pytest.mark.asyncio
async def test_log_success(caplog):
    """Test that _log_success logs correctly."""
    agent = ConcreteAgent("test_agent")
    test_output = TestAgentOutput(
        agent_id="test-123",
        status="success",
    )

    with caplog.at_level(logging.INFO):
        agent._log_success(test_output)

    assert "Agent test_agent completed successfully" in caplog.text


@pytest.mark.asyncio
async def test_log_error(caplog):
    """Test that _log_error logs correctly."""
    agent = ConcreteAgent("test_agent")
    error = ValueError("Test error")

    with caplog.at_level(logging.ERROR):
        agent._log_error(error)

    assert "Agent test_agent failed" in caplog.text


@pytest.mark.asyncio
async def test_failing_agent_logs_error(caplog):
    """Test that failing agent logs error."""
    agent = FailingAgent("failing_agent")
    test_input = TestAgentInput(
        agent_id="test-123",
        user_id=UUID("12345678-1234-5678-1234-567812345678"),
        test_data="hello",
    )

    with caplog.at_level(logging.ERROR), pytest.raises(ValueError, match="Test error"):
        await agent.process(test_input)

    assert "Agent failing_agent failed" in caplog.text


def test_agent_input_default_values():
    """Test AgentInput default values."""
    agent_input = AgentInput(user_id=UUID("12345678-1234-5678-1234-567812345678"))

    assert agent_input.agent_id  # Should have a UUID
    assert agent_input.session_id is None
    assert agent_input.metadata == {}


def test_agent_output_default_values():
    """Test AgentOutput default values."""
    agent_output = AgentOutput(agent_id="test-123", status="success")

    assert agent_output.result is None
    assert agent_output.error is None
    assert agent_output.metadata == {}
