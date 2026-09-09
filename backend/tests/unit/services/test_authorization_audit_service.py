"""Unit tests for denial auditing.

Two properties matter more than the happy path: the record survives malformed input, and
a broken audit never changes the 403 the caller already earned.
"""

import asyncio
from typing import Any
from uuid import uuid4

import pytest

from app.core.authorization_reasons import (
    NO_CARE_TEAM_ASSIGNMENT,
    NO_CARE_TEAM_ASSIGNMENT_CROSS_CLINIC,
    PATIENT_SCOPE_SELF_ONLY,
    UNSPECIFIED,
)
from app.services import authorization_audit_service
from app.services.authorization_audit_service import record_denial


@pytest.fixture
def written(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    async def _capture(payload: dict[str, Any]) -> None:
        rows.append(dict(payload))

    monkeypatch.setattr(authorization_audit_service, "_insert_row", _capture)
    return rows


@pytest.fixture(autouse=True)
def no_refine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refinement is covered by the classifier's own tests; keep it out of these."""

    async def _identity(reason_code: str, *_args: Any) -> str:
        return reason_code

    monkeypatch.setattr(authorization_audit_service, "_refine", _identity)


@pytest.mark.asyncio
async def test_records_the_denial_with_its_context(written):
    actor, target = str(uuid4()), str(uuid4())

    assert await record_denial(
        reason_code=PATIENT_SCOPE_SELF_ONLY,
        actor_id=actor,
        actor_role="patient",
        target_type="patient",
        target_id=target,
        request_method="GET",
        request_path="/api/v1/clinicians/me/patients/x",
    )

    assert written == [
        {
            "reason_code": PATIENT_SCOPE_SELF_ONLY,
            "actor_id": actor,
            "actor_role": "patient",
            "target_type": "patient",
            "target_id": target,
            "request_method": "GET",
            "request_path": "/api/v1/clinicians/me/patients/x",
        }
    ]


@pytest.mark.asyncio
async def test_malformed_identifiers_are_dropped_not_lost(written):
    """A probe against a junk id is precisely the event worth keeping."""
    assert await record_denial(
        reason_code=NO_CARE_TEAM_ASSIGNMENT,
        actor_id="not-a-uuid",
        target_type="patient",
        target_id="../../etc/passwd",
    )

    row = written[0]
    assert row["actor_id"] is None
    assert row["target_id"] is None
    assert row["reason_code"] == NO_CARE_TEAM_ASSIGNMENT


@pytest.mark.asyncio
async def test_overlong_request_path_is_truncated_to_the_column_width(written):
    assert await record_denial(reason_code=UNSPECIFIED, request_path="/x" * 5000)

    assert len(written[0]["request_path"]) == 2000


@pytest.mark.asyncio
async def test_defaults_to_unspecified_rather_than_writing_nothing(written):
    assert await record_denial()

    assert written[0]["reason_code"] == UNSPECIFIED


@pytest.mark.asyncio
async def test_insert_failure_is_swallowed(monkeypatch):
    async def _boom(_payload: dict[str, Any]) -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(authorization_audit_service, "_insert_row", _boom)

    # Returns False rather than raising: the caller is already returning 403, and an
    # audit outage must not turn a correct denial into a 500.
    assert await record_denial(reason_code=NO_CARE_TEAM_ASSIGNMENT) is False


@pytest.mark.asyncio
async def test_slow_insert_is_abandoned_rather_than_holding_the_response(monkeypatch):
    async def _hang(_payload: dict[str, Any]) -> None:
        await asyncio.sleep(60)

    monkeypatch.setattr(authorization_audit_service, "_insert_row", _hang)
    monkeypatch.setattr(authorization_audit_service, "_AUDIT_TIMEOUT_SECONDS", 0.05)

    assert await record_denial(reason_code=NO_CARE_TEAM_ASSIGNMENT) is False


@pytest.mark.asyncio
async def test_refinement_result_is_what_gets_written(written, monkeypatch):
    async def _to_cross_clinic(*_args: Any) -> str:
        return NO_CARE_TEAM_ASSIGNMENT_CROSS_CLINIC

    monkeypatch.setattr(authorization_audit_service, "_refine", _to_cross_clinic)

    await record_denial(
        reason_code=NO_CARE_TEAM_ASSIGNMENT,
        actor_id=str(uuid4()),
        target_type="patient",
        target_id=str(uuid4()),
    )

    assert written[0]["reason_code"] == NO_CARE_TEAM_ASSIGNMENT_CROSS_CLINIC
