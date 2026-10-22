"""Tests for StaffService: clinic team management scoped by clinic membership (CLN-003)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import AuthorizationError, ValidationError
from app.models.clinic_membership import ClinicMembership
from app.models.enums import ClinicianRole, ClinicMembershipStatus
from app.services.staff_service import StaffService

CLINIC_A = "00000000-0000-0000-0000-0000000000a1"
CLINIC_B = "00000000-0000-0000-0000-0000000000b2"


def _membership(clinician_id, clinic_id=CLINIC_A, role="admin"):
    return ClinicMembership(
        clinician_id=clinician_id,
        clinic_id=clinic_id,
        role=ClinicianRole(role),
        status=ClinicMembershipStatus.ACTIVE,
    )


@pytest.fixture
def service():
    svc = StaffService(db=MagicMock())
    svc.clinic_repo.get_identity_by_id = MagicMock(  # type: ignore[method-assign]
        return_value={"id": CLINIC_A, "display_name": "City Health", "code": "ABC123"}
    )
    svc.memberships.set_member_role = AsyncMock(return_value={"role": "nurse"})  # type: ignore[method-assign]
    svc.memberships.remove_member = AsyncMock(return_value={"status": "removed"})  # type: ignore[method-assign]
    return svc


def _memberships(svc, *memberships):
    svc.memberships.active_memberships = AsyncMock(return_value=list(memberships))  # type: ignore[method-assign]


# ── list ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_staff_returns_members_with_the_role_held_at_the_clinic(service):
    admin_id, peer_id = uuid4(), uuid4()
    _memberships(service, _membership(admin_id, role="provider"))
    service.memberships.repo.list_active_for_clinic = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            {"clinician_id": str(admin_id), "role": "provider"},
            {"clinician_id": str(peer_id), "role": "nurse"},
        ]
    )
    service.clinician_repo.list_staff_by_ids = MagicMock(  # type: ignore[method-assign]
        return_value=[
            {"id": str(admin_id), "role": "admin", "first_name": "A"},
            {"id": str(peer_id), "role": "admin", "first_name": "P"},
        ]
    )

    result = await service.list_staff(admin_id)

    # Roles come from the memberships, never from clinicians.role.
    assert {row["id"]: row["role"] for row in result["staff"]} == {
        str(admin_id): "provider",
        str(peer_id): "nurse",
    }
    assert result["clinic_id"] == CLINIC_A
    assert result["clinic_name"] == "City Health"
    # The open join code is for admins only; this caller is a provider there.
    assert result["clinic_code"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["provider", "nurse"])
async def test_list_staff_hides_the_clinic_code_from_non_admins(service, role):
    me = uuid4()
    _memberships(service, _membership(me, role=role))
    service.memberships.repo.list_active_for_clinic = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"clinician_id": str(me), "role": role}]
    )
    service.clinician_repo.list_staff_by_ids = MagicMock(return_value=[{"id": str(me)}])  # type: ignore[method-assign]
    assert (await service.list_staff(me))["clinic_code"] is None


@pytest.mark.asyncio
async def test_list_staff_gives_the_clinic_code_to_an_admin(service):
    me = uuid4()
    _memberships(service, _membership(me, role="admin"))
    service.memberships.repo.list_active_for_clinic = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"clinician_id": str(me), "role": "admin"}]
    )
    service.clinician_repo.list_staff_by_ids = MagicMock(return_value=[{"id": str(me)}])  # type: ignore[method-assign]
    assert (await service.list_staff(me))["clinic_code"] == "ABC123"


@pytest.mark.asyncio
async def test_list_staff_without_a_membership_is_refused(service):
    _memberships(service)
    with pytest.raises(AuthorizationError):
        await service.list_staff(uuid4())


@pytest.mark.asyncio
async def test_list_staff_requires_a_clinic_when_there_are_several(service):
    clinician_id = uuid4()
    _memberships(service, _membership(clinician_id), _membership(clinician_id, CLINIC_B))
    with pytest.raises(ValidationError) as raised:
        await service.list_staff(clinician_id)
    assert raised.value.code == "CLINIC_REQUIRED"


@pytest.mark.asyncio
async def test_list_staff_for_a_clinic_without_membership_is_refused(service):
    clinician_id = uuid4()
    _memberships(service, _membership(clinician_id))
    with pytest.raises(AuthorizationError) as raised:
        await service.list_staff(clinician_id, UUID(CLINIC_B))
    assert raised.value.reason_code == "CLINIC_MEMBERSHIP_REQUIRED"


# ── role change and removal ─────────────────────────────────


@pytest.mark.asyncio
async def test_update_role_self_change_rejected(service):
    admin_id = uuid4()
    with pytest.raises(ValidationError, match="own role"):
        await service.update_role(admin_id, admin_id, "provider")


@pytest.mark.asyncio
async def test_update_role_runs_at_the_named_clinic(service):
    admin_id, target_id = uuid4(), uuid4()
    _memberships(service, _membership(admin_id), _membership(admin_id, CLINIC_B, "provider"))

    result = await service.update_role(admin_id, target_id, "nurse", UUID(CLINIC_A))

    assert result == {"id": str(target_id), "role": "nurse"}
    service.memberships.set_member_role.assert_awaited_once_with(
        admin_id, CLINIC_A, target_id, "nurse"
    )


@pytest.mark.asyncio
async def test_an_admin_at_one_clinic_cannot_change_roles_at_another(service):
    admin_id, target_id = uuid4(), uuid4()
    _memberships(service, _membership(admin_id, CLINIC_A, "admin"))
    with pytest.raises(AuthorizationError):
        await service.update_role(admin_id, target_id, "admin", UUID(CLINIC_B))
    service.memberships.set_member_role.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_rights_do_not_carry_between_clinics(service):
    """Admin at A, provider at B: acting at B is refused even though the legacy role is admin."""
    admin_id, target_id = uuid4(), uuid4()
    _memberships(
        service,
        _membership(admin_id, CLINIC_A, "admin"),
        _membership(admin_id, CLINIC_B, "provider"),
    )

    with pytest.raises(AuthorizationError) as raised:
        await service.update_role(admin_id, target_id, "provider", UUID(CLINIC_B))
    assert raised.value.reason_code == "ADMIN_SCOPE_ONLY"
    with pytest.raises(AuthorizationError):
        await service.remove_member(admin_id, target_id, UUID(CLINIC_B))
    with pytest.raises(AuthorizationError):
        await service.invite_member(admin_id, "new@example.com", "provider", UUID(CLINIC_B))
    service.memberships.set_member_role.assert_not_awaited()
    service.memberships.remove_member.assert_not_awaited()


@pytest.mark.asyncio
async def test_staff_actions_fail_closed_without_a_membership(service):
    """No active membership: no name-matching fallback, whatever clinicians.role says."""
    admin_id, target_id = uuid4(), uuid4()
    _memberships(service)
    for call in (
        service.update_role(admin_id, target_id, "provider"),
        service.remove_member(admin_id, target_id),
        service.invite_member(admin_id, "new@example.com", "provider"),
    ):
        with pytest.raises(AuthorizationError):
            await asyncio.wait_for(call, timeout=5)


@pytest.mark.asyncio
async def test_non_admin_cannot_remove_members(service):
    clinician_id = uuid4()
    _memberships(service, _membership(clinician_id, role="provider"))
    with pytest.raises(AuthorizationError):
        await service.remove_member(clinician_id, uuid4())
    service.memberships.remove_member.assert_not_awaited()


@pytest.mark.asyncio
async def test_remove_member_self_rejected(service):
    admin_id = uuid4()
    with pytest.raises(ValidationError, match="yourself"):
        await service.remove_member(admin_id, admin_id)


@pytest.mark.asyncio
async def test_remove_member_runs_at_the_clinic(service):
    admin_id, target_id = uuid4(), uuid4()
    _memberships(service, _membership(admin_id))

    result = await service.remove_member(admin_id, target_id)

    assert result == {"status": "removed", "id": str(target_id)}
    service.memberships.remove_member.assert_awaited_once_with(admin_id, CLINIC_A, target_id)


# ── invitations ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invite_refuses_an_address_already_in_the_clinic(service):
    admin_id, existing_id = uuid4(), uuid4()
    _memberships(service, _membership(admin_id))
    service.clinician_repo.list_by_email = MagicMock(return_value=[{"id": str(existing_id)}])  # type: ignore[method-assign]
    service.memberships.repo.get_active = AsyncMock(return_value={"role": "provider"})  # type: ignore[method-assign]

    with pytest.raises(ValidationError, match="already in your clinic"):
        await service.invite_member(admin_id, "peer@example.com", "provider")


@pytest.mark.asyncio
async def test_invite_allows_an_address_that_belongs_to_another_clinic(service):
    admin_id, existing_id = uuid4(), uuid4()
    _memberships(service, _membership(admin_id))
    service.clinician_repo.list_by_email = MagicMock(return_value=[{"id": str(existing_id)}])  # type: ignore[method-assign]
    service.memberships.repo.get_active = AsyncMock(return_value=None)  # type: ignore[method-assign]
    invitations = MagicMock()
    invitations.create = AsyncMock(return_value={"status": "queued"})

    with patch("app.services.staff_service.EmailInvitationService", return_value=invitations):
        result = await service.invite_member(admin_id, "peer@example.com", "nurse")

    assert result == {"status": "queued"}
    invitations.create.assert_awaited_once_with(
        admin_id, "peer@example.com", "nurse", "City Health", clinic_id=UUID(CLINIC_A)
    )


@pytest.mark.asyncio
async def test_invite_new_address_is_queued_for_the_named_clinic(service):
    admin_id = uuid4()
    _memberships(service, _membership(admin_id), _membership(admin_id, CLINIC_B, "admin"))
    service.clinician_repo.list_by_email = MagicMock(return_value=[])  # type: ignore[method-assign]
    invitations = MagicMock()
    invitations.create = AsyncMock(return_value={"status": "queued"})

    with patch("app.services.staff_service.EmailInvitationService", return_value=invitations):
        await service.invite_member(admin_id, "new@example.com", "provider", UUID(CLINIC_B))

    assert invitations.create.await_args.kwargs["clinic_id"] == UUID(CLINIC_B)
