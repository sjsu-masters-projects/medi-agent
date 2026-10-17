"""Tests for ClinicianService."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.models.adr import ADRReviewAction, ADRReviewDecisionRequest
from app.models.clinic_membership import ClinicMembership
from app.models.dashboard import PatientRiskData
from app.models.enums import ClinicianRole, ClinicMembershipStatus, DocumentReviewStatus
from app.pharmacovigilance import NaranjoQuestion
from app.services.clinic_link_scope import ClinicLinkScope
from app.services.clinician_service import ClinicianService


def _response(*, data=None, count=None):
    return SimpleNamespace(data=data, count=count)


CLINIC_ID = "00000000-0000-0000-0000-0000000000c1"


def _membership(clinician_id, role="provider"):
    return ClinicMembership(
        clinician_id=clinician_id,
        clinic_id=CLINIC_ID,
        role=ClinicianRole(role),
        status=ClinicMembershipStatus.ACTIVE,
    )


def _as_member(service, clinician_id=None, role="provider"):
    """Give the service an active membership for the clinician."""
    membership = _membership(clinician_id or uuid4(), role)
    service.memberships.acting_membership = AsyncMock(return_value=membership)
    service.memberships.active_memberships = AsyncMock(return_value=[membership])


def _link_scope(service, patient_ids, clinic_id=CLINIC_ID, clinic_name="Synthetic clinic"):
    """Give the service active links to these patients, all at one clinic."""
    service.memberships.link_scope = AsyncMock(
        return_value=ClinicLinkScope({str(pid): (clinic_id, clinic_name) for pid in patient_ids})
    )


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def service(mock_db):
    return ClinicianService(db=mock_db)


@pytest.mark.asyncio
async def test_get_dashboard_data_filters_sorts_and_paginates(service):
    patient_ids = [uuid4(), uuid4(), uuid4()]
    _link_scope(service, patient_ids)
    service._get_pending_adr_review_count = AsyncMock(return_value=4)  # type: ignore[method-assign]
    service._get_pending_medwatch_count = AsyncMock(return_value=1)  # type: ignore[method-assign]

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
    assert result["pending_adr_reviews"] == 4
    assert result["medwatch_pending"] == 1
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
async def test_cross_clinic_patient_detail_is_denied_before_patient_query(service, mock_db):
    """A clinician cannot read a patient assigned only to another clinic's clinician."""
    requesting_clinician_id = uuid4()
    other_clinic_clinician_id = uuid4()
    other_clinic_patient_id = uuid4()

    async def find_assignment(clinician_id: str, patient_id: str):
        assert clinician_id == str(requesting_clinician_id)
        assert patient_id == str(other_clinic_patient_id)
        # The foreign clinic has an active assignment, but not for this clinician.
        assert clinician_id != str(other_clinic_clinician_id)
        return []

    service.care_team_repo.find_active_assignment = find_assignment  # type: ignore[method-assign]

    with pytest.raises(AuthorizationError, match="not assigned"):
        await service.get_patient_detail(requesting_clinician_id, other_clinic_patient_id)

    mock_db.table.assert_not_called()


@pytest.mark.asyncio
async def test_pending_adr_review_count_queries_only_valid_draft_status(service, mock_db):
    chain = MagicMock()
    for method in ("select", "in_"):
        getattr(chain, method).return_value = chain
    mock_db.table.return_value = chain
    service._execute = AsyncMock(return_value=_response(count=2))  # type: ignore[method-assign]

    count = await service._get_pending_adr_review_count([uuid4()])

    assert count == 2
    mock_db.table.assert_called_once_with("adr_assessments")
    chain.in_.assert_any_call("status", ["draft"])


@pytest.mark.asyncio
async def test_pending_medwatch_count_queries_medwatch_drafts(service, mock_db):
    chain = MagicMock()
    for method in ("select", "in_", "is_"):
        getattr(chain, method).return_value = chain
    mock_db.table.return_value = chain
    service._execute = AsyncMock(return_value=_response(count=1))  # type: ignore[method-assign]

    count = await service._get_pending_medwatch_count([uuid4()])

    assert count == 1
    mock_db.table.assert_called_once_with("medwatch_drafts")
    chain.in_.assert_any_call("status", ["draft"])
    chain.is_.assert_called_once_with("discarded_at", "null")


