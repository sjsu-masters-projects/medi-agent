"""Tests for ClinicMembershipService (CLN-003 slice A)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, call
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.models.enums import ClinicianRole, ClinicMembershipStatus
from app.services.clinic_membership_service import ClinicMembershipService

CLINIC_A = "00000000-0000-0000-0000-00000000000a"
CLINIC_B = "00000000-0000-0000-0000-00000000000b"


def _service(rows):
    chain = MagicMock()
    chain.execute.return_value = Mock(data=rows)
    for method in ("select", "eq", "limit"):
        getattr(chain, method).return_value = chain
    db = MagicMock()
    db.table.return_value = chain
    return ClinicMembershipService(SimpleNamespace(db=db)), db, chain


def _row(clinician_id, clinic_id, role="provider"):
    return {"clinician_id": clinician_id, "clinic_id": clinic_id, "role": role, "status": "active"}


@pytest.mark.asyncio
async def test_active_memberships_reads_only_active_rows_for_the_clinician():
    clinician_id = str(uuid4())
    service, db, chain = _service([_row(clinician_id, CLINIC_B), _row(clinician_id, CLINIC_A)])

    memberships = await service.active_memberships(clinician_id)

    db.table.assert_called_once_with("clinic_memberships")
    chain.eq.assert_has_calls([call("clinician_id", clinician_id), call("status", "active")])
    assert [str(m.clinic_id) for m in memberships] == [CLINIC_A, CLINIC_B]
    assert memberships[0].status is ClinicMembershipStatus.ACTIVE


@pytest.mark.asyncio
async def test_acting_membership_returns_the_single_clinic_and_role():
    clinician_id = str(uuid4())
    service, _, _ = _service([_row(clinician_id, CLINIC_A, "admin")])

    membership = await service.acting_membership(clinician_id)

    assert membership is not None
    assert str(membership.clinic_id) == CLINIC_A
    assert membership.role is ClinicianRole.ADMIN


@pytest.mark.asyncio
async def test_acting_membership_is_none_for_a_clinician_without_a_clinic():
    service, _, _ = _service([])

    assert await service.acting_membership(uuid4()) is None


@pytest.mark.asyncio
async def test_acting_membership_refuses_to_guess_between_clinics():
    clinician_id = str(uuid4())
    service, _, _ = _service([_row(clinician_id, CLINIC_A), _row(clinician_id, CLINIC_B)])

    with pytest.raises(ValidationError, match="Choose the clinic"):
        await service.acting_membership(clinician_id)


@pytest.mark.asyncio
async def test_clinic_member_ids_lists_active_members_of_one_clinic():
    first, second = str(uuid4()), str(uuid4())
    service, _, chain = _service([{"clinician_id": first}, {"clinician_id": second}, {}])

    assert await service.clinic_member_ids(CLINIC_A) == [first, second]
    chain.eq.assert_has_calls([call("clinic_id", CLINIC_A), call("status", "active")])
    chain.limit.assert_called_once_with(200)


# ── Clinic operations (066) ──────────────────────────────────


def _rpc_service(*, data=None, error=None):
    db = MagicMock()
    execute = db.rpc.return_value.execute
    if error is not None:
        execute.side_effect = error
    else:
        execute.return_value = Mock(data=data)
    return ClinicMembershipService(SimpleNamespace(db=db)), db


def _api_error(hint, code="P0001"):
    from postgrest.exceptions import APIError

    return APIError({"code": code, "message": "refused", "hint": hint, "details": None})


@pytest.mark.asyncio
async def test_join_by_code_sends_the_actor_code_and_role_to_the_database():
    service, db = _rpc_service(data={"status": "joined", "clinic_id": CLINIC_A})
    result = await service.join_by_code("clinician-1", " abc123 ", "nurse")
    assert result["status"] == "joined"
    name, params = db.rpc.call_args.args
    assert name == "clinician_clinic_operation"
    assert params == {
        "p_actor": "clinician-1",
        "p_action": "join_code",
        "p_payload": {"clinic_code": "ABC123", "role": "nurse"},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("hint", "expected_type", "expected_code"),
    [
        ("clinic_code_invalid", "ValidationError", "CLINIC_CODE_INVALID"),
        ("clinic_code_inactive", "ValidationError", "CLINIC_CODE_INACTIVE"),
        ("invalid_role", "ValidationError", "INVALID_ROLE"),
        ("membership_inactive", "AuthorizationError", None),
        ("admin_required", "AuthorizationError", None),
        ("clinic_unavailable", "AuthorizationError", None),
        ("member_unavailable", "NotFoundError", None),
    ],
)
async def test_database_refusals_become_public_errors(hint, expected_type, expected_code):
    service, _db = _rpc_service(error=_api_error(hint))
    with pytest.raises(Exception) as raised:  # noqa: PT011
        await service.join_by_code("clinician-1", "ABC123", "provider")
    assert type(raised.value).__name__ == expected_type
    if expected_code:
        assert raised.value.code == expected_code


@pytest.mark.asyncio
async def test_a_removed_membership_cannot_rejoin_by_code():
    service, _db = _rpc_service(error=_api_error("membership_inactive"))
    with pytest.raises(Exception) as raised:  # noqa: PT011
        await service.join_by_code("clinician-1", "ABC123", "provider")
    assert raised.value.reason_code == "CLINIC_MEMBERSHIP_REQUIRED"
    assert raised.value.code == "MEMBERSHIP_INACTIVE"
    assert "invite you again" in raised.value.message


@pytest.mark.asyncio
async def test_missing_function_reports_setup_pending_without_database_text():
    service, _db = _rpc_service(error=_api_error(None, code="PGRST202"))
    with pytest.raises(Exception) as raised:  # noqa: PT011
        await service.clinics("clinician-1")
    assert raised.value.code == "CLINIC_SETUP_PENDING"


@pytest.mark.asyncio
async def test_role_change_and_removal_name_the_clinic_and_member():
    service, db = _rpc_service(data={"id": "m"})
    await service.set_member_role("admin-1", CLINIC_A, "member-1", "nurse")
    assert db.rpc.call_args.args[1]["p_payload"] == {
        "clinic_id": CLINIC_A,
        "member_id": "member-1",
        "role": "nurse",
    }
    await service.remove_member("admin-1", CLINIC_A, "member-1")
    assert db.rpc.call_args.args[1]["p_action"] == "remove_member"


@pytest.mark.asyncio
async def test_a_suspended_clinic_is_not_an_acting_clinic():
    clinician_id = str(uuid4())
    rows = [
        {**_row(clinician_id, CLINIC_A), "clinics": {"status": "suspended"}},
        {**_row(clinician_id, CLINIC_B, "admin"), "clinics": {"status": "active"}},
    ]
    service, _db, _chain = _service(rows)
    memberships = await service.active_memberships(clinician_id)
    assert [str(m.clinic_id) for m in memberships] == [CLINIC_B]


# ── List scope: the clinic of each link (CLN-003 slice C) ───────────────────────────────


def _links():
    return [
        {"patient_id": "p-a", "clinic_id": CLINIC_A, "clinics": {"display_name": "Clinic A"}},
        {"patient_id": "p-b", "clinic_id": CLINIC_B, "clinics": {"display_name": "Clinic B"}},
        {"patient_id": None, "clinic_id": CLINIC_A, "clinics": {"display_name": "Clinic A"}},
    ]


def _scope_service(memberships):
    from unittest.mock import AsyncMock, patch

    service, _db, _chain = _service([])
    service.active_memberships = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            SimpleNamespace(clinic_id=clinic, role=ClinicianRole.PROVIDER) for clinic in memberships
        ]
    )
    patcher = patch(
        "app.services.clinic_membership_service.CareTeamRepository.list_active_links",
        new=AsyncMock(return_value=_links()),
    )
    return service, patcher


@pytest.mark.asyncio
async def test_link_scope_without_a_filter_is_every_active_link_with_its_clinic():
    service, patcher = _scope_service([CLINIC_A, CLINIC_B])
    with patcher:
        scope = await service.link_scope("c-1")
    assert scope.patient_ids == ["p-a", "p-b"]
    assert scope.tag("p-b") == {"clinic_id": CLINIC_B, "clinic_name": "Clinic B"}


@pytest.mark.asyncio
async def test_link_scope_for_own_clinic_keeps_only_that_clinics_links():
    service, patcher = _scope_service([CLINIC_A, CLINIC_B])
    with patcher:
        scope = await service.link_scope("c-1", CLINIC_A)
    assert scope.patient_ids == ["p-a"]


@pytest.mark.asyncio
async def test_link_scope_for_a_clinic_without_membership_is_empty_not_an_error():
    service, patcher = _scope_service([CLINIC_A])
    with patcher:
        other = await service.link_scope("c-1", CLINIC_B)
        unknown = await service.link_scope("c-1", str(uuid4()))
    assert other.patient_ids == [] and unknown.patient_ids == []


# ── Default clinic, leave and rename (067) ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_default_leave_and_rename_send_their_actions():
    service, db = _rpc_service(data={"status": "left"})
    await service.set_default("c-1", CLINIC_A)
    await service.leave("c-1", CLINIC_A)
    await service.rename_clinic("c-1", CLINIC_A, "New name")
    sent = [(c.args[1]["p_action"], c.args[1]["p_payload"]) for c in db.rpc.call_args_list]
    assert sent == [
        ("set_default", {"clinic_id": CLINIC_A}),
        ("leave", {"clinic_id": CLINIC_A}),
        ("update_clinic", {"clinic_id": CLINIC_A, "display_name": "New name"}),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("hint", "code"),
    [
        ("last_clinic", "LAST_CLINIC"),
        ("sole_admin", "SOLE_ADMIN"),
        ("clinic_name_taken", "CLINIC_NAME_TAKEN"),
        ("invalid_name", "INVALID_NAME"),
    ],
)
async def test_new_refusals_have_public_codes(hint, code):
    service, _db = _rpc_service(error=_api_error(hint, code="22023"))
    with pytest.raises(ValidationError) as raised:
        await service.leave("c-1", CLINIC_A)
    assert raised.value.code == code
