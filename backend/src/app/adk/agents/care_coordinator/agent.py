"""The Care Coordinator: reason over the patient's own record, then answer them.

Two stages, as the plan's routing decision requires. The reasoning stage runs on gpt-oss,
which answered triage at a 2.2 s median against Flash's 6.2 s and holds the tools; the
responding stage runs on Flash, which writes better patient-facing prose and has the
perfect schema record. Neither model is chosen here — both come from the registry, so a
routing change stays a data change in one file.

**The agent names are load-bearing.** `ToolPolicyPlugin` keys its allowlist on
`tool_context.agent_name` and denies by default, so renaming the tool-holding agent
without renaming its allowlist entry does not raise anything — every tool call is simply
refused, the model carries on without the record, and the answer degrades quietly. The
names and the allowlist are therefore defined together, in this module, and a test pins
that they agree.

Sub-agent transfer is disabled on both stages. Delegation to the Follow-up worker is WS4;
until it exists and has been reviewed, a transfer the model decided to make on its own is
a path nobody designed.

**`SequentialAgent` emits a deprecation warning, and it is kept deliberately.** adk 2.9.1
says it is "deprecated in favor of Workflow" — but `Workflow` is not exported by
`google.adk.agents` in 2.9.1 at all, so there is nothing to migrate to on the pinned
version. The warning names no removal release, and its own text adds that "Workflow cannot
yet be used as an LlmAgent sub-agent", which is precisely what WS4's delegation to the
Follow-up worker requires. Switching on the strength of the warning would trade a working
primitive for an unavailable one and block the next workstream. Revisit when `Workflow`
ships and supports sub-agent transfer.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent, SequentialAgent
from google.genai import types

from app.adk.agents.care_coordinator.prompts import (
    CARE_COORDINATOR_INSTRUCTION,
    CARE_RESPONDER_INSTRUCTION,
)
from app.adk.models import adk_model_for_workload
from app.adk.registry import Transport, Workload, route_for
from app.adk.tools.document_context import get_active_document_context
from app.adk.tools.patient_context import get_patient_context
from app.adk.tools.triage_decision import submit_triage_decision

COORDINATOR_AGENT_NAME = "care_coordinator"
RESPONDER_AGENT_NAME = "care_responder"
PIPELINE_AGENT_NAME = "care_coordinator_pipeline"

FINDINGS_STATE_KEY = "care_findings"
"""Where the coordinator's working notes are stored for the rest of the invocation."""

TOOL_ALLOWLIST: dict[str, frozenset[str]] = {
    # Derived from the functions rather than spelled as literals: ADK names a tool after
    # the function it wraps, so these cannot drift out of step with the tools themselves.
    COORDINATOR_AGENT_NAME: frozenset(
        {
            get_patient_context.__name__,
            get_active_document_context.__name__,
            submit_triage_decision.__name__,
        }
    ),
    # Stated rather than omitted. Deny-by-default already gives an absent agent nothing,
    # but an explicit empty set records that the responder reaching no tool is a decision:
    # it writes prose from notes that were already gathered, and a tool call at that stage
    # would be reaching for a record the reasoning stage did not think was needed.
    RESPONDER_AGENT_NAME: frozenset(),
}
"""The allowlist `build_runner` enforces for this pipeline.

`search_patient_documents` is deliberately absent: it is WS6 work and its backing table
does not exist yet. Granting a tool before it exists would mean the allowlist stops
describing what is actually reachable.
"""


def route_for_intent(intent: str) -> str:
    """Which worker a classified turn belongs to.

    Routing is an architectural decision rather than a safety one, so it lives beside the
    agent that produces the classification rather than in `app.safety`. It moved out of
    the graph module because the websocket contract carries `route` on every turn and must
    not depend on a runtime that is being removed.
    """
    return "symptom" if intent == "symptom" else "triage"


def _generation_config(workload: Workload) -> types.GenerateContentConfig:
    """Build the per-call config from the registry's measured numbers.

    `temperature` is deliberately never set. Gemini 3.x accepts it and silently ignores
    it — measured, `temperature=0.0` produced four different answers in four calls — so
    setting it would read at the call site as a deliberate sampling choice and be nothing
    of the sort. See `_honours_sampling_parameters` in `clients/gemini.py`.
    """
    route = route_for(workload)
    config = types.GenerateContentConfig(max_output_tokens=route.max_output_tokens)

    if route.primary.transport is Transport.VERTEX_GENAI:
        # `ThinkingConfig` is a Gen AI SDK shape. The managed open-weight models are
        # reached over an OpenAI-compatible surface that has never seen it; their
        # reasoning ceiling is set as `reasoning_effort` when the model is built, at the
        # low level every measurement we have of them was taken at.
        config.thinking_config = types.ThinkingConfig(thinking_level=route.thinking_level)

    return config


def build_care_coordinator() -> SequentialAgent:
    """Assemble the two-stage Care Coordinator.

    Returns the pipeline rather than registering it anywhere: `build_runner` is still the
    only path that attaches the runtime guarantees, and this function deliberately does
    not build a `Runner` itself.
    """
    coordinator = LlmAgent(
        name=COORDINATOR_AGENT_NAME,
        model=adk_model_for_workload(Workload.TRIAGE),
        description="Reads this patient's own record and works out what their message needs.",
        instruction=CARE_COORDINATOR_INSTRUCTION,
        tools=[get_patient_context, get_active_document_context, submit_triage_decision],
        output_key=FINDINGS_STATE_KEY,
        generate_content_config=_generation_config(Workload.TRIAGE),
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )

    responder = LlmAgent(
        name=RESPONDER_AGENT_NAME,
        model=adk_model_for_workload(Workload.REPLY),
        description="Writes the reply the patient reads, in the language they wrote in.",
        instruction=CARE_RESPONDER_INSTRUCTION,
        generate_content_config=_generation_config(Workload.REPLY),
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )

    return SequentialAgent(
        name=PIPELINE_AGENT_NAME,
        description=(
            "Answers a patient chat turn: reason over their record, then write the reply."
        ),
        sub_agents=[coordinator, responder],
    )
