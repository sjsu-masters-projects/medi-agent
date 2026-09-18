"""Transports that turn a `ModelSpec` into something that can answer a request.

Each transport in `app.adk.registry.Transport` has a builder here. Keeping them apart
from the registry means the routing table stays readable as data, and a change to how a
model is reached never edits the table that says which model is used.
"""

from app.adk.models.adk_models import (
    BearerLiteLlm,
    adk_model_for,
    adk_model_for_workload,
)
from app.adk.models.factory import provider_for, provider_for_workload
from app.adk.models.vertex_genai import build_genai_provider
from app.adk.models.vertex_maas import (
    build_maas_provider,
    litellm_model_id,
    vertex_openapi_base_url,
)

__all__ = [
    "BearerLiteLlm",
    "adk_model_for",
    "adk_model_for_workload",
    "build_genai_provider",
    "build_maas_provider",
    "litellm_model_id",
    "provider_for",
    "provider_for_workload",
    "vertex_openapi_base_url",
]
