"""Open-weight managed models on Vertex, over its OpenAI-compatible surface.

Vertex serves partner and open-weight models behind a `/chat/completions` endpoint that
speaks the OpenAI dialect but authenticates with a Google bearer token. That combination
is why this goes through `OpenAICompatibleTextProvider` with an ADC token callable rather
than through the Gen AI SDK, which does not front these models.

Verified live on 2026-09-17 against `openai/gpt-oss-120b-maas`: both the global and the
regional endpoint form answer correctly. The global form is used here because it is the
form the run behind our routing decision used, it answers most consistently (0.34-0.46 s
against 0.56-10.18 s regional over alternating probes, the outlier being a cold start),
and it matches the `location=global` the Gemini client already uses — so one project
setting describes both transports instead of two that can drift apart.
"""

from __future__ import annotations

from collections.abc import Callable

from app.adk.registry import ModelSpec, Transport
from app.clients.openai_compatible import OpenAICompatibleTextProvider
from app.clients.vertex_auth import google_adc_bearer
from app.config import settings

# Vertex exposes the OpenAI dialect under this suffix rather than at the API root.
_OPENAPI_SUFFIX = "endpoints/openapi"

# LiteLLM's provider prefix, which it consumes and removes. See `litellm_model_id`.
_LITELLM_PROVIDER_PREFIX = "openai/"

# gpt-oss always reasons, and at its default effort it thinks for far longer than a chat
# turn can afford. Every measurement we have of it was taken at low effort, so deploying
# it at any other effort would mean deploying something we have not measured.
_DEFAULT_REASONING_EFFORT = "low"


def vertex_openapi_base_url(project_id: str, location: str = "global") -> str:
    """Build the OpenAI-compatible base URL for a project.

    The location appears in the path and, for regional endpoints, in the host as well.
    `global` is the exception: its host carries no region prefix, so the two forms cannot
    be produced by a single f-string with the region substituted in both places.
    """
    if not project_id:
        raise ValueError(
            "GOOGLE_PROJECT_ID must be set to reach Vertex managed models. Without it the "
            "URL would be built with an empty project segment and every call would 404."
        )
    host = (
        "aiplatform.googleapis.com"
        if location == "global"
        else f"{location}-aiplatform.googleapis.com"
    )
    return f"https://{host}/v1/projects/{project_id}/locations/{location}/{_OPENAPI_SUFFIX}"


def litellm_model_id(spec: ModelSpec) -> str:
    """The model string LiteLLM must be given so Vertex receives the right one.

    **The doubled prefix is deliberate and load-bearing.** LiteLLM reads the leading
    segment of a model id as *its own* provider prefix and strips it before dispatching.
    Our id already begins with `openai/` because that is the publisher namespace Vertex's
    OpenAI-compatible surface requires — so passing `openai/gpt-oss-120b-maas` means
    LiteLLM eats the prefix and forwards the bare `gpt-oss-120b-maas`, which Vertex
    rejects:

        400 Malformed publisher model (`model`: 'gpt-oss-120b-maas') for the 'openapi'
            request endpoint ID; expected '<publisher>/<model>'.

    Measured 2026-09-17 against the live endpoint: the single prefix fails, the doubled
    prefix succeeds and the response comes back reporting `openai/gpt-oss-120b-maas`,
    confirming the full id arrived. Setting `custom_llm_provider="openai"` does **not**
    fix it on its own — it still strips.

    This reads exactly like a typo, so it is produced here rather than written into the
    registry: `ModelSpec.model_id` stays the true wire id that the raw HTTP transport
    sends verbatim, and only the LiteLLM adapter adds the extra hop it needs.
    """
    if spec.transport is not Transport.VERTEX_MAAS_OPENAI:
        raise ValueError(
            f"{spec.key} is reached over {spec.transport.value}; LiteLLM is only used for "
            "Vertex's OpenAI-compatible surface"
        )
    return f"{_LITELLM_PROVIDER_PREFIX}{spec.model_id}"


def build_maas_provider(
    spec: ModelSpec,
    *,
    timeout_seconds: float = 90.0,
    max_retries: int = 2,
    reasoning_effort: str | None = _DEFAULT_REASONING_EFFORT,
    location: str = "global",
    bearer_token: Callable[[], str] | None = None,
) -> OpenAICompatibleTextProvider:
    """Build a text provider for a managed open-weight model on Vertex.

    `native_structured_output` is deliberately left on even though this model honours a
    schema only sometimes. Asking for the schema still helps; the measured 3-in-10
    violation rate means the *caller* must validate, and `ModelSpec.honours_response_schema`
    is what tells it to. Turning the request off here would remove the help without
    removing the need to validate.
    """
    if spec.transport is not Transport.VERTEX_MAAS_OPENAI:
        raise ValueError(
            f"{spec.key} is reached over {spec.transport.value}, not Vertex's "
            "OpenAI-compatible surface"
        )

    return OpenAICompatibleTextProvider(
        name=spec.key,
        model=spec.model_id,
        base_url=vertex_openapi_base_url(settings.google_project_id, location),
        timeout_seconds=timeout_seconds,
        native_structured_output=True,
        reasoning_effort=reasoning_effort,
        max_retries=max_retries,
        # Resolved per request rather than frozen, because an hour-old token is the
        # failure mode that ends long runs.
        bearer_token=bearer_token or google_adc_bearer(),
    )
