"""A runner without its plugins looks perfectly normal and has no safety properties.

That is why construction is funnelled through one function and why the check reads the
constructed runner rather than the list passed to it — a list check would only prove that
`build_runner` passed what `build_runner` built.
"""

from __future__ import annotations

import inspect

import pytest
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from app.adk.plugins import SafetyFloorPlugin, TelemetryPlugin
from app.adk.runner import (
    REQUIRED_PLUGIN_NAMES,
    MissingRuntimeGuaranteeError,
    assert_guarantees,
    build_runner,
)

ALLOWLIST = {"care_coordinator": frozenset({"get_patient_context"})}


def _agent() -> LlmAgent:
    return LlmAgent(name="care_coordinator", model="gemini-3.8-flash")


def _attached(runner: Runner) -> set[str]:
    return {plugin.name for plugin in runner.plugin_manager.plugins}


def test_a_built_runner_carries_every_guarantee() -> None:
    runner = build_runner(app_name="mediagent", agent=_agent(), tool_allowlist=ALLOWLIST)

    assert _attached(runner) == set(REQUIRED_PLUGIN_NAMES)


def test_the_required_set_is_the_four_safety_plugins() -> None:
    """Named explicitly so adding a fifth plugin is a deliberate decision, not a drift."""
    assert set(REQUIRED_PLUGIN_NAMES) == {
        "safety_floor",
        "tool_policy",
        "telemetry",
        "provenance",
    }


def test_a_runner_built_directly_is_rejected() -> None:
    """The failure this exists to catch: a Runner assembled somewhere else."""
    bare = Runner(
        app_name="mediagent",
        agent=_agent(),
        session_service=InMemorySessionService(),
        plugins=[],
    )

    with pytest.raises(MissingRuntimeGuaranteeError) as raised:
        assert_guarantees(bare)

    for name in REQUIRED_PLUGIN_NAMES:
        assert name in str(raised.value)


def test_a_partially_equipped_runner_is_rejected() -> None:
    """Three of four is not a safe runtime, and it looks entirely normal."""
    partial = Runner(
        app_name="mediagent",
        agent=_agent(),
        session_service=InMemorySessionService(),
        plugins=[SafetyFloorPlugin(), TelemetryPlugin()],
    )

    with pytest.raises(MissingRuntimeGuaranteeError) as raised:
        assert_guarantees(partial)

    assert "tool_policy" in str(raised.value)
    assert "provenance" in str(raised.value)
    # The ones that are present must not be reported as missing.
    assert "safety_floor" not in str(raised.value)


def test_the_check_is_a_raise_not_an_assert_statement() -> None:
    """`assert` is stripped under `python -O`; a guarantee that vanishes is not one."""
    source = inspect.getsource(assert_guarantees)

    assert "raise MissingRuntimeGuaranteeError" in source
    assert "\n    assert " not in source


def test_the_tool_allowlist_reaches_the_policy_plugin() -> None:
    runner = build_runner(app_name="mediagent", agent=_agent(), tool_allowlist=ALLOWLIST)

    policy = next(p for p in runner.plugin_manager.plugins if p.name == "tool_policy")

    assert policy.permitted_tools("care_coordinator") == frozenset({"get_patient_context"})
    assert policy.permitted_tools("someone_else") == frozenset()


def test_sessions_default_to_in_memory_for_the_strangler_phase() -> None:
    runner = build_runner(app_name="mediagent", agent=_agent(), tool_allowlist=ALLOWLIST)

    assert isinstance(runner.session_service, InMemorySessionService)


def test_a_session_service_can_be_injected() -> None:
    """WS9 swaps this for a database-backed one without touching call sites."""
    provided = InMemorySessionService()

    runner = build_runner(
        app_name="mediagent",
        agent=_agent(),
        tool_allowlist=ALLOWLIST,
        session_service=provided,
    )

    assert runner.session_service is provided
