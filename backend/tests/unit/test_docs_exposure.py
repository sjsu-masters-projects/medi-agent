"""The interactive API docs must not be reachable in production.

`/openapi.json` enumerates every route and request shape, including the clinician and
SMART import surface. Browser clients never read it; it is only useful to someone
mapping the API.
"""

import pytest

import app.config
import app.core.security_headers
import app.main


def _app_for(environment: str, monkeypatch: pytest.MonkeyPatch):
    """Build an app as if the process had started with this ENVIRONMENT.

    `settings` is bound at import time in several modules, so patching the attribute on
    each of them is what actually changes the behaviour under test.
    """
    settings = app.config.Settings(  # type: ignore[call-arg]
        supabase_url="https://test.supabase.co",
        supabase_anon_key="test",
        supabase_service_role_key="test",
        supabase_jwt_secret="test",
        environment=environment,
        a2a_retry_worker_enabled=False,
    )
    monkeypatch.setattr(app.config, "settings", settings)
    monkeypatch.setattr(app.main, "settings", settings)
    monkeypatch.setattr(app.core.security_headers, "settings", settings)
    return app.main.create_app()


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_docs_are_not_served_in_production(path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(_app_for("production", monkeypatch))

    assert client.get(path).status_code == 404


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_docs_remain_available_outside_production(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    client = TestClient(_app_for("development", monkeypatch))

    assert client.get(path).status_code == 200


def test_health_still_responds_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gating the docs must not take the liveness probe with it."""
    from fastapi.testclient import TestClient

    client = TestClient(_app_for("production", monkeypatch))

    assert client.get("/health").status_code == 200
