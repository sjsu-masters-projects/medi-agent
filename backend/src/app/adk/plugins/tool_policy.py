"""Deny every tool call an agent has not been explicitly allowed to make.

The rule in `.agent/ARCHITECTURE.md` is that the model chooses *which* read-only tool to
call, and code decides which tools it may reach at all. This is where the second half is
enforced: an allowlist per agent, deny by default, checked before the tool runs rather
than trusted to the prompt.

Deny-by-default is the load-bearing part. An allowlist that silently permits anything it
has not heard of would let a tool added later — or an agent renamed — reach a capability
nobody granted it, and prompts are not a mechanism for preventing that.

**Denials are not written to `authorization_denial_events`.** That table records refused
*patient access*, and its reason codes are a closed set kept in step with the negative
access cases in the canonical synthetic fixture. An agent reaching for a tool outside its
allowlist is a different fact, and mixing it into a feed that is alerted on for care-team
boundary probing would blunt that signal. It is recorded here instead, through a seam that
can gain a durable table without changing this plugin.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from google.adk.plugins import BasePlugin

logger = logging.getLogger(__name__)

DENIED_ERROR_CODE = "tool_not_permitted"


def _record_denial(*, agent_name: str, tool_name: str, invocation_id: str | None) -> None:
    """Record one refused tool call. Separated so tests can substitute a sink.

    Deliberately carries no tool arguments: a denied call is still a call the model tried
    to make with real inputs, and those arguments can contain clinical detail. The
    actionable signal is which agent reached for which tool, which names no one.
    """
    logger.warning(
        "Tool policy denied a call: agent=%s tool=%s invocation=%s",
        agent_name,
        tool_name,
        invocation_id,
    )


class ToolPolicyPlugin(BasePlugin):
    """Enforce a per-agent tool allowlist, deny-by-default."""

    def __init__(self, allowlist: Mapping[str, frozenset[str]]) -> None:
        """Take the allowlist explicitly rather than reading it from a global.

        A policy assembled at construction is one a test can state completely, and one
        `build_runner` can assert on. A policy discovered at call time is one nobody can
        review.
        """
        super().__init__(name="tool_policy")
        self._allowlist = {agent: frozenset(tools) for agent, tools in allowlist.items()}

    def permitted_tools(self, agent_name: str) -> frozenset[str]:
        """What this agent may call. An agent with no entry may call nothing."""
        return self._allowlist.get(agent_name, frozenset())

    async def before_tool_callback(
        self, *, tool: Any, tool_args: dict[str, Any], tool_context: Any
    ) -> dict[str, Any] | None:
        """Return a response dict to refuse the call, or None to let it run.

        Returning a dict stops the tool and hands that dict back as its result, so the
        refusal reaches the model as an ordinary tool response it can reason about rather
        than as an exception that ends the turn.
        """
        agent_name = str(getattr(tool_context, "agent_name", "") or "unknown")
        tool_name = str(getattr(tool, "name", "") or "unknown")

        if tool_name in self.permitted_tools(agent_name):
            return None

        _record_denial(
            agent_name=agent_name,
            tool_name=tool_name,
            invocation_id=getattr(tool_context, "invocation_id", None),
        )
        # The message tells the model what to do next without describing the policy: an
        # allowlist enumerated back to the caller is a map of what else to try.
        return {
            "error": DENIED_ERROR_CODE,
            "message": (
                f"The tool {tool_name!r} is not available to this agent. "
                "Continue without it, and say plainly if the answer is incomplete."
            ),
        }
