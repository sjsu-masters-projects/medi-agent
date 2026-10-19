"""Cloud Tasks OIDC verification for the worker endpoint (rule 23), with real signatures."""

import datetime as dt
import time

import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from google.oauth2 import id_token

from app.config import settings
from app.core import task_auth
from app.core.task_auth import require_cloud_tasks_oidc

AUDIENCE = "https://worker.example.test"
INVOKER = "invoker@synthetic.iam.gserviceaccount.com"


def _keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "synthetic")])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return key, cert.public_bytes(serialization.Encoding.PEM).decode()


KEY, CERT = _keypair()
OTHER_KEY, _ = _keypair()


def token(*, key=KEY, **claims):
    body = {
        "iss": "https://accounts.google.com",
        "aud": AUDIENCE,
        "email": INVOKER,
        "email_verified": True,
        "sub": "1234567890",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        **claims,
    }
    body = {k: v for k, v in body.items() if v is not None}
    return jwt.encode(body, key, algorithm="RS256", headers={"kid": "k1"})


@pytest.fixture
def secured(monkeypatch):
    monkeypatch.setattr(settings, "worker_mode", True)
    monkeypatch.setattr(settings, "chat_worker_url", AUDIENCE)
    monkeypatch.setattr(settings, "chat_worker_oidc_audience", "")
    monkeypatch.setattr(settings, "chat_worker_invoker_sa", INVOKER)
    monkeypatch.setattr(id_token, "_fetch_certs", lambda _request, _url: {"k1": CERT})
    task_auth._CachedCertsRequest._cache.clear()
    app = FastAPI()

    @app.post("/probe")
    async def probe(claims: dict = Depends(require_cloud_tasks_oidc)):
        return {"email": claims["email"]}

    return TestClient(app)


def call(client, value=None):
    headers = {"Authorization": f"Bearer {value}"} if value else {}
    return client.post("/probe", headers=headers)


def test_the_expected_service_account_with_the_right_audience_is_accepted(secured):
    response = call(secured, token())
    assert response.status_code == 200 and response.json() == {"email": INVOKER}


def test_a_missing_or_malformed_token_is_refused_with_401(secured):
    assert call(secured).status_code == 401
    assert secured.post("/probe", headers={"Authorization": "Basic abc"}).status_code == 401
    assert call(secured, "not-a-jwt").status_code == 401


@pytest.mark.parametrize(
    "case",
    [
        {"aud": "https://other.example.test"},
        {"iss": "https://evil.example.test"},
        {"exp": int(time.time()) - 600, "iat": int(time.time()) - 900},
    ],
    ids=["wrong-audience", "wrong-issuer", "expired"],
)
def test_a_token_that_is_not_for_this_worker_is_refused_with_401(secured, case):
    assert call(secured, token(**case)).status_code == 401


def test_a_token_signed_by_another_key_is_refused_with_401(secured):
    assert call(secured, token(key=OTHER_KEY)).status_code == 401


def test_a_valid_google_token_for_another_account_is_refused_with_403(secured):
    assert call(secured, token(email="someone@else.iam.gserviceaccount.com")).status_code == 403
    assert call(secured, token(email_verified=False)).status_code == 403
    assert call(secured, token(email=None)).status_code == 403


def test_an_explicit_audience_setting_is_what_must_match(secured, monkeypatch):
    monkeypatch.setattr(settings, "chat_worker_oidc_audience", "https://custom.example.test")
    assert call(secured, token()).status_code == 401
    assert call(secured, token(aud="https://custom.example.test")).status_code == 200


def test_missing_configuration_fails_closed(secured, monkeypatch):
    monkeypatch.setattr(settings, "chat_worker_invoker_sa", "")
    assert call(secured, token()).status_code == 403
    monkeypatch.setattr(settings, "chat_worker_invoker_sa", INVOKER)
    monkeypatch.setattr(settings, "chat_worker_url", "")
    assert call(secured, token()).status_code == 403


def test_the_route_is_disabled_outside_worker_mode(secured, monkeypatch):
    monkeypatch.setattr(settings, "worker_mode", False)
    assert call(secured, token()).status_code == 404


def test_signing_certificates_are_cached_and_bounded(monkeypatch):
    calls = []

    class Response:
        status = 200
        data = b"{}"

    def fake_call(self, url, method="GET", body=None, headers=None, timeout=None, **kwargs):
        calls.append(timeout)
        return Response()

    monkeypatch.setattr(task_auth.google_requests.Request, "__call__", fake_call)
    task_auth._CachedCertsRequest._cache.clear()
    request = task_auth._CachedCertsRequest()
    request("https://certs.example.test")
    request("https://certs.example.test")
    assert calls == [task_auth.CERTS_TIMEOUT_SECONDS]  # one fetch, with a short timeout
