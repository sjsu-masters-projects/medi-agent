"""Models shaped for the agent runtime, as distinct from the text-provider transports.

`models/factory.py` answers "what can satisfy a `GenerationRequest`" and returns a
`TextProvider` — the contract the existing graph path and the evaluation harness both use.
ADK asks a different question: an `LlmAgent` wants a `BaseLlm`, which owns its own request
shape, tool declarations and streaming. The registry stays the single source for *which*
model runs a workload; this is the second of two adapters that reach it.

**A bare model string is not safe here, and this is the reason this module exists.** ADK
resolves `model="gemini-3.8-flash"` through its registry to the `Gemini` class, which
builds a `google.genai.Client` from environment variables — `GOOGLE_GENAI_USE_VERTEXAI`,
`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`. This application sets none of them and
never writes to `os.environ`, so that client would fall back to AI Studio against
`GOOGLE_API_KEY`: a different quota, different data handling, and a different service from
the one the registry says serves this model. That is the same silent downgrade WS1 removed
from `clients/gemini.py`, reappearing one layer up. So the client is built explicitly and
injected, which ADK supports for exactly this purpose.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from google.adk.models import BaseLlm, Gemini
from google.adk.models.lite_llm import LiteLlm
from pydantic import PrivateAttr

from app.adk.models.vertex_maas import litellm_model_id, vertex_openapi_base_url
from app.adk.registry import ModelSpec, Transport, Workload, route_for
from app.clients.vertex_auth import google_adc_bearer
from app.config import settings

logger = logging.getLogger(__name__)


class BearerLiteLlm(LiteLlm):
    """A LiteLLM model whose bearer token is refreshed on every request.

    `LiteLlm` copies its constructor kwargs into `_additional_args` and merges that dict
    into the completion arguments on each call. That makes `api_key` a value frozen at
    construction — and a Google access token lasts an hour, which is shorter than the life
    of a process serving requests. A token captured once works in a demo and fails the
    next morning, as an authentication error that reads like a model outage.

    Refreshing inside `generate_content_async` is what makes it per-request:
    `_additional_args` is read at call time, so replacing the entry here reaches the very
    next completion rather than the next process.
    """

    _bearer_token: Callable[[], str] | None = PrivateAttr(default=None)

    def __init__(self, model: str, *, bearer: Callable[[], str], **kwargs: Any) -> None:
        # `bearer` is keyword-only and deliberately not forwarded to `super()`: anything
        # passed through lands in `_additional_args` and would be sent to LiteLLM as a
        # completion argument it does not understand.
        super().__init__(model=model, **kwargs)
        self._bearer_token = bearer

    async def generate_content_async(self, llm_request: Any, stream: bool = False) -> Any:
        """Refresh the credential, then defer entirely to LiteLLM."""
        if self._bearer_token is not None:
            self._additional_args["api_key"] = self._bearer_token()
        async for response in super().generate_content_async(llm_request, stream=stream):
            yield response


def _vertex_genai_client() -> Any:
    """Build a Gen AI client pinned to Vertex, never inferred from the environment."""
    if not settings.google_project_id:
        # Refused rather than allowed to fall through: an unset project is precisely the
        # condition under which ADK would build an AI Studio client instead, and that
        # substitution is silent at construction and invisible in the answer.
        raise ValueError(
            "GOOGLE_PROJECT_ID must be set to reach Gemini on Vertex. Without it the agent "
            "runtime would construct an AI Studio client for a model the registry routes "
            "to Vertex."
        )

    from google import genai

    return genai.Client(
        vertexai=True,
        project=settings.google_project_id,
        location=settings.gemini_vertex_ai_location,
    )


def adk_model_for(
    spec: ModelSpec,
    *,
    bearer_token: Callable[[], str] | None = None,
) -> BaseLlm:
    """Build the `BaseLlm` an `LlmAgent` needs in order to reach `spec`."""
    if spec.transport is Transport.VERTEX_GENAI:
        # The id stays bare; the transport is carried by the injected client rather than
        # by a prefix, which is why the same spec cannot be handed to the LiteLLM branch.
        return Gemini(model=spec.model_id, client=_vertex_genai_client())

    if spec.transport is Transport.VERTEX_MAAS_OPENAI:
        bearer = bearer_token or google_adc_bearer()
        return BearerLiteLlm(
            # Doubled prefix, for the reason recorded in `litellm_model_id`: LiteLLM eats
            # the first `openai/` as its own provider prefix, and Vertex rejects the bare
            # id that would otherwise arrive.
            model=litellm_model_id(spec),
            bearer=bearer,
            api_base=vertex_openapi_base_url(
                settings.google_project_id, settings.vertex_ai_location
            ),
            # Seeded so the object is coherent on its own; every call replaces it.
            api_key=bearer(),
        )

    # Exhaustive rather than defaulted, matching `provider_for`: a transport added to the
    # enum without a builder here must fail at the call rather than fall through to
    # whichever branch happens to be last.
    raise ValueError(f"No ADK model builder is registered for {spec.transport!r}")


def adk_model_for_workload(workload: Workload) -> BaseLlm:
    """Build the primary model for a workload, as the registry routes it."""
    return adk_model_for(route_for(workload).primary)