@pytest.mark.asyncio
async def test_list_adr_review_queue_returns_patient_grounded_evidence(service, mock_db):
    patient_id = uuid4()
    assessment_id = uuid4()
    symptom_report_id = uuid4()
    medication_id = uuid4()
    _link_scope(service, [patient_id])
    chain = MagicMock()
    for method in ("select", "in_", "eq", "order", "limit"):
        getattr(chain, method).return_value = chain
    mock_db.table.return_value = chain
    service._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _response(
                data=[
                    {
                        "id": str(assessment_id),
                        "patient_id": str(patient_id),
                        "symptom_report_id": str(symptom_report_id),
                        "suspect_medication_id": str(medication_id),
                        "suspect_medication_name": "lisinopril",
                        "naranjo_score": 3,
                        "causality": "Possible",
                        "naranjo_answers": {"event_after_drug": "yes"},
                        "naranjo_assessment": {"missing_questions": ["alternative_causes"]},
                        "evidence": [
                            {
                                "question": "event_after_drug",
                                "answer": "yes",
                                "evidence": "Cough began after the first dose.",
                            }
                        ],
                        "status": "draft",
                        "created_at": "2026-10-02T10:00:00Z",
                        "patients": {"first_name": "Maya", "last_name": "Patel"},
                        "symptom_reports": {
                            "symptom": "dry cough",
                            "severity": 2,
                            "onset": "after first dose",
                            "created_at": "2026-10-02T09:59:00Z",
                        },
                    }
                ]
            ),
            _response(
                data=[
                    {
                        "id": str(uuid4()),
                        "adr_assessment_id": str(assessment_id),
                        "status": "answered",
                        "responses": [
                            {
                                "question": "dose_response",
                                "answer": "yes",
                                "evidence": "It improved after my clinician lowered the dose.",
                            }
                        ],
                        "responded_at": "2026-10-03T10:00:00Z",
                        "created_at": "2026-10-02T11:00:00Z",
                    }
                ]
            ),
        ]
    )

    result = await service.list_adr_review_queue(uuid4())

    assert result["total"] == 1
    assert result["items"][0]["patient_first_name"] == "Maya"
    assert result["items"][0]["symptom"] == "dry cough"
    assert result["items"][0]["information_request_status"] == "answered"
    assert result["items"][0]["patient_responses"][0]["question"] == "dose_response"
    assert "patients" not in result["items"][0]
    assert mock_db.table.call_args_list == [
        call("adr_assessments"),
        call("adr_information_requests"),
    ]
    chain.in_.assert_has_calls(
        [
            call("patient_id", [str(patient_id)]),
            call("adr_assessment_id", [str(assessment_id)]),
        ]
    )
    chain.eq.assert_called_once_with("status", "draft")


@pytest.mark.asyncio
async def test_list_adr_review_queue_returns_empty_without_assignments(service, mock_db):
    _link_scope(service, [])

    result = await service.list_adr_review_queue(uuid4())

    assert result == {"items": [], "total": 0}
    mock_db.table.assert_not_called()


@pytest.mark.asyncio
async def test_review_adr_assessment_calls_atomic_assignment_scoped_rpc(service, mock_db):
    clinician_id = uuid4()
    patient_id = uuid4()
    assessment_id = uuid4()
    service._assert_patient_assignment = AsyncMock()  # type: ignore[method-assign]
    service._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _response(
                data={
                    "id": str(assessment_id),
                    "patient_id": str(patient_id),
                    "status": "draft",
                    "naranjo_assessment": {"missing_questions": ["dose_response"]},
                }
            ),
            _response(
                data=[
                    {
                        "id": str(assessment_id),
                        "patient_id": str(patient_id),
                        "status": "reviewed",
                        "last_review_action": "mark_reviewed",
                    }
                ]
            ),
        ]
    )

    result = await service.review_adr_assessment(
        clinician_id,
        assessment_id,
        ADRReviewDecisionRequest(action=ADRReviewAction.MARK_REVIEWED, note="Reviewed evidence"),
    )

    assert result["status"] == "reviewed"
    service._assert_patient_assignment.assert_awaited_once_with(clinician_id, patient_id)
    mock_db.rpc.assert_called_once_with(
        "review_adr_assessment",
        {
            "p_assessment_id": str(assessment_id),
            "p_actor_id": str(clinician_id),
            "p_action": "mark_reviewed",
            "p_note": "Reviewed evidence",
            "p_requested_information": [],
        },
    )


