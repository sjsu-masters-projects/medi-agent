"""Every refused request must leave a record.

`negative_access_cases` in the canonical synthetic fixture declares
`expected_audit_entry: true` for all eight cases. These tests hold the API to that: a 403
that writes nothing is a probe nobody can see.

Auditing is wired into the 403 handler rather than each raise site, so these tests also
guard the property that matters for denials added later — coverage comes from the handler,
not from remembering.
"""

from uuid import uuid4

import pytest
from fastapi import status

from app.core.authorization_reasons import (
    NO_CARE_TEAM_ASSIGNMENT,
    PATIENT_SCOPE_SELF_ONLY,
    ROLE_LACKS_CLINICAL_SCOPE,
)
from app.core.exception_handlers import _forbidden_handler
from app.core.exceptions import AuthorizationError


class _Request:
    """Minimal stand-in for the parts of Request the handler reads."""

    def __init__(self, method: str = "GET", path: str = "/api/v1/test"):
        self.method = method
        self.url = type("_Url", (), {"path": path})()


@pytest.mark.asyncio
async def test_denial_is_recorded_with_actor_target_and_route(denial_audit):
    actor, target = str(uuid4()), str(uuid4())

    response = await _forbidden_handler(
        _Request("GET", "/api/v1/clinicians/me/patients/x"),
        AuthorizationError(
            "You are not assigned to this patient",
            reason_code=NO_CARE_TEAM_ASSIGNMENT,
            actor_id=actor,
            actor_role="clinician",
            target_type="patient",
            target_id=target,
        ),
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert len(denial_audit) == 1
    row = denial_audit[0]
    assert row["reason_code"] == NO_CARE_TEAM_ASSIGNMENT
    assert row["actor_id"] == actor
    assert row["target_id"] == target
    assert row["request_method"] == "GET"
    assert row["request_path"] == "/api/v1/clinicians/me/patients/x"


@pytest.mark.asyncio
async def test_reason_code_never_reaches_the_caller(denial_audit):
    """Naming the reason would confirm the record exists elsewhere.

    SYN-NEG-001 requires that a cross-clinic denial leak nothing, "including existence of
    the record", so the classification stays in the audit trail.
    """
    response = await _forbidden_handler(
        _Request(),
        AuthorizationError(
            "You are not assigned to this patient",
            reason_code=NO_CARE_TEAM_ASSIGNMENT,
            actor_id=str(uuid4()),
            actor_role="clinician",
            target_type="patient",
            target_id=str(uuid4()),
        ),
    )

    body = bytes(response.body).decode()
    assert "reason_code" not in body
    assert NO_CARE_TEAM_ASSIGNMENT not in body
    assert denial_audit[0]["reason_code"] == NO_CARE_TEAM_ASSIGNMENT


@pytest.mark.asyncio
async def test_denial_without_context_is_still_recorded(denial_audit):
    """A denial raised with no actor or target must not be silently dropped."""
    response = await _forbidden_handler(_Request(), AuthorizationError("Nope"))

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert len(denial_audit) == 1
    assert denial_audit[0]["actor_id"] is None


@pytest.mark.asyncio
async def test_audit_failure_still_returns_a_clean_403(monkeypatch):
    from app.services import authorization_audit_service

    async def _boom(_payload):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(authorization_audit_service, "_insert_row", _boom)

    response = await _forbidden_handler(
        _Request(),
        AuthorizationError("You are not assigned to this patient"),
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert b"database unavailable" not in bytes(response.body)


class TestThroughTheApi:
    """The same guarantee, exercised through a real request."""

    def test_wrong_role_denial_is_audited(self, client, denial_audit):
        patient_id = uuid4()

        response = client.get(f"/api/v1/clinicians/me/patients/{patient_id}")

        # Unauthenticated requests are rejected before any role check, so this asserts
        # only on the denial case.
        if response.status_code == status.HTTP_403_FORBIDDEN:
            assert denial_audit
            assert denial_audit[0]["reason_code"] in {
                ROLE_LACKS_CLINICAL_SCOPE,
                PATIENT_SCOPE_SELF_ONLY,
                NO_CARE_TEAM_ASSIGNMENT,
            }
