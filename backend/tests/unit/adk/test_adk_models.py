"""Turning a routed spec into the model object the agent runtime actually calls.

Every defect this module can have is silent. A Gemini model built from the environment
answers correctly — from AI Studio, on another quota, under different data handling, and
not from the service the registry says serves it. A LiteLLM model built with a token
captured at construction works all afternoon and fails an hour later. Neither shows up in
the answer, so both are pinned here.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from google.adk.models import Gemini
from google.adk.models.lite_llm import LiteLlm

from app.adk.models.adk_models import BearerLiteLlm, adk_model_for, adk_model_for_workload
from app.adk.registry import FLASH, GPT_OSS, ModelSpec, Transport, Workload
from app.config import settings


@pytest.fixture(autouse=True)
def project(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(settings, "google_project_id", "test-project")
    monkeypatch.setattr(settings, "vertex_ai_location", "us-central1")
    return "test-project"


@pytest.fixture(autouse=True)
def no_real_credentials() -> Iterator[None]:
    """Nothing in this module may resolve real Application Default Credentials.

    Without this the workload-level builders reach `google_adc_bearer`, which succeeds on
    a developer machine that happens to be logged in and fails in CI — a test that passes
    for a reason unrelated to what it claims to check.
    """
    with patch(
        "app.adk.models.adk_models.google_adc_bearer",
        return_value=lambda: "adc-token",
    ):
        yield


def _bearer() -> str:
    return "test-token"


@contextmanager
def _capturing_genai_client() -> Iterator[tuple[MagicMock, list[Any]]]:
    """Record the constructor call while still returning a genuine client.

    `Gemini.client` is a validated pydantic field, so a `MagicMock` is rejected outright —
    the injected object has to be a real `genai.Client`. Constructing one resolves no
    credentials and performs no I/O, so this stays offline.
    """
    from google import genai

    real = genai.Client
    created: list[Any] = []

    def build(**kwargs: Any) -> Any:
        client = real(**kwargs)
        created.append(client)
        return client

    with patch("google.genai.Client", side_effect=build) as constructor:
        yield constructor, created


# ---------------------------------------------------------------------------
# Gemini — the transport must never be inferred from the environment
# ---------------------------------------------------------------------------


def test_gemini_is_built_against_vertex_explicitly() -> None:
    """ADK would otherwise construct a client from env and land on AI Studio."""
    with _capturing_genai_client() as (constructor, _created):
        model = adk_model_for(FLASH)

    assert isinstance(model, Gemini)
    assert model.model == "gemini-3.8-flash"
    assert constructor.call_args.kwargs["vertexai"] is True
    assert constructor.call_args.kwargs["project"] == "test-project"
    assert constructor.call_args.kwargs["location"] == "us-central1"


def test_the_explicit_client_is_the_one_the_model_uses() -> None:
    """Injecting a client only helps if ADK actually prefers it over building its own."""
    with _capturing_genai_client() as (_constructor, created):
        model = adk_model_for(FLASH)

    assert len(created) == 1
    assert model.client is created[0]


def test_an_unset_project_is_refused_rather_than_downgraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact condition under which ADK silently builds an AI Studio client instead."""
    monkeypatch.setattr(settings, "google_project_id", "")

    with pytest.raises(ValueError, match="GOOGLE_PROJECT_ID"):
        adk_model_for(FLASH)


def test_gemini_does_not_go_through_litellm() -> None:
    """The Gen AI SDK takes a bare id; LiteLLM would need a prefixed one."""
    with _capturing_genai_client():
        model = adk_model_for(FLASH)

    assert not isinstance(model, LiteLlm)


# ---------------------------------------------------------------------------
# gpt-oss — the prefix and the credential
# ---------------------------------------------------------------------------


def test_the_managed_model_carries_the_doubled_prefix() -> None:
    """Single-prefixed, Vertex answers 400: LiteLLM strips its own provider prefix."""
    model = adk_model_for(GPT_OSS, bearer_token=_bearer)

    assert model.model == "openai/openai/gpt-oss-120b-maas"


def test_the_managed_model_targets_the_openai_compatible_endpoint() -> None:
    model = adk_model_for(GPT_OSS, bearer_token=_bearer)

    assert model._additional_args["api_base"] == (
        "https://us-central1-aiplatform.googleapis.com"
        "/v1/projects/test-project/locations/us-central1/endpoints/openapi"
    )


def test_the_bearer_is_not_forwarded_as_a_completion_argument() -> None:
    """`_additional_args` is sent to LiteLLM verbatim; a stray `bearer` would go with it."""
    model = adk_model_for(GPT_OSS, bearer_token=_bearer)

    assert "bearer" not in model._additional_args


@pytest.mark.asyncio
async def test_the_token_is_refreshed_on_every_request() -> None:
    """A token frozen at construction works in a demo and fails an hour later."""
    issued: list[str] = []

    def rotating() -> str:
        issued.append(f"token-{len(issued)}")
        return issued[-1]

    seen: list[str] = []

    async def fake_parent(self: Any, llm_request: Any, stream: bool = False) -> Any:
        seen.append(self._additional_args["api_key"])
        yield "response"

    model = adk_model_for(GPT_OSS, bearer_token=rotating)

    with patch.object(LiteLlm, "generate_content_async", fake_parent):
        async for _ in model.generate_content_async(MagicMock()):
            pass
        async for _ in model.generate_content_async(MagicMock()):
            pass

    # Construction seeded token-0; the two calls must each have taken a fresh one.
    assert seen == ["token-1", "token-2"]


@pytest.mark.asyncio
async def test_the_response_stream_is_passed_through_untouched() -> None:
    """Refreshing a credential must not change what the model said."""

    async def fake_parent(self: Any, llm_request: Any, stream: bool = False) -> Any:
        yield "first"
        yield "second"

    model = adk_model_for(GPT_OSS, bearer_token=_bearer)

    with patch.object(LiteLlm, "generate_content_async", fake_parent):
        received = [chunk async for chunk in model.generate_content_async(MagicMock())]

    assert received == ["first", "second"]


def test_the_managed_model_is_a_litellm_model() -> None:
    model = adk_model_for(GPT_OSS, bearer_token=_bearer)

    assert isinstance(model, BearerLiteLlm)
    assert isinstance(model, LiteLlm)


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def test_a_workload_gets_the_model_the_registry_routes_it_to() -> None:
    """Triage leads with gpt-oss on the measured latency, so this must not be Flash."""
    model = adk_model_for_workload(Workload.TRIAGE)

    assert model.model == "openai/openai/gpt-oss-120b-maas"


def test_every_workload_can_build_its_primary_model() -> None:
    """A routing table naming a model the runtime cannot construct is not a routing table."""
    with _capturing_genai_client():
        for workload in Workload:
            assert adk_model_for_workload(workload) is not None


def test_an_unknown_transport_fails_loudly() -> None:
    """A transport added to the enum without a builder must not fall through a branch."""
    spec = MagicMock(spec=ModelSpec)
    spec.transport = "invented-transport"

    with pytest.raises(ValueError, match="No ADK model builder"):
        adk_model_for(spec)


def test_the_two_transports_stay_paired_with_their_builders() -> None:
    """Guards the pairing: the two branches are not interchangeable."""
    assert FLASH.transport is Transport.VERTEX_GENAI
    assert GPT_OSS.transport is Transport.VERTEX_MAAS_OPENAI
