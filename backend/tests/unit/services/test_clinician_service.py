"""Tests for ClinicianService."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.models.dashboard import PatientRiskData
from app.services.clinician_service import ClinicianService


def _response(*, data=None, count=None):
    return SimpleNamespace(data=data, count=count)


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def service(mock_db):
    return ClinicianService(db=mock_db)


@pytest.mark.asyncio
async def test_get_dashboard_data_filters_sorts_and_paginates(service):
    patient_ids = [uuid4(), uuid4(), uuid4()]
    service._get_assigned_patient_ids = AsyncMock(return_value=patient_ids)  # type: ignore[method-assign]
    service._get_pending_medwatch_count = AsyncMock(return_value=4)  # type: ignore[method-assign]

    risk_rows = [
        PatientRiskData(
            patient_id=patient_ids[0],
            first_name="Ana",
            last_name="West",
            risk_level="medium",
            adherence_score=0.72,
            open_adr_count=0,
            active_med_count=3,
            recent_symptom_severity=5,
            last_activity="Logged medication 1d ago",
        ),
        RuntimeError("risk lookup failed"),
        PatientRiskData(
            patient_id=patient_ids[2],
            first_name="Bea",
            last_name="Young",
            risk_level="low",
            adherence_score=0.95,
            open_adr_count=0,
            active_med_count=5,
            recent_symptom_severity=1,
            last_activity="Reported 'cough' 2h ago",
        ),
    ]

    with patch(
        "app.services.risk_score_service.RiskScoreService.get_patient_risk",
        new=AsyncMock(side_effect=risk_rows),
    ):
        result = await service.get_dashboard_data(
            uuid4(),
            sort_by="last_activity",
            sort_order="asc",
            min_med_count=2,
            max_last_activity_days=2,
            page=1,
            page_size=1,
        )

    assert result["total"] == 2
    assert result["high_risk"] == 0
    assert result["medium_risk"] == 1
    assert result["low_risk"] == 1
    assert result["medwatch_pending"] == 4
    assert len(result["patients"]) == 1
    assert result["patients"][0]["first_name"] == "Bea"


@pytest.mark.asyncio
async def test_get_patient_risk_snapshot_returns_latest_patient_card(service):
    clinician_id = uuid4()
    patient_id = uuid4()
    service.care_team_repo.find_active_assignment = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"id": str(uuid4())}]
    )

    risk_payload = PatientRiskData(
        patient_id=patient_id,
        first_name="Mina",
        last_name="Patel",
        risk_level="medium",
        adherence_score=0.7,
        open_adr_count=1,
        active_med_count=4,
        recent_symptom_severity=6,
        last_activity="Reported 'nausea' 1h ago",
    )

    with patch(
        "app.services.risk_score_service.RiskScoreService.get_patient_risk",
        new=AsyncMock(return_value=risk_payload),
    ) as get_patient_risk:
        result = await service.get_patient_risk_snapshot(clinician_id, patient_id)

    assert result["patient_id"] == patient_id
    assert result["first_name"] == "Mina"
    assert result["risk_level"] == "medium"
    get_patient_risk.assert_awaited_once_with(patient_id)


@pytest.mark.asyncio
async def test_get_patient_risk_snapshot_requires_assignment(service):
    service.care_team_repo.find_active_assignment = AsyncMock(  # type: ignore[method-assign]
        return_value=[]
    )

    with pytest.raises(AuthorizationError, match="not assigned"):
        await service.get_patient_risk_snapshot(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_set_patient_obligation_inserts_care_team_scoped_row(service, mock_db):
    clinician_id = uuid4()
    patient_id = uuid4()
    care_team_id = str(uuid4())
    created = {"id": str(uuid4()), "description": "Walk daily"}
    chain = MagicMock()
    for method in ("select", "eq", "insert"):
        getattr(chain, method).return_value = chain
    mock_db.table.return_value = chain
    service.care_team_repo.find_active_assignment = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"id": care_team_id}]
    )
    service._execute = AsyncMock(  # type: ignore[method-assign]
        return_value=_response(data=[created])
    )

    result = await service.set_patient_obligation(
        clinician_id,
        patient_id,
        {
            "obligation_type": "exercise",
            "description": "Walk daily",
            "frequency": "daily",
            "notes": "30 minutes minimum",
        },
    )

    assert result == created
    chain.insert.assert_called_once_with(
        {
            "patient_id": str(patient_id),
            "set_by_care_team_id": care_team_id,
            "obligation_type": "exercise",
            "description": "Walk daily",
            "frequency": "daily",
            "notes": "30 minutes minimum",
            "is_active": True,
        }
    )


@pytest.mark.asyncio
async def test_set_patient_obligation_requires_assignment(service):
    service.care_team_repo.find_active_assignment = AsyncMock(  # type: ignore[method-assign]
        return_value=[]
    )

    with pytest.raises(AuthorizationError, match="not assigned"):
        await service.set_patient_obligation(
            uuid4(),
            uuid4(),
            {
                "obligation_type": "diet",
                "description": "Reduce sodium",
                "frequency": "daily",
            },
        )


@pytest.mark.asyncio
async def test_get_current_invite_code_returns_latest_pending(service):
    clinician_id = uuid4()
    service.care_team_repo.list_pending_invites_for_clinician = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            {
                "id": str(uuid4()),
                "invite_code": "AB12CD34",
                "created_at": "2026-04-10T20:00:00Z",
            }
        ]
    )

    result = await service.get_current_invite_code(clinician_id)

    assert result["invite_code"] == "AB12CD34"
    assert result["care_team_id"] is not None


@pytest.mark.asyncio
async def test_get_current_invite_code_returns_null_when_missing(service):
    service.care_team_repo.list_pending_invites_for_clinician = AsyncMock(  # type: ignore[method-assign]
        return_value=[]
    )

    result = await service.get_current_invite_code(uuid4())

    assert result == {"invite_code": None, "care_team_id": None}


@pytest.mark.asyncio
async def test_list_invite_codes_returns_lifecycle_buckets(service):
    clinician_id = uuid4()
    active_id = str(uuid4())
    claimed_id = str(uuid4())
    expired_id = str(uuid4())

    service.clinician_repo.get_context_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "id": str(clinician_id),
            "clinic_id": "clinic-1",
            "clinic_name": "City Health",
            "role": "provider",
        }
    )
    service.care_team_repo.list_invites_for_clinician_ids = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            {
                "id": active_id,
                "invite_code": "ACTIVE123",
                "status": "pending",
                "patient_id": None,
                "role": "provider",
                "created_at": "2026-04-10T20:00:00Z",
                "invite_expires_at": "2099-01-01T00:00:00+00:00",
                "invite_claimed_at": None,
                "patients": None,
                "clinicians": {
                    "id": str(clinician_id),
                    "first_name": "Casey",
                    "last_name": "Jones",
                    "email": "casey@example.com",
                },
            },
            {
                "id": claimed_id,
                "invite_code": "CLAIM123",
                "status": "active",
                "patient_id": str(uuid4()),
                "role": "provider",
                "created_at": "2026-04-10T19:00:00Z",
                "invite_expires_at": "2099-01-01T00:00:00+00:00",
                "invite_claimed_at": "2026-04-10T21:00:00Z",
                "patients": {
                    "id": str(uuid4()),
                    "first_name": "John",
                    "last_name": "Doe",
                    "email": "john@example.com",
                },
                "clinicians": {
                    "id": str(clinician_id),
                    "first_name": "Casey",
                    "last_name": "Jones",
                    "email": "casey@example.com",
                },
            },
            {
                "id": expired_id,
                "invite_code": "OLD12345",
                "status": "pending",
                "patient_id": None,
                "role": "provider",
                "created_at": "2026-03-01T10:00:00Z",
                "invite_expires_at": "2000-01-01T00:00:00+00:00",
                "invite_claimed_at": None,
                "patients": None,
                "clinicians": {
                    "id": str(clinician_id),
                    "first_name": "Casey",
                    "last_name": "Jones",
                    "email": "casey@example.com",
                },
            },
        ]
    )
    service.care_team_repo.deactivate_invite = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"id": expired_id, "status": "inactive"}]
    )

    result = await service.list_invite_codes(clinician_id)

    assert result["counts"] == {"active": 1, "claimed": 1, "inactive": 1}
    by_id = {row["care_team_id"]: row for row in result["invites"]}
    assert by_id[active_id]["lifecycle_state"] == "active"
    assert by_id[claimed_id]["lifecycle_state"] == "claimed"
    assert by_id[expired_id]["lifecycle_state"] == "inactive"
    assert by_id[active_id]["created_by"]["email"] == "casey@example.com"


@pytest.mark.asyncio
async def test_list_invite_codes_uses_clinic_scope_for_admin(service):
    admin_id = uuid4()
    own_id = str(admin_id)
    peer_id = str(uuid4())
    service.clinician_repo.get_context_async = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "id": own_id,
            "clinic_id": "clinic-1",
            "clinic_name": "City Health",
            "role": "admin",
        }
    )
    service.clinician_repo.list_ids_by_clinic_id_async = AsyncMock(  # type: ignore[method-assign]
        return_value=[own_id, peer_id]
    )
    service.clinician_repo.list_ids_by_clinic_name_async = AsyncMock(  # type: ignore[method-assign]
        return_value=[peer_id]
    )
    service.care_team_repo.list_invites_for_clinician_ids = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            {
                "id": str(uuid4()),
                "invite_code": "ADMIN001",
                "status": "pending",
                "patient_id": None,
                "role": "provider",
                "created_at": "2026-04-10T20:00:00Z",
                "invite_expires_at": "2099-01-01T00:00:00+00:00",
                "invite_claimed_at": None,
                "patients": None,
                "clinicians": {
                    "id": peer_id,
                    "first_name": "Taylor",
                    "last_name": "Mills",
                    "email": "taylor@example.com",
                },
            }
        ]
    )

    result = await service.list_invite_codes(admin_id)

    service.care_team_repo.list_invites_for_clinician_ids.assert_awaited_once_with(
        sorted([own_id, peer_id])
    )
    assert result["counts"] == {"active": 1, "claimed": 0, "inactive": 0}
    assert result["invites"][0]["created_by"]["id"] == peer_id
    assert result["invites"][0]["created_by"]["email"] == "taylor@example.com"


@pytest.mark.asyncio
async def test_revoke_invite_code_sets_pending_invite_to_inactive(service):
    clinician_id = uuid4()
    invite_id = uuid4()

    service.care_team_repo.find_invite_for_creator = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "id": str(invite_id),
            "clinician_id": str(clinician_id),
            "status": "pending",
            "patient_id": None,
            "invite_code": "REVK1234",
        }
    )
    service.care_team_repo.deactivate_invite = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"id": str(invite_id), "status": "inactive"}]
    )

    result = await service.revoke_invite_code(clinician_id, invite_id)

    assert result["care_team_id"] == str(invite_id)
    assert result["status"] == "inactive"


@pytest.mark.asyncio
async def test_revoke_invite_code_rejects_claimed_or_non_pending_invite(service):
    service.care_team_repo.find_invite_for_creator = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "id": str(uuid4()),
            "status": "active",
            "patient_id": str(uuid4()),
            "invite_code": "USED1234",
        }
    )

    with pytest.raises(ValidationError, match="pending unclaimed"):
        await service.revoke_invite_code(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_revoke_invite_code_raises_not_found_for_unknown_invite(service):
    service.care_team_repo.find_invite_for_creator = AsyncMock(  # type: ignore[method-assign]
        return_value=None
    )

    with pytest.raises(NotFoundError, match="Invite code"):
        await service.revoke_invite_code(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_save_document_annotation_rejects_document_outside_patient_scope(service):
    service.care_team_repo.find_active_assignment = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"id": str(uuid4())}]
    )
    service._execute = AsyncMock(  # type: ignore[method-assign]
        return_value=_response(data=[])
    )

    with pytest.raises(NotFoundError, match="Document"):
        await service.save_document_annotation(uuid4(), uuid4(), uuid4(), "Needs follow-up")


@pytest.mark.asyncio
async def test_save_document_annotation_updates_document_for_assigned_patient(service, mock_db):
    clinician_id = uuid4()
    patient_id = uuid4()
    document_id = uuid4()
    chain = MagicMock()
    for method in ("select", "eq", "update"):
        getattr(chain, method).return_value = chain
    mock_db.table.return_value = chain
    service.care_team_repo.find_active_assignment = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"id": str(uuid4())}]
    )
    service._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _response(data=[{"id": str(document_id)}]),
            _response(data=[{"id": str(document_id)}]),
        ]
    )

    result = await service.save_document_annotation(
        clinician_id,
        patient_id,
        document_id,
        "Medication adherence improving",
    )

    assert result == {"status": "saved", "document_id": str(document_id)}
    chain.update.assert_called_once_with(
        {
            "clinician_annotation": "Medication adherence improving",
            "annotation_by": str(clinician_id),
        }
    )


@pytest.mark.asyncio
async def test_get_patient_a2a_timeline_returns_session_filtered_tasks(service, mock_db):
    clinician_id = uuid4()
    patient_id = uuid4()
    task = {
        "id": str(uuid4()),
        "patient_id": str(patient_id),
        "conversation_session_id": "session-1",
        "status": "completed",
    }
    chain = MagicMock()
    for method in ("select", "eq", "order", "limit"):
        getattr(chain, method).return_value = chain
    mock_db.table.return_value = chain

    service.get_patient_detail = AsyncMock(return_value={"id": str(patient_id)})  # type: ignore[method-assign]
    service._execute = AsyncMock(return_value=_response(data=[task]))  # type: ignore[method-assign]

    result = await service.get_patient_a2a_timeline(
        clinician_id,
        patient_id,
        session_id="session-1",
        limit=25,
    )

    assert result["patient_id"] == str(patient_id)
    assert result["session_id"] == "session-1"
    assert result["tasks"][0]["id"] == task["id"]
    chain.eq.assert_any_call("conversation_session_id", "session-1")


@pytest.mark.asyncio
async def test_get_patient_a2a_timeline_requires_assignment(service):
    service.get_patient_detail = AsyncMock(  # type: ignore[method-assign]
        side_effect=AuthorizationError("You are not assigned to this patient")
    )

    with pytest.raises(AuthorizationError, match="not assigned"):
        await service.get_patient_a2a_timeline(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_build_adherence_series_aggregates_recent_days(service):
    patient_id = uuid4()
    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)
    service._execute = AsyncMock(  # type: ignore[method-assign]
        return_value=_response(
            data=[
                {
                    "status": "completed",
                    "target_type": "medication",
                    "logged_at": f"{today.isoformat()}T08:00:00Z",
                },
                {
                    "status": "skipped",
                    "target_type": "medication",
                    "logged_at": f"{today.isoformat()}T12:00:00Z",
                },
                {
                    "status": "completed",
                    "target_type": "obligation",
                    "logged_at": f"{yesterday.isoformat()}T08:00:00Z",
                },
                {
                    "status": "completed",
                    "target_type": "obligation",
                    "logged_at": None,
                },
            ]
        )
    )

    series = await service._build_adherence_series(patient_id)

    assert len(series) == 30
    by_day = {row["date"]: row for row in series}
    assert by_day[today.isoformat()] == {
        "date": today.isoformat(),
        "score": 0.5,
        "completed": 1,
        "expected": 2,
    }
    assert by_day[yesterday.isoformat()] == {
        "date": yesterday.isoformat(),
        "score": 1.0,
        "completed": 1,
        "expected": 1,
    }


@pytest.mark.asyncio
async def test_compute_obligation_completion_rate_counts_completed_rows(service):
    service._execute = AsyncMock(  # type: ignore[method-assign]
        return_value=_response(
            data=[
                {"status": "completed"},
                {"status": "completed"},
                {"status": "skipped"},
            ]
        )
    )

    rate = await service._compute_obligation_completion_rate(uuid4())

    assert rate == pytest.approx(2 / 3)


def test_last_activity_age_days_parses_supported_units(service):
    assert service._last_activity_age_days("Logged medication 30m ago") == pytest.approx(
        30 / (60 * 24)
    )
    assert service._last_activity_age_days("Logged medication 3h ago") == pytest.approx(3 / 24)
    assert service._last_activity_age_days("Logged medication 4d ago") == 4.0
    assert service._last_activity_age_days("No recent activity") is None