@pytest.mark.asyncio
async def test_review_adr_assessment_rejects_a_completed_review(service, mock_db):
    assessment_id = uuid4()
    patient_id = uuid4()
    service._assert_patient_assignment = AsyncMock()  # type: ignore[method-assign]
    service._execute = AsyncMock(  # type: ignore[method-assign]
        return_value=_response(
            data={
                "id": str(assessment_id),
                "patient_id": str(patient_id),
                "status": "dismissed",
            }
        )
    )

    with pytest.raises(ValidationError, match="already been completed"):
        await service.review_adr_assessment(
            uuid4(),
            assessment_id,
            ADRReviewDecisionRequest(action=ADRReviewAction.MARK_REVIEWED),
        )

    mock_db.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_review_adr_assessment_denies_an_unassigned_clinician(service, mock_db):
    clinician_id = uuid4()
    patient_id = uuid4()
    assessment_id = uuid4()
    service._assert_patient_assignment = AsyncMock(  # type: ignore[method-assign]
        side_effect=AuthorizationError("You are not assigned to this patient")
    )
    service._execute = AsyncMock(  # type: ignore[method-assign]
        return_value=_response(
            data={
                "id": str(assessment_id),
                "patient_id": str(patient_id),
                "status": "draft",
            }
        )
    )

    with pytest.raises(AuthorizationError, match="not assigned"):
        await service.review_adr_assessment(
            clinician_id,
            assessment_id,
            ADRReviewDecisionRequest(action=ADRReviewAction.MARK_REVIEWED),
        )

    mock_db.rpc.assert_not_called()


def test_request_information_requires_a_note() -> None:
    with pytest.raises(ValueError, match="review note is required"):
        ADRReviewDecisionRequest(
            action=ADRReviewAction.REQUEST_INFORMATION,
            requested_information=[NaranjoQuestion.DOSE_RESPONSE],
        )


@pytest.mark.asyncio
async def test_request_information_accepts_only_missing_patient_question(service, mock_db):
    clinician_id = uuid4()
    patient_id = uuid4()
    assessment_id = uuid4()
    service._assert_patient_assignment = AsyncMock()  # type: ignore[method-assign]
    service._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _response(
                data={
                    "id": str(assessment_id),
                    "patient_id": str(patient_id),
                    "status": "draft",
                    "naranjo_assessment": {"missing_questions": ["dose_response"]},
                }
            ),
            _response(
                data=[
                    {
                        "id": str(assessment_id),
                        "patient_id": str(patient_id),
                        "status": "draft",
                    }
                ]
            ),
        ]
    )

    await service.review_adr_assessment(
        clinician_id,
        assessment_id,
        ADRReviewDecisionRequest(
            action=ADRReviewAction.REQUEST_INFORMATION,
            note="Describe what happened after the prior dose change.",
            requested_information=[NaranjoQuestion.DOSE_RESPONSE],
        ),
    )

    mock_db.rpc.assert_called_once_with(
        "review_adr_assessment",
        {
            "p_assessment_id": str(assessment_id),
            "p_actor_id": str(clinician_id),
            "p_action": "request_information",
            "p_note": "Describe what happened after the prior dose change.",
            "p_requested_information": ["dose_response"],
        },
    )


@pytest.mark.asyncio
async def test_set_patient_obligation_stages_care_plan_draft(service, mock_db, monkeypatch):
    clinician_id = uuid4()
    patient_id = uuid4()
    created = {"id": str(uuid4()), "status": "draft"}

    class FakeCarePlanService:
        def __init__(self, db):
            assert db is mock_db

        def add_clinician_authored_obligation(self, *args):
            assert args[0] == clinician_id
            assert args[1] == patient_id
            return created

    from app.services import care_plan_service

    monkeypatch.setattr(care_plan_service, "CarePlanService", FakeCarePlanService)

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
    mock_db.table.assert_not_called()


@pytest.mark.asyncio
async def test_set_patient_obligation_propagates_care_plan_assignment_denial(service, monkeypatch):
    clinician_id = uuid4()
    patient_id = uuid4()

    class FakeCarePlanService:
        def __init__(self, _db):
            pass

        def add_clinician_authored_obligation(self, *_args):
            raise AuthorizationError("You are not assigned to this patient")

    from app.services import care_plan_service

    monkeypatch.setattr(care_plan_service, "CarePlanService", FakeCarePlanService)

    with pytest.raises(AuthorizationError, match="not assigned"):
        await service.set_patient_obligation(
            clinician_id,
            patient_id,
            {
                "obligation_type": "diet",
                "description": "Reduce sodium",
                "frequency": "daily",
            },
        )


