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

    mock_db.rpc.return_value.execute.return_value = SimpleNamespace(
        data={"appointment": {"id": str(appointment_id), "status": "confirmed"}}
    )

    result = await service.respond_to_appointment(
        user_id=patient_id,
        role="patient",
        appointment_id=appointment_id,
        action=AppointmentResponseAction.ACCEPT,
    )

    assert result["status"] == "confirmed"
    chain.update.assert_not_called()
    assert mock_db.rpc.call_args.args[1]["p_action"] == "accept"


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

    mock_db.rpc.return_value.execute.return_value = SimpleNamespace(
        data={"appointment": {"id": str(appointment_id), "status": "declined"}}
    )

    result = await service.respond_to_appointment(
        user_id=patient_id,
        role="patient",
        appointment_id=appointment_id,
        action=AppointmentResponseAction.DECLINE,
    )

    assert result["status"] == "declined"
    chain.update.assert_not_called()
    assert mock_db.rpc.call_args.args[1]["p_action"] == "decline"


# ── respond_to_proposal: guard rails ───────────────────────────────────


@pytest.mark.asyncio
async def test_clinician_cannot_respond(service):
    with pytest.raises(AuthorizationError):
        await service.respond_to_appointment(
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
        await service.respond_to_appointment(
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
        await service.respond_to_appointment(
            user_id=patient_id,
            role="patient",
            appointment_id=appointment_id,
            action=AppointmentResponseAction.ACCEPT,
        )


# ── respond_to_appointment: Slice 2 actions (request alternative, cancel) ──


@pytest.mark.asyncio
async def test_request_alternative_from_proposed_stores_note(service, mock_db):
    patient_id = uuid4()
    appointment_id = uuid4()
    chain = _chain(
        mock_db,
        results=[
            [{"id": str(appointment_id), "patient_id": str(patient_id), "status": "proposed"}],
            [
                {
                    "id": str(appointment_id),
                    "patient_id": str(patient_id),
                    "status": "alternative_requested",
                }
            ],
        ],
    )

    mock_db.rpc.return_value.execute.return_value = SimpleNamespace(
        data={"appointment": {"id": str(appointment_id), "status": "alternative_requested"}}
    )

    result = await service.respond_to_appointment(
        user_id=patient_id,
        role="patient",
        appointment_id=appointment_id,
        action=AppointmentResponseAction.REQUEST_ALTERNATIVE,
        note="Mornings work better for me",
    )

    assert result["status"] == "alternative_requested"
    chain.update.assert_not_called()
    assert mock_db.rpc.call_args.args[1]["p_note"] == "Mornings work better for me"


@pytest.mark.asyncio
async def test_cancel_from_proposed(service, mock_db):
    patient_id = uuid4()
    appointment_id = uuid4()
    chain = _chain(
        mock_db,
        results=[
            [{"id": str(appointment_id), "patient_id": str(patient_id), "status": "proposed"}],
            [{"id": str(appointment_id), "patient_id": str(patient_id), "status": "cancelled"}],
        ],
    )

    mock_db.rpc.return_value.execute.return_value = SimpleNamespace(
        data={"appointment": {"id": str(appointment_id), "status": "cancelled"}}
    )

    result = await service.respond_to_appointment(
        user_id=patient_id,
        role="patient",
        appointment_id=appointment_id,
        action=AppointmentResponseAction.CANCEL,
    )

    assert result["status"] == "cancelled"
    chain.update.assert_not_called()
    assert mock_db.rpc.call_args.args[1]["p_action"] == "cancel"


@pytest.mark.asyncio
async def test_cancel_from_confirmed(service, mock_db):
    patient_id = uuid4()
    appointment_id = uuid4()
    _chain(
        mock_db,
        results=[
            [{"id": str(appointment_id), "patient_id": str(patient_id), "status": "confirmed"}],
            [{"id": str(appointment_id), "patient_id": str(patient_id), "status": "cancelled"}],
        ],
    )

    mock_db.rpc.return_value.execute.return_value = SimpleNamespace(
        data={"appointment": {"id": str(appointment_id), "status": "cancelled"}}
    )

    result = await service.respond_to_appointment(
        user_id=patient_id,
        role="patient",
        appointment_id=appointment_id,
        action=AppointmentResponseAction.CANCEL,
    )

    assert result["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_from_scheduled(service, mock_db):
    patient_id = uuid4()
    appointment_id = uuid4()
    _chain(
        mock_db,
        results=[
            [{"id": str(appointment_id), "patient_id": str(patient_id), "status": "scheduled"}],
            [{"id": str(appointment_id), "patient_id": str(patient_id), "status": "cancelled"}],
        ],
    )

    mock_db.rpc.return_value.execute.return_value = SimpleNamespace(
        data={"appointment": {"id": str(appointment_id), "status": "cancelled"}}
    )

    result = await service.respond_to_appointment(
        user_id=patient_id,
        role="patient",
        appointment_id=appointment_id,
        action=AppointmentResponseAction.CANCEL,
    )

    assert result["status"] == "cancelled"


@pytest.mark.asyncio
async def test_request_alternative_rejected_when_not_proposed(service, mock_db):
    patient_id = uuid4()
    appointment_id = uuid4()
    _chain(
        mock_db,
        results=[
            [{"id": str(appointment_id), "patient_id": str(patient_id), "status": "confirmed"}],
        ],
    )

    with pytest.raises(ValidationError):
        await service.respond_to_appointment(
            user_id=patient_id,
            role="patient",
            appointment_id=appointment_id,
            action=AppointmentResponseAction.REQUEST_ALTERNATIVE,
        )


@pytest.mark.asyncio
async def test_cancel_rejected_when_already_cancelled(service, mock_db):
    patient_id = uuid4()
    appointment_id = uuid4()
    _chain(
        mock_db,
        results=[
            [{"id": str(appointment_id), "patient_id": str(patient_id), "status": "cancelled"}],
        ],
    )

    with pytest.raises(ValidationError):
        await service.respond_to_appointment(
            user_id=patient_id,
            role="patient",
            appointment_id=appointment_id,
            action=AppointmentResponseAction.CANCEL,
        )


# Grouped offers use a single database transaction, not sequential row updates.
@pytest.mark.asyncio
async def test_assigned_clinician_proposes_group(service, mock_db):
    clinician_id, patient_id, team_id = uuid4(), uuid4(), uuid4()
    _chain(
        mock_db,
        results=[
            [{"id": str(team_id), "clinician_id": str(clinician_id), "patient_id": str(patient_id)}]
        ],
    )
    mock_db.rpc.return_value.execute.return_value = SimpleNamespace(
        data={"appointments": [{"id": "slot-1", "proposal_group_id": "offer-1"}]}
    )
    slots = ["2099-10-01T10:00:00+00:00", "2099-10-02T10:00:00+00:00"]
    result = await service.propose_for_user(
        user_id=clinician_id, role="clinician", data={"care_team_id": str(team_id), "slots": slots}
    )
    assert result[0]["proposal_group_id"] == "offer-1"
    assert mock_db.rpc.call_args.args[0] == "propose_appointment_slots"
    assert mock_db.rpc.call_args.args[1]["p_slots"] == slots


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["patient", "admin", "staff"])
async def test_non_clinician_cannot_propose_group(service, mock_db, role):
    with pytest.raises(AuthorizationError):
        await service.propose_for_user(user_id=uuid4(), role=role, data={})
    mock_db.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_unassigned_clinician_cannot_propose_group(service, mock_db):
    _chain(mock_db, results=[[{"clinician_id": str(uuid4())}]])
    with pytest.raises(AuthorizationError):
        await service.propose_for_user(
            user_id=uuid4(), role="clinician", data={"care_team_id": str(uuid4())}
        )
    mock_db.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_cannot_propose_past_times(service, mock_db):
    clinician = uuid4()
    _chain(mock_db, results=[[{"clinician_id": str(clinician)}]])
    with pytest.raises(ValidationError):
        await service.propose_for_user(
            user_id=clinician,
            role="clinician",
            data={"care_team_id": str(uuid4()), "slots": ["2000-01-01T00:00:00+00:00"]},
        )
    mock_db.rpc.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action",
    [
        AppointmentResponseAction.ACCEPT,
        AppointmentResponseAction.DECLINE,
        AppointmentResponseAction.REQUEST_ALTERNATIVE,
    ],
)
async def test_group_response_uses_atomic_rpc(service, mock_db, action):
    patient, appointment = uuid4(), uuid4()
    chain = _chain(
        mock_db,
        results=[
            [
                {
                    "id": str(appointment),
                    "patient_id": str(patient),
                    "status": "proposed",
                    "proposal_group_id": str(uuid4()),
                }
            ]
        ],
    )
    mock_db.rpc.return_value.execute.return_value = SimpleNamespace(
        data={"appointment": {"id": str(appointment), "status": "confirmed"}}
    )
    result = await service.respond_to_appointment(
        user_id=patient,
        role="patient",
        appointment_id=appointment,
        action=action,
        note="Afternoons",
    )
    assert result["id"] == str(appointment)
    mock_db.rpc.assert_called_once_with(
        "respond_to_appointment_offer",
        {
            "p_actor_id": str(patient),
            "p_appointment_id": str(appointment),
            "p_action": action.value,
            "p_note": "Afternoons",
        },
    )
    chain.update.assert_not_called()


@pytest.mark.asyncio
async def test_stale_group_response_is_a_safe_validation_error(service, mock_db):
    patient, appointment = uuid4(), uuid4()
    _chain(
        mock_db,
        results=[
            [
                {
                    "id": str(appointment),
                    "patient_id": str(patient),
                    "status": "proposed",
                    "proposal_group_id": str(uuid4()),
                }
            ]
        ],
    )
    mock_db.rpc.return_value.execute.return_value = SimpleNamespace(data={"error": "stale"})
    with pytest.raises(ValidationError):
        await service.respond_to_appointment(
            user_id=patient,
            role="patient",
            appointment_id=appointment,
            action=AppointmentResponseAction.ACCEPT,
        )


@pytest.mark.asyncio
async def test_generic_update_cannot_bypass_group_state_machine(service, mock_db):
    patient = uuid4()
    _chain(mock_db, results=[[{"patient_id": str(patient), "proposal_group_id": str(uuid4())}]])
    with pytest.raises(ValidationError):
        await service.update_for_user(
            user_id=patient, role="patient", appointment_id=uuid4(), data={"status": "confirmed"}
        )


@pytest.mark.asyncio
async def test_offer_database_failure_is_sanitized(service, mock_db):
    from postgrest.exceptions import APIError

    from app.core.exceptions import ExternalServiceError

    mock_db.rpc.return_value.execute.side_effect = APIError(
        {"message": "raw database detail", "code": "PGRST202", "details": None, "hint": None}
    )
    with pytest.raises(ExternalServiceError) as caught:
        await service._appointment_rpc("respond_to_appointment_offer", {})
    assert "raw database detail" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason,code",
    [
        ("conflict", "APPOINTMENT_CONFLICT"),
        ("expired", "APPOINTMENT_EXPIRED"),
        ("stale", "APPOINTMENT_UNAVAILABLE"),
        ("past", "APPOINTMENT_PAST"),
    ],
)
async def test_rpc_booking_failures_have_stable_codes(service, mock_db, reason, code):
    mock_db.rpc.return_value.execute.return_value = SimpleNamespace(data={"error": reason})
    with pytest.raises(ValidationError) as caught:
        await service._appointment_rpc("respond_to_appointment_offer", {})
    assert caught.value.code == code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sqlstate,message,code",
    [
        ("23P01", "Private conflicting row", "APPOINTMENT_CONFLICT"),
        ("40P01", "Private transaction detail", "APPOINTMENT_UNAVAILABLE"),
        ("P0001", "appointment_expired", "APPOINTMENT_EXPIRED"),
        ("P0001", "appointment_past", "APPOINTMENT_PAST"),
        ("P0001", "appointment_stale", "APPOINTMENT_UNAVAILABLE"),
    ],
)
async def test_direct_write_booking_errors_are_sanitized(service, mock_db, sqlstate, message, code):
    from postgrest.exceptions import APIError

    query = MagicMock()
    query.execute.side_effect = APIError(
        {"code": sqlstate, "message": message, "details": None, "hint": None}
    )
    with pytest.raises(ValidationError) as caught:
        await service._execute(query)
    assert caught.value.code == code
    assert "Private" not in caught.value.message


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["patient", "clinician"])
async def test_listing_persists_authorized_expiration_before_reading(service, mock_db, role):
    user = uuid4()
    chain = _chain(mock_db, results=[[]])
    mock_db.rpc.return_value.execute.return_value = SimpleNamespace(data={"expired_count": 2})
    assert await service.list_for_user(user_id=user, role=role) == []
    mock_db.rpc.assert_called_once_with(
        "expire_appointment_proposals", {"p_actor_id": str(user), "p_actor_role": role}
    )
    chain.execute.assert_called_once()


@pytest.mark.asyncio
async def test_unsupported_role_cannot_trigger_expiration(service, mock_db):
    with pytest.raises(AuthorizationError):
        await service.list_for_user(user_id=uuid4(), role="staff")
    mock_db.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_already_expired_visit_has_expiry_code(service, mock_db):
    patient = uuid4()
    _chain(mock_db, results=[[{"patient_id": str(patient), "status": "expired"}]])
    with pytest.raises(ValidationError) as caught:
        await service.respond_to_appointment(
            user_id=patient,
            role="patient",
            appointment_id=uuid4(),
            action=AppointmentResponseAction.ACCEPT,
        )
    assert caught.value.code == "APPOINTMENT_EXPIRED"
    mock_db.rpc.assert_not_called()
