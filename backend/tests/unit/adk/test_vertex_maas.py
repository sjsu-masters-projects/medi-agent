"""Wiring the managed open-weight transport.

The HTTP behaviour itself is covered by `test_openai_compatible.py`. What is tested here
is the wiring, because every defect this module can have is a silent one: a URL built
with an empty project segment, a model id stripped of the prefix Vertex requires, a token
frozen at construction, or a reasoning effort we never measured.
"""

from __future__ import annotations

import pytest

from app.adk.models.vertex_maas import (
    build_maas_provider,
    litellm_model_id,
    vertex_openapi_base_url,
)
from app.adk.registry import FLASH, GPT_OSS, ModelSpec, Transport
from app.config import settings


@pytest.fixture
def project(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(settings, "google_project_id", "test-project")
    monkeypatch.setattr(settings, "vertex_ai_location", "us-central1")
    return "test-project"


def _bearer() -> str:
    return "test-token"


def test_the_global_host_carries_no_region_prefix() -> None:
    """The global form is not the regional form with the region substituted in."""
    assert vertex_openapi_base_url("p") == (
        "https://aiplatform.googleapis.com/v1/projects/p/locations/global/endpoints/openapi"
    )


def test_a_regional_host_carries_the_region_in_both_places() -> None:
    assert vertex_openapi_base_url("p", "us-central1") == (
        "https://us-central1-aiplatform.googleapis.com"
        "/v1/projects/p/locations/us-central1/endpoints/openapi"
    )


def test_an_empty_project_is_refused_rather_than_interpolated() -> None:
    """An empty segment builds a URL that 404s on every call and looks like an outage."""
    with pytest.raises(ValueError, match="GOOGLE_PROJECT_ID"):
        vertex_openapi_base_url("")


def test_the_provider_keeps_the_publisher_prefixed_model_id(project: str) -> None:
    provider = build_maas_provider(GPT_OSS, bearer_token=_bearer)

    assert provider.model == "openai/gpt-oss-120b-maas"
    assert provider.name == "gpt_oss"


def test_the_provider_targets_the_configured_endpoint(project: str) -> None:
    provider = build_maas_provider(GPT_OSS, bearer_token=_bearer)

    assert provider.base_url == (
        "https://us-central1-aiplatform.googleapis.com"
        "/v1/projects/test-project/locations/us-central1/endpoints/openapi"
    )


def test_a_model_on_another_transport_is_refused(project: str) -> None:
    """Flash is reached through the Gen AI SDK; building it here would use the wrong id."""
    with pytest.raises(ValueError, match="not Vertex's"):
        build_maas_provider(FLASH, bearer_token=_bearer)


def test_reasoning_effort_defaults_to_the_level_we_measured(project: str) -> None:
    """Every number we have for this model was taken at low effort.

    Deploying it at the default effort would mean deploying a configuration that has
    never been evaluated, and one that thinks for longer than a chat turn allows.
    """
    assert build_maas_provider(GPT_OSS, bearer_token=_bearer).reasoning_effort == "low"


def test_the_schema_is_still_requested_despite_imperfect_conformance(project: str) -> None:
    """Asking helps even at a 3-in-10 violation rate; the caller validates regardless.

    Turning the request off would remove the help without removing the need to validate.
    """
    provider = build_maas_provider(GPT_OSS, bearer_token=_bearer)

    assert provider.native_structured_output is True
    assert GPT_OSS.honours_response_schema is False


def test_the_token_is_resolved_per_request_not_frozen(project: str) -> None:
    """An access token outlives neither a long run nor a long-lived process."""
    issued: list[str] = []

    def rotating() -> str:
        issued.append(f"token-{len(issued)}")
        return issued[-1]

    provider = build_maas_provider(GPT_OSS, bearer_token=rotating)

    first = provider._request_headers()["Authorization"]
    second = provider._request_headers()["Authorization"]

    assert first == "Bearer token-0"
    assert second == "Bearer token-1"


def test_retries_are_bounded(project: str) -> None:
    provider = build_maas_provider(GPT_OSS, bearer_token=_bearer, max_retries=2)

    assert provider.max_retries == 2


def test_litellm_needs_the_prefix_doubled() -> None:
    """Measured, not guessed: the single prefix returns HTTP 400 from Vertex.

    LiteLLM strips the leading segment as its own provider prefix, so `openai/<model>`
    arrives at Vertex as the bare `<model>` and is refused with "Malformed publisher
    model ... expected '<publisher>/<model>'". Doubling it makes the real id arrive, and
    the live response confirmed it by reporting `openai/gpt-oss-120b-maas` back.

    This exists because the doubled prefix reads as a typo and will be "cleaned up"
    otherwise — silently breaking a model that is deployed and working.
    """
    assert litellm_model_id(GPT_OSS) == "openai/openai/gpt-oss-120b-maas"


def test_the_registry_keeps_the_true_wire_id() -> None:
    """Only the LiteLLM adapter doubles it; the raw HTTP transport sends it verbatim."""
    assert GPT_OSS.model_id == "openai/gpt-oss-120b-maas"


def test_litellm_ids_are_refused_for_a_non_maas_model() -> None:
    """Flash goes through the Gen AI SDK, which takes a bare id and no LiteLLM at all."""
    with pytest.raises(ValueError, match="only used for"):
        litellm_model_id(FLASH)


def test_an_unknown_transport_cannot_be_built_here(project: str) -> None:
    spec = ModelSpec(
        key="mystery",
        model_id="mystery-1",
        transport=Transport.VERTEX_GENAI,
        honours_response_schema=True,
    )

    with pytest.raises(ValueError):
        build_maas_provider(spec, bearer_token=_bearer)
