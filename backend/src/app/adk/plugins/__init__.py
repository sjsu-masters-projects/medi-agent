"""Runtime-wide guarantees, attached once to the runner rather than to each agent.

A plugin registered on the `Runner` applies to every invocation and runs before any agent
callback, so a guarantee expressed here cannot be bypassed by adding an agent later or by
forgetting a decorator on one. That is why the emergency floor lives here and not inside
an agent: the point is that no agent gets the chance to see the message at all.
"""

from app.adk.plugins.provenance import (
    PROVENANCE_AGENT_KEY,
    PROVENANCE_MODEL_KEY,
    ProvenancePlugin,
)
from app.adk.plugins.safety_floor import LOCALE_STATE_KEY, SafetyFloorPlugin
from app.adk.plugins.telemetry import TelemetryPlugin
from app.adk.plugins.tool_policy import DENIED_ERROR_CODE, ToolPolicyPlugin

__all__ = [
    "DENIED_ERROR_CODE",
    "LOCALE_STATE_KEY",
    "PROVENANCE_AGENT_KEY",
    "PROVENANCE_MODEL_KEY",
    "ProvenancePlugin",
    "SafetyFloorPlugin",
    "TelemetryPlugin",
    "ToolPolicyPlugin",
]
