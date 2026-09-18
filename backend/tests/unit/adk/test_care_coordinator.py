"""Assembling the Care Coordinator, without calling a model.

The failures worth catching here are all silent ones. An agent renamed out of step with
its allowlist still runs, still answers, and simply never reaches the patient's record. A
`temperature` set on a Gemini 3.x model reads as a deliberate sampling choice and does
nothing. A thinking config sent to the OpenAI-compatible surface is a shape it has never
seen. None of these raise, so each is pinned.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from google.adk.agents import LlmAgent, SequentialAgent

from app.adk.agents.care_coordinator import (
    COORDINATOR_AGENT_NAME,
    FINDINGS_STATE_KEY,
    RESPONDER_AGENT_NAME,
    TOOL_ALLOWLIST,
    build_care_coordinator,
)
from app.adk.plugins import ToolPolicyPlugin
from app.adk.registry import Workload, route_for
from app.adk.runner import build_runner


@pytest.fixture
def routed() -> Any:
    """Build the pipeline with model construction stubbed out.

    Real construction resolves credentials and builds a Vertex client, neither of which
    this module is about. The workload each stage asks for is recorded instead, because
    *which* workload is what the registry decision actually is.
    """
    requested: list[Workload] = []

    def fake_model(workload: Workload) -> str:
        requested.append(workload)
        return f"model-for-{workload.value}"

    with patch(
        "app.adk.agents.care_coordinator.agent.adk_model_for_workload",
        side_effect=fake_model,
    ):
        pipeline = build_care_coordinator()

    return pipeline, requested


@pytest.fixture
def pipeline(routed: Any) -> SequentialAgent:
    return routed[0]


@pytest.fixture
def coordinator(pipeline: SequentialAgent) -> LlmAgent:
    return pipeline.sub_agents[0]


@pytest.fixture
def responder(pipeline: SequentialAgent) -> LlmAgent:
    return pipeline.sub_agents[1]


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------


def test_the_pipeline_runs_reasoning_before_replying(
    pipeline: SequentialAgent, coordinator: LlmAgent, responder: LlmAgent
) -> None:
    """Order is the whole point: the reply is written from notes already gathered."""
    assert isinstance(pipeline, SequentialAgent)
    assert [agent.name for agent in pipeline.sub_agents] == [
        COORDINATOR_AGENT_NAME,
        RESPONDER_AGENT_NAME,
    ]


def test_the_coordinator_notes_are_kept_for_the_rest_of_the_turn(
    coordinator: LlmAgent,
) -> None:
    assert coordinator.output_key == FINDINGS_STATE_KEY


# ---------------------------------------------------------------------------
# The allowlist — a name mismatch here denies every tool call, silently
# ---------------------------------------------------------------------------


def test_the_tool_holder_is_named_exactly_as_its_allowlist_entry(
    coordinator: LlmAgent,
) -> None:
    """Rename one without the other and every tool call is refused, raising nothing."""
    assert coordinator.name in TOOL_ALLOWLIST

    permitted = ToolPolicyPlugin(TOOL_ALLOWLIST).permitted_tools(coordinator.name)

    assert permitted == frozenset({"get_patient_context", "submit_triage_decision"})


def test_the_typed_decision_tool_is_granted(coordinator: LlmAgent) -> None:
    """Denied, the turn would reach the websocket with no intent and no urgency at all."""
    permitted = ToolPolicyPlugin(TOOL_ALLOWLIST).permitted_tools(coordinator.name)

    assert "submit_triage_decision" in permitted


def test_the_coordinator_can_reach_the_tool_it_was_actually_given(
    coordinator: LlmAgent,
) -> None:
    """The tools attached and the tools permitted have to be the same set."""
    attached = {tool.__name__ for tool in coordinator.tools}

    assert attached == ToolPolicyPlugin(TOOL_ALLOWLIST).permitted_tools(coordinator.name)


def test_the_responder_holds_no_tools_and_is_granted_none(responder: LlmAgent) -> None:
    assert responder.tools == []
    assert ToolPolicyPlugin(TOOL_ALLOWLIST).permitted_tools(responder.name) == frozenset()


def test_a_tool_that_does_not_exist_yet_is_not_granted_in_advance() -> None:
    """WS6 builds `search_patient_documents`; granting it early would misdescribe reach."""
    assert "search_patient_documents" not in TOOL_ALLOWLIST[COORDINATOR_AGENT_NAME]


def test_no_stage_may_reach_a_tool_outside_the_allowlist(coordinator: LlmAgent) -> None:
    policy = ToolPolicyPlugin(TOOL_ALLOWLIST)

    assert "lookup_rxnorm_ingredient" not in policy.permitted_tools(coordinator.name)


# ---------------------------------------------------------------------------
# Routing and generation config
# ---------------------------------------------------------------------------


def test_each_stage_asks_the_registry_for_its_own_workload(routed: Any) -> None:
    """Triage leads with gpt-oss on latency; the reply leads with Flash on prose."""
    _pipeline, requested = routed

    assert requested == [Workload.TRIAGE, Workload.REPLY]


def test_the_models_are_not_chosen_in_this_module(
    coordinator: LlmAgent, responder: LlmAgent
) -> None:
    assert coordinator.model == "model-for-triage"
    assert responder.model == "model-for-reply"


def test_token_budgets_come_from_the_registry_not_a_literal(
    coordinator: LlmAgent, responder: LlmAgent
) -> None:
    assert coordinator.generate_content_config.max_output_tokens == (
        route_for(Workload.TRIAGE).max_output_tokens
    )
    assert responder.generate_content_config.max_output_tokens == (
        route_for(Workload.REPLY).max_output_tokens
    )


@pytest.mark.parametrize("stage", ["coordinator", "responder"])
def test_temperature_is_never_set(routed: Any, stage: str) -> None:
    """Gemini 3.x accepts it and ignores it, so setting it would be a claim, not a control."""
    pipeline, _ = routed
    agent = pipeline.sub_agents[0 if stage == "coordinator" else 1]

    assert agent.generate_content_config.temperature is None


def test_the_gemini_stage_carries_its_measured_thinking_ceiling(
    responder: LlmAgent,
) -> None:
    thinking = responder.generate_content_config.thinking_config

    assert thinking is not None
    assert thinking.thinking_level == route_for(Workload.REPLY).thinking_level


def test_the_managed_model_is_not_sent_a_gemini_thinking_config(
    coordinator: LlmAgent,
) -> None:
    """The OpenAI-compatible surface has never seen this shape.

    That model's reasoning ceiling is set as `reasoning_effort` where the model is built,
    at the low level every measurement of it was taken at.
    """
    assert coordinator.generate_content_config.thinking_config is None


# ---------------------------------------------------------------------------
# Safety properties of the assembled agent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("stage", ["coordinator", "responder"])
def test_no_stage_may_transfer_on_its_own(routed: Any, stage: str) -> None:
    """Delegation is WS4. Until it is designed, a model-chosen transfer is an unplanned path."""
    pipeline, _ = routed
    agent = pipeline.sub_agents[0 if stage == "coordinator" else 1]

    assert agent.disallow_transfer_to_parent is True
    assert agent.disallow_transfer_to_peers is True


@pytest.mark.parametrize(
    "forbidden",
    ["diagnose", "dose", "untrusted"],
)
def test_both_instructions_state_the_clinical_limits(
    coordinator: LlmAgent, responder: LlmAgent, forbidden: str
) -> None:
    assert forbidden in coordinator.instruction.lower()
    assert forbidden in responder.instruction.lower()


def test_the_responder_is_told_to_answer_in_the_patient_s_language(
    responder: LlmAgent,
) -> None:
    """Both supported locales are named, rather than left to the model to infer."""
    instruction = responder.instruction.lower()

    assert "english" in instruction
    assert "spanish" in instruction


def test_the_coordinator_notes_are_not_addressed_to_the_patient(
    coordinator: LlmAgent,
) -> None:
    """The reasoning model's output is working notes; the responder writes the reply."""
    assert "internal" in coordinator.instruction.lower()


# ---------------------------------------------------------------------------
# It has to be runnable through the one construction path
# ---------------------------------------------------------------------------


def test_the_pipeline_runs_with_every_runtime_guarantee_attached(
    pipeline: SequentialAgent,
) -> None:
    """`build_runner` raises unless all four plugins are present, so this proves the wiring."""
    runner = build_runner(
        app_name="mediagent",
        agent=pipeline,
        tool_allowlist=TOOL_ALLOWLIST,
    )

    policy = next(p for p in runner.plugin_manager.plugins if p.name == "tool_policy")

    assert policy.permitted_tools(COORDINATOR_AGENT_NAME) == frozenset(
        {"get_patient_context", "submit_triage_decision"}
    )
