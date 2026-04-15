"""Tests for ClinicService."""

from unittest.mock import MagicMock, Mock

import pytest

from app.core.exceptions import ValidationError
from app.services.clinic_service import ClinicService


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def service(mock_db):
    return ClinicService(db=mock_db)


def _chain(mock_db, *, data):
    chain = MagicMock()
    chain.execute.return_value = Mock(data=data)
    for method in ("select", "eq", "insert"):
        getattr(chain, method).return_value = chain
    mock_db.table.return_value = chain
    return chain


@pytest.mark.asyncio
async def test_resolve_clinic_code_success(service, mock_db):
    _chain(
        mock_db,
        data=[
            {
                "id": "clinic-1",
                "code": "ABC123",
                "display_name": "City Health",
                "status": "active",
            }
        ],
    )

    result = await service.resolve_clinic_code("abc123")

    assert result == {
        "clinic_id": "clinic-1",
        "clinic_code": "ABC123",
        "clinic_name": "City Health",
        "status": "active",
    }


@pytest.mark.asyncio
async def test_resolve_clinic_code_invalid(service, mock_db):
    _chain(mock_db, data=[])

    with pytest.raises(ValidationError, match="invalid"):
        await service.resolve_clinic_code("missing")


@pytest.mark.asyncio
async def test_resolve_clinic_code_inactive(service, mock_db):
    _chain(
        mock_db,
        data=[
            {
                "id": "clinic-1",
                "code": "ABC123",
                "display_name": "City Health",
                "status": "suspended",
            }
        ],
    )

    with pytest.raises(ValidationError, match="inactive"):
        await service.resolve_clinic_code("ABC123")


@pytest.mark.asyncio
async def test_provision_clinic_success(service, mock_db):
    existing_chain = MagicMock()
    existing_chain.execute.return_value = Mock(data=[])
    for method in ("select", "eq"):
        getattr(existing_chain, method).return_value = existing_chain

    created_row = {
        "id": "8f8ffd0d-bd7f-4312-93f7-f9cb6f3f8a55",
        "code": "ABC123",
        "display_name": "City Health",
        "canonical_name": "city health",
        "type2_npi": "1234567890",
        "status": "active",
        "created_at": "2026-01-01T00:00:00Z",
    }
    insert_chain = MagicMock()
    insert_chain.execute.return_value = Mock(data=[created_row])
    for method in ("insert", "select"):
        getattr(insert_chain, method).return_value = insert_chain

    mock_db.table.side_effect = [existing_chain, insert_chain]

    result = await service.provision_clinic("  City   Health  ", "1234567890")

    assert result == created_row
    insert_chain.insert.assert_called_once_with(
        {
            "display_name": "City Health",
            "canonical_name": "city health",
            "type2_npi": "1234567890",
            "status": "active",
        }
    )


@pytest.mark.asyncio
async def test_provision_clinic_duplicate_precheck(service, mock_db):
    _chain(mock_db, data=[{"id": "existing"}])

    with pytest.raises(ValidationError, match="already exists"):
        await service.provision_clinic("City Health", None)


@pytest.mark.asyncio
async def test_provision_clinic_empty_name(service):
    with pytest.raises(ValidationError, match="cannot be empty"):
        await service.provision_clinic("   ", None)


@pytest.mark.asyncio
async def test_provision_clinic_rls_failure_returns_clear_error(service, mock_db):
    existing_chain = MagicMock()
    existing_chain.execute.return_value = Mock(data=[])
    for method in ("select", "eq"):
        getattr(existing_chain, method).return_value = existing_chain

    insert_chain = MagicMock()
    insert_chain.insert.return_value = insert_chain
    insert_chain.execute.side_effect = Exception(
        'new row violates row-level security policy for table "clinics"'
    )

    mock_db.table.side_effect = [existing_chain, insert_chain]

    with pytest.raises(ValidationError, match="blocked by clinics table RLS policy"):
        await service.provision_clinic("City Health", "1234567890")