@pytest.mark.asyncio
async def test_get_current_invite_code_returns_latest_pending(service):
    _as_member(service)
    clinician_id = uuid4()
    service.care_team_repo.list_pending_invites_for_clinician = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            {
                "id": str(uuid4()),
                "clinic_id": CLINIC_ID,
                "invite_code": "AB12CD34",
                "created_at": "2026-04-10T20:00:00Z",
            },
            {
                "id": str(uuid4()),
                "clinic_id": "00000000-0000-0000-0000-0000000000c2",
                "invite_code": "OTHERCLN",
                "created_at": "2026-04-11T20:00:00Z",
            },
        ]
    )

    result = await service.get_current_invite_code(clinician_id)

    assert result["invite_code"] == "AB12CD34"
    assert result["care_team_id"] is not None


@pytest.mark.asyncio
async def test_get_current_invite_code_returns_null_when_missing(service):
    _as_member(service)
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
    service.memberships.acting_membership = AsyncMock(  # type: ignore[method-assign]
        return_value=_membership(clinician_id)
    )
    service.care_team_repo.list_invites_for_clinician_ids = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            {
                "id": active_id,
                "clinic_id": CLINIC_ID,
                "clinician_id": str(clinician_id),
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
                "clinic_id": CLINIC_ID,
                "clinician_id": str(clinician_id),
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
                "clinic_id": CLINIC_ID,
                "clinician_id": str(clinician_id),
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
    service.memberships.acting_membership = AsyncMock(  # type: ignore[method-assign]
        return_value=_membership(admin_id, "admin")
    )
    service.memberships.clinic_member_ids = AsyncMock(  # type: ignore[method-assign]
        return_value=[own_id, peer_id]
    )
    service.care_team_repo.list_invites_for_clinician_ids = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            {
                "id": str(uuid4()),
                "clinic_id": CLINIC_ID,
                "clinician_id": peer_id,
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
    service.memberships.clinic_member_ids.assert_awaited_once()
    assert str(service.memberships.clinic_member_ids.await_args.args[0]) == CLINIC_ID


@pytest.mark.asyncio
async def test_invite_scope_uses_the_membership_role_over_the_legacy_row(service):
    clinician_id = uuid4()
    service.clinician_repo.get_context_async = AsyncMock(  # type: ignore[method-assign]
        return_value={"clinic_id": CLINIC_ID, "clinic_name": "City Health", "role": "admin"}
    )
    service.memberships.clinic_member_ids = AsyncMock()  # type: ignore[method-assign]

    ids, admin_clinics = await service._get_invite_scope(_membership(clinician_id, "provider"))

    assert ids == [str(clinician_id)]
    assert admin_clinics == set()
    service.memberships.clinic_member_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_invite_scope_has_no_name_or_legacy_fallback(service):
    """Without an active membership nothing is listed, even for a legacy admin row."""
    admin_id = uuid4()
    service.memberships.active_memberships = AsyncMock(return_value=[])  # type: ignore[method-assign]
    service.care_team_repo.list_invites_for_clinician_ids = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(AuthorizationError) as raised:
        await service.list_invite_codes(admin_id)

    assert raised.value.reason_code == "CLINIC_MEMBERSHIP_REQUIRED"
    service.care_team_repo.list_invites_for_clinician_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_invite_codes_of_another_clinic_with_the_same_name_are_not_listed(service):
    admin_id = uuid4()
    peer_id = str(uuid4())
    other_clinic = "00000000-0000-0000-0000-0000000000c2"
    service.memberships.acting_membership = AsyncMock(  # type: ignore[method-assign]
        return_value=_membership(admin_id, "admin")
    )
    service.memberships.clinic_member_ids = AsyncMock(  # type: ignore[method-assign]
        return_value=[str(admin_id), peer_id]
    )
    service.care_team_repo.list_invites_for_clinician_ids = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            {
                "id": str(uuid4()),
                "clinic_id": other_clinic,
                "clinician_id": peer_id,
                "invite_code": "OTHERCLN",
                "status": "pending",
                "invite_expires_at": "2099-01-01T00:00:00+00:00",
                "clinicians": {"id": peer_id},
            }
        ]
    )

    result = await service.list_invite_codes(admin_id, UUID(CLINIC_ID))

    assert result["invites"] == []


