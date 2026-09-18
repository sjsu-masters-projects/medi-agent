"""Make the model that answered reachable by the tools that write records.

A candidate written during an agent run has to record which model produced it, for the
same reason the legacy ingestion path now does: without it, a model swap leaves no way to
tell which stored facts came from which model, and therefore no way to re-review or retire
them selectively. `source_provenances.model_version` has had room for this since migration
017 and went unfilled for exactly this reason — nothing carried the answer forward.

The model is stamped into session state here and read by candidate-writing tools, rather
than each tool guessing from configuration. Configuration is the wrong source: the router
falls back, so the configured model is not necessarily the one that replied, and a
confidently wrong provenance stamp is worse than an absent one.

**The keys are `temp:`-scoped on purpose.** ADK's `append_event` applies temp state to the
session before trimming the delta, explicitly so later agents and tools in the same
invocation can read it, and then strips it before anything is persisted. That is precisely
what is wanted: available to the tool that writes the candidate this turn, and never
accumulating a stale "last model used" in durable session state.
"""

from __future__ import annotations

import logging
from typing import Any

from google.adk.plugins import BasePlugin

logger = logging.getLogger(__name__)

PROVENANCE_MODEL_KEY = "temp:provenance.model_version"
"""Session-state key holding the model that produced this turn's answer."""

PROVENANCE_AGENT_KEY = "temp:provenance.agent"
"""Session-state key holding the agent that made the call."""


class ProvenancePlugin(BasePlugin):
    """Stamp the answering model into state for candidate-writing tools to read."""

    def __init__(self) -> None:
        super().__init__(name="provenance")

    async def after_model_callback(self, *, callback_context: Any, llm_response: Any) -> None:
        """Record which model answered. Returning None leaves the response unmodified."""
        if getattr(llm_response, "partial", False):
            # A streaming chunk. The final response carries the authoritative model.
            return None

        model = getattr(llm_response, "model_version", None)
        if not model:
            # Deliberately leaves the key unset rather than writing an empty value: a tool
            # reading a blank stamp cannot tell "no model recorded" from "recorded
            # nothing", and an absent stamp is the honest signal.
            logger.debug("Model response carried no model_version; provenance unset")
            return None

        state = getattr(callback_context, "state", None)
        if state is None:
            logger.warning("No session state available; provenance was not stamped")
            return None

        try:
            state[PROVENANCE_MODEL_KEY] = str(model)
            agent = getattr(callback_context, "agent_name", None)
            if agent:
                state[PROVENANCE_AGENT_KEY] = str(agent)
        except Exception:
            # Bookkeeping must not cost the patient their answer. A candidate written
            # without a stamp is the old behaviour, which is recoverable; a failed turn
            # is not.
            logger.error("Could not stamp provenance into session state", exc_info=True)
        return None
