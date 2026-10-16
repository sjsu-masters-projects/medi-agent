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