@pytest.mark.asyncio
async def test_a_provider_sees_only_their_own_codes_at_the_clinic(service):
    provider_id = uuid4()
    peer_id = str(uuid4())
    service.memberships.acting_membership = AsyncMock(  # type: ignore[method-assign]
        return_value=_membership(provider_id, "provider")
    )
    service.care_team_repo.list_invites_for_clinician_ids = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            {
                "id": str(uuid4()),
                "clinic_id": CLINIC_ID,
                "clinician_id": peer_id,
                "invite_code": "PEERCODE",
                "status": "pending",
                "invite_expires_at": "2099-01-01T00:00:00+00:00",
                "clinicians": {"id": peer_id},
            }
        ]
    )

    result = await service.list_invite_codes(provider_id)

    assert result["invites"] == []


@pytest.mark.asyncio
async def test_invite_codes_need_a_clinic_when_there_are_several(service):
    clinician_id = uuid4()
    service.memberships.active_memberships = AsyncMock(  # type: ignore[method-assign]
        return_value=[_membership(clinician_id), _membership(clinician_id)]
    )
    service.memberships.active_memberships.return_value[1] = ClinicMembership(
        clinician_id=clinician_id,
        clinic_id="00000000-0000-0000-0000-0000000000c2",
        role=ClinicianRole("admin"),
        status=ClinicMembershipStatus.ACTIVE,
    )

    with pytest.raises(ValidationError) as raised:
        await service.generate_invite_code(clinician_id)

    assert raised.value.code == "CLINIC_REQUIRED"


@pytest.mark.asyncio
async def test_invite_code_for_a_clinic_without_membership_is_refused(service, mock_db):
    clinician_id = uuid4()
    service.memberships.active_memberships = AsyncMock(  # type: ignore[method-assign]
        return_value=[_membership(clinician_id, "admin")]
    )

    with pytest.raises(AuthorizationError):
        await service.generate_invite_code(
            clinician_id, UUID("00000000-0000-0000-0000-0000000000c9")
        )

    mock_db.table.assert_not_called()


@pytest.mark.asyncio
async def test_generate_invite_code_records_the_issuing_clinic(service, mock_db):
    clinician_id = uuid4()
    service.memberships.acting_membership = AsyncMock(  # type: ignore[method-assign]
        return_value=_membership(clinician_id)
    )
    mock_db.table.return_value.insert.return_value.execute.return_value = _response(
        data=[{"id": "team-1"}]
    )

    result = await service.generate_invite_code(clinician_id)

    payload = mock_db.table.return_value.insert.call_args.args[0]
    mock_db.table.assert_called_with("care_teams")
    assert payload["clinic_id"] == CLINIC_ID
    assert payload["clinician_id"] == str(clinician_id)
    assert payload["status"] == "pending"
    assert result == {"invite_code": payload["invite_code"], "care_team_id": "team-1"}


@pytest.mark.asyncio
async def test_generate_invite_code_without_a_membership_fails_closed(service, mock_db):
    service.memberships.active_memberships = AsyncMock(return_value=[])  # type: ignore[method-assign]

    with pytest.raises(AuthorizationError):
        await service.generate_invite_code(uuid4())

    mock_db.table.assert_not_called()


@pytest.mark.asyncio
async def test_generate_invite_code_needs_a_clinic_choice_with_several(service, mock_db):
    service.memberships.acting_membership = AsyncMock(  # type: ignore[method-assign]
        side_effect=ValidationError("Choose the clinic for this action")
    )

    with pytest.raises(ValidationError):
        await service.generate_invite_code(uuid4())

    mock_db.table.return_value.insert.assert_not_called()


