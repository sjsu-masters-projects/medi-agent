"""Routing a spec to the transport that can actually reach it."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.adk.models.factory import provider_for, provider_for_workload
from app.adk.registry import FLASH, GPT_OSS, Workload, route_for
from app.config import settings


@pytest.fixture(autouse=True)
def project(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "google_project_id", "test-project")


@pytest.fixture(autouse=True)
def no_real_credentials() -> object:
    """Nothing in this module may touch real ADC or construct a real Vertex client."""
    with (
        patch("app.adk.models.vertex_maas.google_adc_bearer", return_value=lambda: "t"),
        patch("app.adk.models.vertex_genai.GeminiClient") as gemini,
    ):
        gemini.return_value = MagicMock(generate=MagicMock())
        yield gemini


def test_a_maas_spec_is_built_over_the_openai_surface() -> None:
    provider = provider_for(GPT_OSS)

    assert provider.name == "gpt_oss"
    assert provider.model == "openai/gpt-oss-120b-maas"
    assert "endpoints/openapi" in provider.base_url  # type: ignore[attr-defined]


def test_a_gemini_spec_is_built_over_the_genai_sdk(no_real_credentials: MagicMock) -> None:
    provider = provider_for(FLASH)

    assert provider.name == "flash"
    assert provider.model == "gemini-3.8-flash"
    # Vertex is demanded explicitly, never inferred from whether a project happens to be
    # configured, or an unset project would silently yield an AI Studio client.
    assert no_real_credentials.call_args.kwargs["use_vertex_ai"] is True
    assert no_real_credentials.call_args.kwargs["model"] == "gemini-3.8-flash"


def test_a_workload_provider_inherits_its_measured_budget() -> None:
    """The registry budget and the transport timeout must not be able to drift apart."""
    provider = provider_for_workload(Workload.TRIAGE)

    assert route_for(Workload.TRIAGE).budget_seconds == 8.0
    assert provider._client.timeout.read == 8.0  # type: ignore[attr-defined]


def test_a_workload_without_a_budget_keeps_the_transport_default() -> None:
    """Extraction runs in an async job; nothing is waiting, so nothing is cut short."""
    assert route_for(Workload.EXTRACTION).budget_seconds is None

    provider_for_workload(Workload.EXTRACTION)  # must not raise


def test_every_workload_can_build_its_primary_provider() -> None:
    """A routing table that names a model nothing can construct is not a routing table."""
    for workload in Workload:
        assert provider_for_workload(workload) is not None


def test_an_unbuildable_transport_fails_loudly() -> None:
    """Adding a transport to the enum without a builder must not fall through a branch."""
    spec = MagicMock()
    spec.transport = "invented-transport"

    with pytest.raises(ValueError, match="No transport builder"):
        provider_for(spec)
