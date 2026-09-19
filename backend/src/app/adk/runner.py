"""The one place a `Runner` is constructed, so its guarantees cannot be skipped.

Every safety property this runtime has lives in a plugin: the emergency floor that halts
before any agent sees the message, the deny-by-default tool allowlist, the telemetry that
makes routing decisions reviewable, and the provenance stamp that lets a stored candidate
say which model produced it. A `Runner` built anywhere else, by anyone, silently has none
of them — and nothing about the resulting object looks wrong.

So construction goes through here, and `assert_guarantees` checks the **constructed
runner** rather than the list handed to it. Checking the list would be tautological: this
function builds that list itself. Reading the plugins back off the runner is what catches
a later edit that drops one.

(The plan sketched this module as `adk/app.py`; it is `adk/runner.py` because
`app.adk.app.build_runner` reads poorly inside a package already called `app`.)

**Known follow-up:** adk 2.9.1 deprecates `Runner(plugins=...)` in favour of
`Runner(app=App(name=..., root_agent=..., plugins=[...]))`, and unlike the `SequentialAgent`
deprecation that successor *does* exist here. It is not taken yet because this is the one
construction path carrying every safety guarantee, and `assert_guarantees` reads the
plugins back off `runner.plugin_manager`; moving to `App` has to be a deliberate change
that re-proves that read, not a warning silenced in passing. Passing both arguments raises,
so the migration is all-or-nothing.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, InMemorySessionService

from app.adk.plugins import (
    ProvenancePlugin,
    SafetyFloorPlugin,
    TelemetryPlugin,
    ToolPolicyPlugin,
)

REQUIRED_PLUGIN_NAMES: tuple[str, ...] = (
    "safety_floor",
    "tool_policy",
    "telemetry",
    "provenance",
)
"""Plugins a runner must carry. Each one is a guarantee, not a convenience."""


class MissingRuntimeGuaranteeError(RuntimeError):
    """A runner was assembled without one of its safety plugins."""


def assert_guarantees(runner: Runner) -> None:
    """Raise unless every required plugin is attached to this runner.

    A real `raise` rather than an `assert` statement: `assert` is removed under `python
    -O`, and a safety guarantee that disappears under an optimisation flag is not one.
    """
    manager = getattr(runner, "plugin_manager", None)
    attached = {str(getattr(plugin, "name", "")) for plugin in getattr(manager, "plugins", [])}
    missing = [name for name in REQUIRED_PLUGIN_NAMES if name not in attached]
    if missing:
        raise MissingRuntimeGuaranteeError(
            f"Runner is missing required plugins: {', '.join(missing)}. "
            "Build it with build_runner rather than constructing Runner directly."
        )


def build_runner(
    *,
    app_name: str,
    agent: Any,
    tool_allowlist: Mapping[str, frozenset[str]],
    session_service: BaseSessionService | None = None,
) -> Runner:
    """Assemble a runner carrying every runtime guarantee.

    `tool_allowlist` is required rather than defaulted. An empty default would read as
    "no restrictions configured yet" and behave as "this agent may call nothing", and the
    difference between those two readings is exactly the kind of thing that gets
    discovered in a demo.

    Sessions default to in-memory for the strangler phase. `chat_messages`,
    `conversation_states` and `clinical_facts` remain the system of record — an ADK
    session is scratch space for one conversation, never the durable truth.
    """
    runner = Runner(
        app_name=app_name,
        agent=agent,
        session_service=session_service or InMemorySessionService(),
        plugins=[
            # Order matters for readability only; ADK runs each callback across all
            # plugins. The floor is first because it is the one that can end the run.
            SafetyFloorPlugin(),
            ToolPolicyPlugin(tool_allowlist),
            TelemetryPlugin(),
            ProvenancePlugin(),
        ],
    )
    assert_guarantees(runner)
    return runner
