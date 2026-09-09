"""Unit tests for care-team denial classification.

The reason code is the whole value of a denial record — "someone reached across clinics"
and "someone is not on this patient's team" call for different responses — so each branch
is pinned here against a fake client.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.authorization_reasons import (
    ASSIGNMENT_EXISTS_FOR_DIFFERENT_PATIENT_ONLY,
    NO_CARE_TEAM_ASSIGNMENT,
    NO_CARE_TEAM_ASSIGNMENT_CROSS_CLINIC,
    SAME_CLINIC_BUT_NO_CARE_TEAM_ASSIGNMENT,
)
from app.services.authorization_denial_classifier import classify_care_team_denial

CLINIC_A = str(uuid4())
CLINIC_B = str(uuid4())


def _db(*, actor_clinic, patient_clinics, actor_has_other_assignment):
    """Fake client answering the classifier's three reads in the order it makes them."""
    db = MagicMock()
    table = MagicMock()
    db.table.return_value = table
    for method in ("select", "eq", "limit"):
        getattr(table, method).return_value = table

    actor_rows = [{"clinic_id": actor_clinic}] if actor_clinic else []
    patient_rows = [{"clinicians": {"clinic_id": c}} for c in patient_clinics]
    assignment_rows = [{"id": str(uuid4())}] if actor_has_other_assignment else []

    table.execute.side_effect = [
        SimpleNamespace(data=actor_rows),
        SimpleNamespace(data=patient_rows),
        SimpleNamespace(data=assignment_rows),
    ]
    return db


@pytest.mark.asyncio
async def test_cross_clinic_actor_is_flagged_as_cross_clinic():
    db = _db(
        actor_clinic=CLINIC_B,
        patient_clinics=[CLINIC_A],
        actor_has_other_assignment=True,
    )

    reason = await classify_care_team_denial(db, str(uuid4()), str(uuid4()))

    # Cross-clinic outranks "has assignments elsewhere": reaching into another clinic is
    # the stronger signal, and both are true here.
    assert reason == NO_CARE_TEAM_ASSIGNMENT_CROSS_CLINIC


@pytest.mark.asyncio
async def test_same_clinic_actor_holding_other_assignments():
    db = _db(
        actor_clinic=CLINIC_A,
        patient_clinics=[CLINIC_A],
        actor_has_other_assignment=True,
    )

    reason = await classify_care_team_denial(db, str(uuid4()), str(uuid4()))

    assert reason == ASSIGNMENT_EXISTS_FOR_DIFFERENT_PATIENT_ONLY


@pytest.mark.asyncio
async def test_same_clinic_actor_with_no_assignments_at_all():
    db = _db(
        actor_clinic=CLINIC_A,
        patient_clinics=[CLINIC_A],
        actor_has_other_assignment=False,
    )

    reason = await classify_care_team_denial(db, str(uuid4()), str(uuid4()))

    assert reason == SAME_CLINIC_BUT_NO_CARE_TEAM_ASSIGNMENT


@pytest.mark.asyncio
async def test_patient_with_no_active_care_team_stays_generic():
    db = _db(actor_clinic=CLINIC_A, patient_clinics=[], actor_has_other_assignment=False)

    reason = await classify_care_team_denial(db, str(uuid4()), str(uuid4()))

    # Nothing to compare against, so no clinic claim is made.
    assert reason == NO_CARE_TEAM_ASSIGNMENT


@pytest.mark.asyncio
async def test_database_failure_degrades_to_generic_reason():
    db = MagicMock()
    db.table.side_effect = RuntimeError("database unavailable")

    reason = await classify_care_team_denial(db, str(uuid4()), str(uuid4()))

    # A coarse record beats losing the event.
    assert reason == NO_CARE_TEAM_ASSIGNMENT