@pytest.mark.asyncio
async def test_revoke_invite_code_sets_pending_invite_to_inactive(service):
    _as_member(service)
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
    _as_member(service)
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
    _as_member(service)
    service.care_team_repo.find_invite_for_creator = AsyncMock(  # type: ignore[method-assign]
        return_value=None
    )

    with pytest.raises(NotFoundError, match="Invite code"):
        await service.revoke_invite_code(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_save_document_annotation_rejects_document_outside_patient_scope(service):
    service.document_workflows.save_document_annotation = AsyncMock(  # type: ignore[method-assign]
        side_effect=NotFoundError("Document", str(uuid4()))
    )

    with pytest.raises(NotFoundError, match="Document"):
        await service.save_document_annotation(uuid4(), uuid4(), uuid4(), "Needs follow-up")


@pytest.mark.asyncio
async def test_save_document_annotation_updates_document_for_assigned_patient(service, mock_db):
    clinician_id = uuid4()
    patient_id = uuid4()
    document_id = uuid4()
    service.document_workflows.save_document_annotation = AsyncMock(  # type: ignore[method-assign]
        return_value={"status": "saved", "document_id": str(document_id)}
    )

    result = await service.save_document_annotation(
        clinician_id,
        patient_id,
        document_id,
        "Medication adherence improving",
    )

    assert result == {"status": "saved", "document_id": str(document_id)}
    service.document_workflows.save_document_annotation.assert_awaited_once_with(
        clinician_id,
        patient_id,
        document_id,
        "Medication adherence improving",
    )


@pytest.mark.asyncio
async def test_get_patient_deep_dive_includes_review_metadata(service):
    clinician_id = uuid4()
    patient_id = uuid4()
    reviewer_id = uuid4()
    service.care_team_repo.find_active_assignment = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"id": str(uuid4())}]
    )
    service._build_adherence_series = AsyncMock(return_value=[])  # type: ignore[method-assign]
    service._compute_obligation_completion_rate = AsyncMock(  # type: ignore[method-assign]
        return_value=0.5
    )
    service._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _response(
                data={
                    "id": str(patient_id),
                    "first_name": "Asha",
                    "last_name": "Lane",
                    "email": "asha@example.com",
                    "date_of_birth": "1995-01-01",
                    "avatar_url": None,
                }
            ),
            _response(data=[]),
            _response(data=[]),
            _response(data=[]),
            _response(data=[]),
            _response(data=[]),
            _response(data=[]),
            _response(data=[]),
            _response(data=[]),
            _response(data=[]),
        ]
    )
    service.document_workflows.fetch_patient_documents = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            {
                "id": str(uuid4()),
                "file_name": "lab.pdf",
                "document_type": "lab_report",
                "parse_status": "completed",
                "ai_summary": "Summary",
                "created_at": "2026-04-20T10:00:00Z",
                "uploaded_by_role": "patient",
                "clinician_annotation": "Review soon",
                "review_status": "approved",
                "reviewed_by": str(reviewer_id),
                "reviewed_at": "2026-04-21T09:00:00Z",
                "review_note": "Looks valid",
                "reviewer": {
                    "id": str(reviewer_id),
                    "first_name": "Mina",
                    "last_name": "Shah",
                },
            }
        ]
    )

    with patch(
        "app.services.risk_score_service.RiskScoreService.get_patient_risk",
        new=AsyncMock(
            return_value=PatientRiskData(
                patient_id=patient_id,
                first_name="Asha",
                last_name="Lane",
                risk_level="medium",
                adherence_score=0.82,
                open_adr_count=0,
                active_med_count=2,
                recent_symptom_severity=2,
                last_activity="Logged medication 2h ago",
            )
        ),
    ):
        result = await service.get_patient_deep_dive(clinician_id, patient_id)

    document = result["documents"][0]
    assert document["review_status"] == "approved"
    assert document["review_note"] == "Looks valid"
    assert document["reviewer"]["first_name"] == "Mina"
    assert result["obligation_completion_rate"] == 0.5


@pytest.mark.asyncio
async def test_list_document_review_queue_scopes_to_assigned_patients(service):
    clinician_id = uuid4()
    assigned_patient_id = uuid4()
    _link_scope(service, [assigned_patient_id])
    service.document_workflows.list_document_review_queue = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            {
                "id": str(uuid4()),
                "patient_id": str(assigned_patient_id),
                "file_name": "symptoms.pdf",
                "document_type": "lab_report",
                "parse_status": "pending",
                "ai_summary": "summary",
                "source_clinic": "North Clinic",
                "created_at": "2026-04-20T10:00:00Z",
                "uploaded_by_role": "patient",
                "review_status": "pending",
                "patient_first_name": "Mia",
                "patient_last_name": "Chen",
            }
        ]
    )

    result = await service.list_document_review_queue(clinician_id)

    assert len(result) == 1
    assert result[0]["patient_first_name"] == "Mia"
    assert result[0]["review_status"] == "pending"
    assert result[0]["clinic_id"] == CLINIC_ID
    assert result[0]["clinic_name"] == "Synthetic clinic"


@pytest.mark.asyncio
async def test_approve_document_review_updates_pending_patient_upload(service, mock_db):
    clinician_id = uuid4()
    patient_id = uuid4()
    document_id = uuid4()
    service.document_workflows.approve_document_review = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "status": "reviewed",
            "document_id": str(document_id),
            "patient_id": str(patient_id),
            "review_status": "approved",
            "reviewed_by": str(clinician_id),
            "reviewed_at": "2026-04-22T18:00:00Z",
            "review_note": None,
        }
    )

    result = await service.approve_document_review(clinician_id, patient_id, document_id)

    assert result["review_status"] == DocumentReviewStatus.APPROVED.value
    service.document_workflows.approve_document_review.assert_awaited_once_with(
        clinician_id,
        patient_id,
        document_id,
    )


