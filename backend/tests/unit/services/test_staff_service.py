"""Tests for StaffService — clinic team management."""

from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.services.staff_service import StaffService


@pytest.fixture
def mock_db():
    """Create a mock Supabase client."""
    return MagicMock()


@pytest.fixture
def service(mock_db):
    svc = StaffService(db=mock_db)
    svc._lookup_clinic_code = MagicMock(return_value=None)  # type: ignore[method-assign]
    return svc


@pytest.fixture
def raw_service(mock_db):
    return StaffService(db=mock_db)


def _chain(mock_db, *, data):
    """Set up a chainable table mock returning the given data."""
    chain = MagicMock()
    chain.execute.return_value = Mock(data=data)
    for method in ("select", "eq", "single", "order", "limit", "insert", "update", "delete"):
        getattr(chain, method).return_value = chain
    mock_db.table.return_value = chain
    return chain


# ── _require_admin ──────────────────────────────────────────


def test_lookup_clinic_code_falls_back_to_canonical_name_when_clinic_id_is_stale(raw_service, mock_db):
    stale_id_chain = MagicMock()
    for method in ("select", "eq", "single"):
        getattr(stale_id_chain, method).return_value = stale_id_chain
    stale_id_chain.execute.side_effect = Exception("PGRST116: The result contains 0 rows")

    canonical_chain = MagicMock()
    for method in ("select", "eq", "limit"):
        getattr(canonical_chain, method).return_value = canonical_chain
    canonical_chain.execute.return_value = Mock(data=[{"code": "0901CA82DC"}])

    mock_db.table.side_effect = [stale_id_chain, canonical_chain]

    code = raw_service._lookup_clinic_code("missing-clinic-id", "San Jose   Health Clinic")

    assert code == "0901CA82DC"


def test_lookup_clinic_code_uses_peer_clinician_clinic_id_when_name_queries_miss(raw_service, mock_db):
    stale_id_chain = MagicMock()
    for method in ("select", "eq", "single"):
        getattr(stale_id_chain, method).return_value = stale_id_chain
    stale_id_chain.execute.side_effect = Exception("PGRST116: The result contains 0 rows")

    canonical_chain = MagicMock()
    for method in ("select", "eq", "limit"):
        getattr(canonical_chain, method).return_value = canonical_chain
    canonical_chain.execute.return_value = Mock(data=[])

    display_chain = MagicMock()
    for method in ("select", "eq", "limit"):
        getattr(display_chain, method).return_value = display_chain
    display_chain.execute.return_value = Mock(data=[])

    peer_clinicians_chain = MagicMock()
    for method in ("select", "eq", "limit"):
        getattr(peer_clinicians_chain, method).return_value = peer_clinicians_chain
    peer_clinicians_chain.execute.return_value = Mock(data=[{"clinic_id": "clinic-uuid-1"}])

    peer_id_clinic_chain = MagicMock()
    for method in ("select", "eq", "single"):
        getattr(peer_id_clinic_chain, method).return_value = peer_id_clinic_chain
    peer_id_clinic_chain.execute.return_value = Mock(data={"code": "0901CA82DC"})

    mock_db.table.side_effect = [
        stale_id_chain,
        canonical_chain,
        display_chain,
        peer_clinicians_chain,
        peer_id_clinic_chain,
    ]

    code = raw_service._lookup_clinic_code("stale-id", "San Jose Health Clinic")

    assert code == "0901CA82DC"


@pytest.mark.asyncio
async def test_require_admin_not_found(service, mock_db):
    _chain(mock_db, data=None)
    with pytest.raises(NotFoundError):
        await service._require_admin(uuid4())


@pytest.mark.asyncio
async def test_require_admin_single_no_rows_error_maps_to_not_found(service, mock_db):
    chain = MagicMock()
    for method in ("select", "eq", "single"):
        getattr(chain, method).return_value = chain
    chain.execute.side_effect = Exception("PGRST116: The result contains 0 rows")
    mock_db.table.return_value = chain

    with pytest.raises(NotFoundError):
        await service._require_admin(uuid4())


@pytest.mark.asyncio
async def test_require_admin_not_admin(service, mock_db):
    _chain(mock_db, data={"clinic_name": "Clinic", "role": "provider"})
    with pytest.raises(AuthorizationError, match="admin"):
        await service._require_admin(uuid4())


@pytest.mark.asyncio
async def test_require_admin_success(service, mock_db):
    _chain(mock_db, data={"clinic_name": "Clinic A", "role": "admin"})
    result = await service._require_admin(uuid4())
    assert result == {"clinic_id": None, "clinic_name": "Clinic A", "clinic_code": None}


