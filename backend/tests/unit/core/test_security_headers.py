"""Response headers and production docs gating.

Both are the kind of protection that is silently lost in a refactor and noticed only
after it matters, so each header is pinned by name.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.security_headers import SecurityHeadersMiddleware


def _app() -> FastAPI:
    application = FastAPI()
    application.add_middleware(SecurityHeadersMiddleware)

    @application.get("/probe")
    def probe() -> dict[str, bool]:
        return {"ok": True}

    return application


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "no-referrer"),
        ("Permissions-Policy", "geolocation=(), microphone=(), camera=()"),
    ],
)
def test_each_security_header_is_present(header: str, expected: str) -> None:
    response = TestClient(_app()).get("/probe")

    assert response.headers[header] == expected


def test_content_security_policy_denies_everything_by_default() -> None:
    """A JSON API renders nothing, so nothing needs to be allowed."""
    response = TestClient(_app()).get("/probe")

    csp = response.headers["Content-Security-Policy"]
    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp


def test_hsts_is_sent_over_https() -> None:
    client = TestClient(_app(), base_url="https://api.example.test")

    response = client.get("/probe")

    assert "max-age=" in response.headers["Strict-Transport-Security"]


def test_hsts_is_withheld_over_plain_http_outside_production() -> None:
    """Pinning HSTS from a local http:// dev server poisons the developer's browser."""
    response = TestClient(_app(), base_url="http://localhost").get("/probe")

    assert "Strict-Transport-Security" not in response.headers


def test_a_route_may_set_its_own_policy() -> None:
    application = _app()

    @application.get("/custom")
    def custom():
        from fastapi.responses import JSONResponse

        return JSONResponse({"ok": True}, headers={"Referrer-Policy": "origin"})

    response = TestClient(application).get("/custom")

    assert response.headers["Referrer-Policy"] == "origin"
