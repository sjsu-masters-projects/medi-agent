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