# ── list_staff ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_staff_success(service, mock_db):
    clinician_id = uuid4()
    staff_rows = [
        {
            "id": str(uuid4()),
            "email": "a@test.com",
            "first_name": "A",
            "last_name": "B",
            "role": "admin",
            "specialty": "General",
            "created_at": "2025-01-01T00:00:00Z",
        }
    ]

    # First call: _get_clinic_name → single clinician lookup
    chain1 = MagicMock()
    chain1.execute.return_value = Mock(data={"clinic_name": "Clinic A"})
    for m in ("select", "eq", "single"):
        getattr(chain1, m).return_value = chain1

    # Second call: list staff by clinic_name
    chain2 = MagicMock()
    chain2.execute.return_value = Mock(data=staff_rows)
    for m in ("select", "eq", "order"):
        getattr(chain2, m).return_value = chain2

    mock_db.table.side_effect = [chain1, chain2]

    result = await service.list_staff(clinician_id)
    assert result["clinic_name"] == "Clinic A"
    assert len(result["staff"]) == 1
    assert result["staff"][0]["email"] == "a@test.com"


@pytest.mark.asyncio
async def test_list_staff_with_clinic_id_merges_id_and_name_matches(service, mock_db):
    clinician_id = uuid4()

    chain_context = MagicMock()
    chain_context.execute.return_value = Mock(
        data={
            "clinic_id": "clinic-123",
            "clinic_name": "Clinic A",
        }
    )
    for method in ("select", "eq", "single"):
        getattr(chain_context, method).return_value = chain_context

    chain_by_id = MagicMock()
    chain_by_id.execute.return_value = Mock(
        data=[
            {
                "id": str(uuid4()),
                "email": "admin@test.com",
                "first_name": "Admin",
                "last_name": "One",
                "role": "admin",
                "specialty": "General",
                "created_at": "2025-01-01T00:00:00Z",
                "clinic_id": "clinic-123",
                "clinic_name": "Clinic A",
            }
        ]
    )
    for method in ("select", "eq", "order"):
        getattr(chain_by_id, method).return_value = chain_by_id

    chain_by_name = MagicMock()
    chain_by_name.execute.return_value = Mock(
        data=[
            {
                "id": str(uuid4()),
                "email": "provider@test.com",
                "first_name": "Provider",
                "last_name": "Two",
                "role": "provider",
                "specialty": "Cardiology",
                "created_at": "2025-01-02T00:00:00Z",
                "clinic_id": "clinic-123",
                "clinic_name": "Clinic A",
            }
        ]
    )
    for method in ("select", "eq", "order"):
        getattr(chain_by_name, method).return_value = chain_by_name

    mock_db.table.side_effect = [chain_context, chain_by_id, chain_by_name]

    result = await service.list_staff(clinician_id)
    assert result["clinic_name"] == "Clinic A"
    assert len(result["staff"]) == 2
    assert {row["email"] for row in result["staff"]} == {"admin@test.com", "provider@test.com"}


@pytest.mark.asyncio
async def test_list_staff_single_no_rows_error_maps_to_not_found(service, mock_db):
    clinician_id = uuid4()

    chain = MagicMock()
    for method in ("select", "eq", "single"):
        getattr(chain, method).return_value = chain
    chain.execute.side_effect = Exception("PGRST116: The result contains 0 rows")
    mock_db.table.return_value = chain

    with pytest.raises(NotFoundError):
        await service.list_staff(clinician_id)


# ── update_role ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_role_self_change_rejected(service, mock_db):
    admin_id = uuid4()
    _chain(mock_db, data={"clinic_name": "Clinic A", "role": "admin"})
    with pytest.raises(ValidationError, match="own role"):
        await service.update_role(admin_id, admin_id, "nurse")


@pytest.mark.asyncio
async def test_update_role_target_not_in_clinic(service, mock_db):
    admin_id = uuid4()
    target_id = uuid4()

    # _require_admin
    chain_admin = MagicMock()
    chain_admin.execute.return_value = Mock(data={"clinic_name": "Clinic A", "role": "admin"})
    for m in ("select", "eq", "single"):
        getattr(chain_admin, m).return_value = chain_admin

    # target lookup — different clinic
    chain_target = MagicMock()
    chain_target.execute.return_value = Mock(
        data={"id": str(target_id), "clinic_name": "Other Clinic"}
    )
    for m in ("select", "eq", "single"):
        getattr(chain_target, m).return_value = chain_target

    mock_db.table.side_effect = [chain_admin, chain_target]

    with pytest.raises(NotFoundError, match="Staff member"):
        await service.update_role(admin_id, target_id, "nurse")


