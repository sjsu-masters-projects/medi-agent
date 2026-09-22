"""Tests for AppointmentService proposal lifecycle (SCH-001, Slice 1)."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import AuthorizationError, ValidationError
from app.models.enums import AppointmentResponseAction
from app.services.appointment_service import AppointmentService


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def service(mock_db):
    return AppointmentService(db=mock_db)


def _chain(mock_db, *, results):
    """Make each successive `.execute()` return the next payload in `results`."""
    chain = MagicMock()
    chain.execute.side_effect = [SimpleNamespace(data=data) for data in results]
    for method in ("select", "eq", "order", "insert", "update", "limit", "in_"):
        getattr(chain, method).return_value = chain
    mock_db.table.return_value = chain
    return chain


# ── create_for_user: initial status depends on who creates it ──────────


@pytest.mark.asyncio
async def test_clinician_created_appointment_is_proposed(service, mock_db):
    clinician_id = uuid4()
    care_team_id = uuid4()
    patient_id = uuid4()
    chain = _chain(
        mock_db,
        results=[
            [
                {
                    "id": str(care_team_id),
                    "patient_id": str(patient_id),
                    "clinician_id": str(clinician_id),
                    "status": "active",
                }
            ],
            [{"first_name": "Elena", "last_name": "Park"}],
            [{"id": str(uuid4()), "status": "proposed"}],
        ],
    )

    await service.create_for_user(
        user_id=clinician_id,
        role="clinician",
        data={"care_team_id": str(care_team_id), "scheduled_at": "2026-05-08T17:00:00Z"},
    )

    inserted = chain.insert.call_args.args[0]
    assert inserted["status"] == "proposed"
    assert inserted["patient_id"] == str(patient_id)


@pytest.mark.asyncio
async def test_patient_created_appointment_is_scheduled(service, mock_db):
    patient_id = uuid4()
    care_team_id = uuid4()
    clinician_id = uuid4()
    chain = _chain(
        mock_db,
        results=[
            [
                {
                    "id": str(care_team_id),
                    "patient_id": str(patient_id),
                    "clinician_id": str(clinician_id),
                    "status": "active",
                }
            ],
            [{"first_name": "Elena", "last_name": "Park"}],
            [{"id": str(uuid4()), "status": "scheduled"}],
        ],
    )

    await service.create_for_user(
        user_id=patient_id,
        role="patient",
        data={"care_team_id": str(care_team_id), "scheduled_at": "2026-05-08T17:00:00Z"},
    )

    assert chain.insert.call_args.args[0]["status"] == "scheduled"


# ── respond_to_proposal: accept / decline transitions ──────────────────


@pytest.mark.asyncio
async def test_accept_confirms_proposed_appointment(service, mock_db):
    patient_id = uuid4()
    appointment_id = uuid4()
    chain = _chain(
        mock_db,
        results=[
            [{"id": str(appointment_id), "patient_id": str(patient_id), "status": "proposed"}],
            [{"id": str(appointment_id), "patient_id": str(patient_id), "status": "confirmed"}],
        ],
    )

    result = await service.respond_to_proposal(
        user_id=patient_id,
        role="patient",
        appointment_id=appointment_id,
        action=AppointmentResponseAction.ACCEPT,
    )

    assert result["status"] == "confirmed"
    chain.update.assert_called_once_with({"status": "confirmed"})


@pytest.mark.asyncio
async def test_decline_marks_appointment_declined(service, mock_db):
    patient_id = uuid4()
    appointment_id = uuid4()
    chain = _chain(
        mock_db,
        results=[
            [{"id": str(appointment_id), "patient_id": str(patient_id), "status": "proposed"}],
            [{"id": str(appointment_id), "patient_id": str(patient_id), "status": "declined"}],
        ],
    )

    result = await service.respond_to_proposal(
        user_id=patient_id,
        role="patient",
        appointment_id=appointment_id,
        action=AppointmentResponseAction.DECLINE,
    )

    assert result["status"] == "declined"
    chain.update.assert_called_once_with({"status": "declined"})


# ── respond_to_proposal: guard rails ───────────────────────────────────


@pytest.mark.asyncio
async def test_clinician_cannot_respond(service):
    with pytest.raises(AuthorizationError):
        await service.respond_to_proposal(
            user_id=uuid4(),
            role="clinician",
            appointment_id=uuid4(),
            action=AppointmentResponseAction.ACCEPT,
        )


@pytest.mark.asyncio
async def test_patient_cannot_respond_to_another_patients_appointment(service, mock_db):
    appointment_id = uuid4()
    _chain(
        mock_db,
        results=[
            [{"id": str(appointment_id), "patient_id": str(uuid4()), "status": "proposed"}],
        ],
    )

    with pytest.raises(AuthorizationError):
        await service.respond_to_proposal(
            user_id=uuid4(),
            role="patient",
            appointment_id=appointment_id,
            action=AppointmentResponseAction.ACCEPT,
        )


@pytest.mark.asyncio
async def test_cannot_respond_to_non_proposed_appointment(service, mock_db):
    patient_id = uuid4()
    appointment_id = uuid4()
    _chain(
        mock_db,
        results=[
            [{"id": str(appointment_id), "patient_id": str(patient_id), "status": "confirmed"}],
        ],
    )

    with pytest.raises(ValidationError):
        await service.respond_to_proposal(
            user_id=patient_id,
            role="patient",
            appointment_id=appointment_id,
            action=AppointmentResponseAction.ACCEPT,
        )
