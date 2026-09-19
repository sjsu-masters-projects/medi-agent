"""Turn a routing decision into something that can answer a request.

Callers ask for a workload and get a provider. They do not choose a transport, a model
id, or an endpoint — those are the registry's answer, and spreading them back out to call
sites is how a routing table stops describing what actually runs.
"""

from __future__ import annotations

from app.adk.models.vertex_genai import build_genai_provider
from app.adk.models.vertex_maas import build_maas_provider
from app.adk.registry import ModelSpec, Transport, Workload, route_for
from app.services.generation_providers import TextProvider

# Used when a workload declares no budget. The asynchronous workloads have nothing
# waiting on them, so they get the transport's own patience rather than a limit invented
# here — but they still get a finite one, because no request should hang forever.
_MAAS_DEFAULT_TIMEOUT_SECONDS = 90.0
_GENAI_DEFAULT_TIMEOUT_SECONDS = 60.0


def provider_for(spec: ModelSpec, *, timeout_seconds: float | None = None) -> TextProvider:
    """Build the provider that reaches `spec` over its declared transport."""
    if spec.transport is Transport.VERTEX_MAAS_OPENAI:
        return build_maas_provider(
            spec,
            timeout_seconds=(
                _MAAS_DEFAULT_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
            ),
        )
    if spec.transport is Transport.VERTEX_GENAI:
        return build_genai_provider(
            spec,
            timeout_seconds=(
                _GENAI_DEFAULT_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
            ),
        )
    # Deliberately exhaustive rather than defaulted: a transport added to the enum without
    # a builder here must fail loudly at the call, not fall through to whichever branch
    # happens to be last.
    raise ValueError(f"No transport builder is registered for {spec.transport!r}")


def provider_for_workload(workload: Workload) -> TextProvider:
    """Build the primary provider for a workload, bounded by its measured budget.

    The budget is passed as the transport timeout so the two cannot drift: a workload
    whose registry budget says 8 seconds does not get a provider willing to wait 90.
    Workloads with no budget — the asynchronous ones — keep the transport default.
    """
    route = route_for(workload)
    return provider_for(route.primary, timeout_seconds=route.budget_seconds)
