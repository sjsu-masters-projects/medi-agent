"""Care Coordinator: chat triage and the patient-facing reply.

Guides and routes; it cannot approve clinical action. The authority boundary is in
`.agent/ARCHITECTURE.md` and enforced by what this agent can reach — every tool it is
granted is read-only, and approval lives in services no tool can call.
"""

from app.adk.agents.care_coordinator.agent import (
    COORDINATOR_AGENT_NAME,
    FINDINGS_STATE_KEY,
    PIPELINE_AGENT_NAME,
    RESPONDER_AGENT_NAME,
    TOOL_ALLOWLIST,
    build_care_coordinator,
    route_for_intent,
)

__all__ = [
    "COORDINATOR_AGENT_NAME",
    "FINDINGS_STATE_KEY",
    "PIPELINE_AGENT_NAME",
    "RESPONDER_AGENT_NAME",
    "TOOL_ALLOWLIST",
    "build_care_coordinator",
    "route_for_intent",
]
