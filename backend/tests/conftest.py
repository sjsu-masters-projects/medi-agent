"""
Pytest configuration and shared fixtures.

Fixtures defined here are available to ALL test files automatically.
"""

import os

# Tests must never inherit live observability or AI-service credentials from the
# repository-level .env file. Set these before importing app.main, which creates
# the application and initializes integrations at module import time.
os.environ["ENVIRONMENT"] = "test"
os.environ["BACKEND_SENTRY_DSN"] = ""
os.environ["DEEPGRAM_API_KEY"] = ""
os.environ["A2A_RETRY_WORKER_ENABLED"] = "false"

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import authorization_audit_service


@pytest.fixture(autouse=True)
def denial_audit(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture authorization-denial audit writes instead of sending them to Supabase.

    Autouse because every 403 in the suite now writes an audit record; without this the
    denial path would reach for a real client and block until the timeout, which is the
    class of hang REV-001 removed from CI.

    Request it by name to assert on what was recorded.
    """
    recorded: list[dict[str, Any]] = []

    async def _capture(payload: dict[str, Any]) -> None:
        recorded.append(dict(payload))

    async def _no_refine(
        reason_code: str,
        actor_id: str | None,
        target_type: str | None,
        target_id: str | None,
    ) -> str:
        return reason_code

    # Both halves of the audit path touch the database: the write, and the read that
    # refines a care-team reason code. Neither may run against a real client here.
    # `classify_care_team_denial` is unit-tested directly against a fake client instead.
    monkeypatch.setattr(authorization_audit_service, "_insert_row", _capture)
    monkeypatch.setattr(authorization_audit_service, "_refine", _no_refine)
    return recorded


@pytest.fixture()
def client() -> TestClient:
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_process_limits() -> None:
    """Per-process recovery limits and provider-status state must not leak across tests."""
    from app.clients.resend import ResendClient
    from app.middleware.rate_limit import (
        password_reset_client_limiter,
        password_reset_email_limiter,
    )

    password_reset_client_limiter._events.clear()
    password_reset_email_limiter._events.clear()
    ResendClient._status_unavailable = False


class _OfflineProvider:
    """A text provider that refuses every call, so a test can never spend a real model call."""

    async def generate(self, *_args: Any, **_kwargs: Any) -> Any:
        from app.models.generation import GenerationErrorCode, GenerationProviderError

        raise GenerationProviderError(
            GenerationErrorCode.CONFIGURATION, "Model calls are disabled in tests"
        )


@pytest.fixture(autouse=True)
def no_real_model_calls(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """No test reaches a real model, whatever credentials (ADC, keys, HOME) the machine has.

    Tests that need model output patch the provider, router or workload function themselves;
    those patches are applied later and take precedence over these refusals.
    """
    # These modules assert how the real provider builders construct clients (no network).
    if request.module.__name__.rsplit(".", 1)[-1] in {"test_adk_models", "test_provider_factory"}:
        return
    from app.adk.models import factory

    monkeypatch.setattr(factory, "build_maas_provider", lambda *_a, **_k: _OfflineProvider())
    monkeypatch.setattr(factory, "build_genai_provider", lambda *_a, **_k: _OfflineProvider())

    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("Model clients are disabled in tests")

    from google import genai

    monkeypatch.setattr(genai, "Client", refuse)