@pytest.mark.asyncio
async def test_reject_document_review_rejects_already_reviewed_document(service):
    service.document_workflows.reject_document_review = AsyncMock(  # type: ignore[method-assign]
        side_effect=ValidationError("Document review has already been completed")
    )

    with pytest.raises(ValidationError, match="already been completed"):
        await service.reject_document_review(uuid4(), uuid4(), uuid4(), "Bad upload")


@pytest.mark.asyncio
async def test_reject_document_review_rejects_clinician_uploaded_document(service):
    service.care_team_repo.find_active_assignment = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"id": str(uuid4())}]
    )
    service._execute = AsyncMock(  # type: ignore[method-assign]
        return_value=_response(
            data={
                "id": str(uuid4()),
                "patient_id": str(uuid4()),
                "uploaded_by_role": "clinician",
                "review_status": "pending",
            }
        )
    )

    with pytest.raises(ValidationError, match="patient-uploaded"):
        await service.reject_document_review(uuid4(), uuid4(), uuid4(), "Bad upload")


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
                    "status": "taken",
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


@pytest.mark.asyncio
async def test_list_adr_review_queue_all_statuses_for_one_patient(service, mock_db):
    patient_id, other_id = uuid4(), uuid4()
    _link_scope(service, [patient_id, other_id])
    chain = MagicMock()
    for method in ("select", "in_", "eq", "order", "limit"):
        getattr(chain, method).return_value = chain
    mock_db.table.return_value = chain
    service._execute = AsyncMock(side_effect=[_response(data=[])])  # type: ignore[method-assign]

    await service.list_adr_review_queue(uuid4(), status_filter="all", patient_id=patient_id)

    chain.in_.assert_called_once_with("patient_id", [str(patient_id)])
    chain.eq.assert_not_called()


@pytest.mark.asyncio
async def test_list_adr_review_queue_unassigned_patient_filter_is_empty(service, mock_db):
    _link_scope(service, [uuid4()])

    result = await service.list_adr_review_queue(uuid4(), patient_id=uuid4())

    assert result == {"items": [], "total": 0}
    mock_db.table.assert_not_called()


@pytest.mark.asyncio
async def test_get_adr_review_item_unknown_and_unassigned_raise_the_same_404(service, mock_db):
    assessment_id, patient_id = uuid4(), uuid4()
    row = {"id": str(assessment_id), "patient_id": str(patient_id), "status": "reviewed"}
    service.care_team_repo = MagicMock()
    service.care_team_repo.find_active_assignment = AsyncMock(return_value=[])
    service._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=[_response(data=[]), _response(data=[row])]
    )

    with pytest.raises(NotFoundError) as unknown:
        await service.get_adr_review_item(uuid4(), assessment_id)
    with pytest.raises(NotFoundError) as unassigned:
        await service.get_adr_review_item(uuid4(), assessment_id)

    assert unknown.value.code == unassigned.value.code == "NOT_FOUND"
    assert unknown.value.message == unassigned.value.message
    assert service._execute.await_count == 2


@pytest.mark.asyncio
async def test_get_adr_review_item_returns_any_status_for_an_assigned_clinician(service, mock_db):
    assessment_id, patient_id = uuid4(), uuid4()
    row = {
        "id": str(assessment_id),
        "patient_id": str(patient_id),
        "status": "dismissed",
        "patients": {"first_name": "Maya", "last_name": "Patel"},
        "symptom_reports": {"symptom": "cough", "severity": 2},
    }
    service.care_team_repo = MagicMock()
    service.care_team_repo.find_active_assignment = AsyncMock(return_value=[{"id": "x"}])
    service._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=[_response(data=[row]), _response(data=[])]
    )

    item = await service.get_adr_review_item(uuid4(), assessment_id)

    assert item["status"] == "dismissed" and item["patient_first_name"] == "Maya"


# ── Clinic chips and filters (CLN-003 slice C) ──────────────────────────────────────────


def _care_team_rows(patients):
    return [
        {
            "id": f"ct-{i}",
            "role": "primary_care",
            "patients": {"id": pid, "first_name": f"P{i}", "last_name": "Test"},
        }
        for i, pid in enumerate(patients)
    ]


