"""An agent may call only the tools it was granted, and nothing else.

The property that matters is the negative one: an agent with no entry, a tool added later,
or an agent renamed must all reach nothing. An allowlist that permits what it has not
heard of is not an allowlist.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.adk.plugins import ToolPolicyPlugin
from app.adk.plugins import tool_policy as tool_policy_module

ALLOWLIST = {
    "care_coordinator": frozenset({"get_patient_context", "search_patient_documents"}),
    "medication_safety": frozenset({"lookup_rxnorm_ingredient"}),
}


def _tool(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


def _context(agent_name: str) -> SimpleNamespace:
    return SimpleNamespace(agent_name=agent_name, invocation_id="inv-1")


async def _call(agent: str, tool: str) -> dict[str, object] | None:
    return await ToolPolicyPlugin(ALLOWLIST).before_tool_callback(
        tool=_tool(tool), tool_args={"query": "hello"}, tool_context=_context(agent)
    )


@pytest.fixture
def denials(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    recorded: list[dict[str, object]] = []

    def _record(*, agent_name: str, tool_name: str, invocation_id: str | None) -> None:
        recorded.append({"agent": agent_name, "tool": tool_name, "invocation": invocation_id})

    monkeypatch.setattr(tool_policy_module, "_record_denial", _record)
    return recorded


@pytest.mark.asyncio
async def test_an_allowed_tool_runs() -> None:
    """None is what lets the tool proceed."""
    assert await _call("care_coordinator", "get_patient_context") is None


@pytest.mark.asyncio
async def test_a_tool_outside_the_allowlist_is_refused() -> None:
    result = await _call("care_coordinator", "lookup_rxnorm_ingredient")

    assert result is not None
    assert result["error"] == "tool_not_permitted"


@pytest.mark.asyncio
async def test_an_agent_with_no_entry_may_call_nothing() -> None:
    """Deny-by-default: an unknown agent is not an unrestricted one."""
    assert await _call("some_new_agent", "get_patient_context") is not None


@pytest.mark.asyncio
async def test_an_unknown_tool_is_refused_even_for_a_known_agent() -> None:
    """A tool added later must not become reachable by existing agents for free."""
    assert await _call("care_coordinator", "delete_everything") is not None


@pytest.mark.asyncio
async def test_the_allowlist_is_per_agent_not_global() -> None:
    """The same tool is granted to one agent and refused to another."""
    assert await _call("medication_safety", "lookup_rxnorm_ingredient") is None
    assert await _call("care_coordinator", "lookup_rxnorm_ingredient") is not None


@pytest.mark.asyncio
async def test_a_missing_agent_name_is_refused_rather_than_trusted() -> None:
    """A malformed context must fail closed."""
    result = await ToolPolicyPlugin(ALLOWLIST).before_tool_callback(
        tool=_tool("get_patient_context"),
        tool_args={},
        tool_context=SimpleNamespace(invocation_id="inv-1"),
    )

    assert result is not None


@pytest.mark.asyncio
async def test_a_denial_is_recorded(denials: list[dict[str, object]]) -> None:
    await _call("care_coordinator", "lookup_rxnorm_ingredient")

    assert denials == [
        {
            "agent": "care_coordinator",
            "tool": "lookup_rxnorm_ingredient",
            "invocation": "inv-1",
        }
    ]


@pytest.mark.asyncio
async def test_an_allowed_call_is_not_recorded(denials: list[dict[str, object]]) -> None:
    """Recording permitted calls would bury the signal this record exists for."""
    await _call("care_coordinator", "get_patient_context")

    assert denials == []


@pytest.mark.asyncio
async def test_the_refusal_does_not_echo_the_tool_arguments() -> None:
    """A denied call still carried real inputs, which can hold clinical detail."""
    result = await ToolPolicyPlugin(ALLOWLIST).before_tool_callback(
        tool=_tool("lookup_rxnorm_ingredient"),
        tool_args={"query": "warfarin 5mg for Maria Gomez"},
        tool_context=_context("care_coordinator"),
    )

    assert result is not None
    assert "Maria Gomez" not in str(result)
    assert "warfarin" not in str(result)


@pytest.mark.asyncio
async def test_the_refusal_does_not_enumerate_the_policy() -> None:
    """Listing what else exists would hand the model a map of what to try next."""
    result = await _call("care_coordinator", "lookup_rxnorm_ingredient")

    assert result is not None
    assert "get_patient_context" not in str(result)
    assert "search_patient_documents" not in str(result)


def test_permitted_tools_is_inspectable_for_the_runner() -> None:
    """`build_runner` needs to assert on the policy, not just trust it was passed."""
    plugin = ToolPolicyPlugin(ALLOWLIST)

    assert plugin.permitted_tools("medication_safety") == frozenset({"lookup_rxnorm_ingredient"})
    assert plugin.permitted_tools("nobody") == frozenset()


def test_the_plugin_is_named_for_the_runner_to_register() -> None:
    assert ToolPolicyPlugin(ALLOWLIST).name == "tool_policy"