@pytest.mark.asyncio
async def test_update_role_success(service, mock_db):
    admin_id = uuid4()
    target_id = uuid4()

    chain_admin = MagicMock()
    chain_admin.execute.return_value = Mock(data={"clinic_name": "Clinic A", "role": "admin"})
    for m in ("select", "eq", "single"):
        getattr(chain_admin, m).return_value = chain_admin

    chain_target = MagicMock()
    chain_target.execute.return_value = Mock(
        data={"id": str(target_id), "clinic_name": "Clinic A"}
    )
    for m in ("select", "eq", "single"):
        getattr(chain_target, m).return_value = chain_target

    chain_update = MagicMock()
    chain_update.execute.return_value = Mock()
    for m in ("update", "eq"):
        getattr(chain_update, m).return_value = chain_update

    mock_db.table.side_effect = [chain_admin, chain_target, chain_update]

    result = await service.update_role(admin_id, target_id, "nurse")
    assert result["role"] == "nurse"
    assert result["id"] == str(target_id)


# ── remove_member ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_remove_member_self_rejected(service, mock_db):
    admin_id = uuid4()
    _chain(mock_db, data={"clinic_name": "Clinic A", "role": "admin"})
    with pytest.raises(ValidationError, match="yourself"):
        await service.remove_member(admin_id, admin_id)


@pytest.mark.asyncio
async def test_remove_member_success(service, mock_db):
    admin_id = uuid4()
    target_id = uuid4()

    chain_admin = MagicMock()
    chain_admin.execute.return_value = Mock(data={"clinic_name": "Clinic A", "role": "admin"})
    for m in ("select", "eq", "single"):
        getattr(chain_admin, m).return_value = chain_admin

    chain_target = MagicMock()
    chain_target.execute.return_value = Mock(
        data={"id": str(target_id), "clinic_name": "Clinic A"}
    )
    for m in ("select", "eq", "single"):
        getattr(chain_target, m).return_value = chain_target

    chain_update = MagicMock()
    chain_update.execute.return_value = Mock()
    for m in ("update", "eq"):
        getattr(chain_update, m).return_value = chain_update

    mock_db.table.side_effect = [chain_admin, chain_target, chain_update]

    result = await service.remove_member(admin_id, target_id)
    assert result["status"] == "removed"


# ── invite_member ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_invite_existing_same_clinic(service, mock_db):
    admin_id = uuid4()

    chain_admin = MagicMock()
    chain_admin.execute.return_value = Mock(data={"clinic_name": "Clinic A", "role": "admin"})
    for m in ("select", "eq", "single"):
        getattr(chain_admin, m).return_value = chain_admin

    chain_existing = MagicMock()
    chain_existing.execute.return_value = Mock(
        data=[{"id": str(uuid4()), "clinic_name": "Clinic A"}]
    )
    for m in ("select", "eq"):
        getattr(chain_existing, m).return_value = chain_existing

    mock_db.table.side_effect = [chain_admin, chain_existing]

    with pytest.raises(ValidationError, match="already in your clinic"):
        await service.invite_member(admin_id, "dup@test.com", "provider")


@pytest.mark.asyncio
async def test_invite_existing_different_clinic(service, mock_db):
    admin_id = uuid4()
    target_id = uuid4()

    chain_admin = MagicMock()
    chain_admin.execute.return_value = Mock(data={"clinic_name": "Clinic A", "role": "admin"})
    for m in ("select", "eq", "single"):
        getattr(chain_admin, m).return_value = chain_admin

    chain_existing = MagicMock()
    chain_existing.execute.return_value = Mock(
        data=[{"id": str(target_id), "clinic_name": "Other"}]
    )
    for m in ("select", "eq"):
        getattr(chain_existing, m).return_value = chain_existing

    chain_update = MagicMock()
    chain_update.execute.return_value = Mock()
    for m in ("update", "eq"):
        getattr(chain_update, m).return_value = chain_update

    mock_db.table.side_effect = [chain_admin, chain_existing, chain_update]

    result = await service.invite_member(admin_id, "other@test.com", "nurse")
    assert result["status"] == "added"


@pytest.mark.asyncio
async def test_invite_new_email_pending(service, mock_db):
    admin_id = uuid4()

    chain_admin = MagicMock()
    chain_admin.execute.return_value = Mock(data={"clinic_name": "Clinic A", "role": "admin"})
    for m in ("select", "eq", "single"):
        getattr(chain_admin, m).return_value = chain_admin

    chain_existing = MagicMock()
    chain_existing.execute.return_value = Mock(data=[])
    for m in ("select", "eq"):
        getattr(chain_existing, m).return_value = chain_existing

    mock_db.table.side_effect = [chain_admin, chain_existing]

    result = await service.invite_member(admin_id, "new@test.com", "provider")
    assert result["status"] == "pending"