def _real_scope(service, links, memberships):
    """Run the real scope over fake link rows and memberships."""
    from app.db.repositories.care_teams import CareTeamRepository

    service.memberships.active_memberships = AsyncMock(
        return_value=[
            ClinicMembership(
                clinician_id=uuid4(),
                clinic_id=c,
                role=ClinicianRole.PROVIDER,
                status=ClinicMembershipStatus.ACTIVE,
            )
            for c in memberships
        ]
    )
    return patch.object(CareTeamRepository, "list_active_links", AsyncMock(return_value=links))


LINKS = [
    {"patient_id": "p-a", "clinic_id": CLINIC_ID, "clinics": {"display_name": "Clinic A"}},
    {
        "patient_id": "p-b",
        "clinic_id": "00000000-0000-0000-0000-0000000000c2",
        "clinics": {"display_name": "Clinic B"},
    },
]
CLINIC_B_ID = "00000000-0000-0000-0000-0000000000c2"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("clinic", "expected"),
    [
        (None, {"p-a": "Clinic A", "p-b": "Clinic B"}),
        (UUID(CLINIC_ID), {"p-a": "Clinic A"}),
        (UUID(CLINIC_B_ID), {"p-b": "Clinic B"}),
        (uuid4(), {}),
    ],
)
async def test_patient_roster_tags_filters_and_hides_other_clinics(
    service, mock_db, clinic, expected
):
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value = MagicMock()
    service._execute = AsyncMock(return_value=_response(data=_care_team_rows(["p-a", "p-b"])))  # type: ignore[method-assign]
    with _real_scope(service, LINKS, [CLINIC_ID, CLINIC_B_ID]):
        rows = await service.get_patients(uuid4(), clinic)
    assert {r["id"]: r["clinic_name"] for r in rows} == expected


@pytest.mark.asyncio
async def test_clinic_without_membership_returns_empty_even_when_links_exist(service):
    service._execute = AsyncMock(return_value=_response(data=_care_team_rows(["p-b"])))  # type: ignore[method-assign]
    with _real_scope(service, LINKS, [CLINIC_ID]):
        assert await service.get_patients(uuid4(), UUID(CLINIC_B_ID)) == []
        assert (await service.list_adr_review_queue(uuid4(), clinic_id=UUID(CLINIC_B_ID)))[
            "items"
        ] == []
        assert await service.list_document_review_queue(uuid4(), UUID(CLINIC_B_ID)) == []


@pytest.mark.asyncio
async def test_sent_messages_are_tagged_and_filtered_by_the_patients_link(service):
    rows = lambda: [  # noqa: E731
        {"id": "m1", "patient_id": "p-a", "patients": {"first_name": "A", "last_name": "A"}},
        {"id": "m2", "patient_id": "p-b", "patients": {"first_name": "B", "last_name": "B"}},
    ]
    service._execute = AsyncMock(side_effect=lambda *_a, **_k: _response(data=rows()))  # type: ignore[method-assign]
    with _real_scope(service, LINKS, [CLINIC_ID, CLINIC_B_ID]):
        everything = await service.list_all_sent_messages(uuid4())
        own = await service.list_all_sent_messages(uuid4(), UUID(CLINIC_ID))
        other = await service.list_all_sent_messages(uuid4(), uuid4())
    assert [(m["id"], m["clinic_name"]) for m in everything] == [
        ("m1", "Clinic A"),
        ("m2", "Clinic B"),
    ]
    assert [m["id"] for m in own] == ["m1"]
    assert other == []


@pytest.mark.asyncio
async def test_dashboard_rows_carry_the_clinic_and_the_filter_narrows_the_patients(service):
    service._get_pending_adr_review_count = AsyncMock(return_value=0)  # type: ignore[method-assign]
    service._get_pending_medwatch_count = AsyncMock(return_value=0)  # type: ignore[method-assign]
    pid = uuid4()
    links = [
        {"patient_id": str(pid), "clinic_id": CLINIC_ID, "clinics": {"display_name": "Clinic A"}}
    ]
    risk = PatientRiskData(
        patient_id=pid, first_name="A", last_name="B", risk_level="low", adherence_score=0.9
    )
    with (
        _real_scope(service, links, [CLINIC_ID]),
        patch(
            "app.services.risk_score_service.RiskScoreService.get_patient_risk",
            new=AsyncMock(return_value=risk),
        ),
    ):
        result = await service.get_dashboard_data(uuid4())
        none = await service.get_dashboard_data(uuid4(), clinic_id=uuid4())
    assert result["patients"][0]["clinic_name"] == "Clinic A"
    assert none["patients"] == [] and none["total"] == 0
