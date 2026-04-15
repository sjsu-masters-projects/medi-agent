"""Tests for ObligationService."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import NotFoundError
from app.services.obligation_service import ObligationService


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def service(mock_db):
    return ObligationService(db=mock_db)


def _chain(mock_db, *, data):
    chain = MagicMock()
    chain.execute.return_value = SimpleNamespace(data=data)
    for method in ("select", "eq", "order", "insert", "update", "single"):
        getattr(chain, method).return_value = chain
    mock_db.table.return_value = chain
    return chain


@pytest.mark.asyncio
async def test_list_obligations_active_only_filters_active_rows(service, mock_db):
    patient_id = uuid4()
    obligations = [{"id": str(uuid4()), "description": "Walk daily"}]
    chain = _chain(mock_db, data=obligations)

    result = await service.list_obligations(patient_id, active_only=True)

    assert result == obligations
    chain.eq.assert_any_call("patient_id", str(patient_id))
    chain.eq.assert_any_call("is_active", True)
    chain.order.assert_called_once_with("created_at", desc=True)


@pytest.mark.asyncio
async def test_list_obligations_allows_inactive_rows_when_requested(service, mock_db):
    patient_id = uuid4()
    obligations = [
        {"id": str(uuid4()), "description": "Walk daily", "is_active": True},
        {"id": str(uuid4()), "description": "Check weight", "is_active": False},
    ]
    chain = _chain(mock_db, data=obligations)

    result = await service.list_obligations(patient_id, active_only=False)

    assert result == obligations
    assert ("is_active", True) not in [call.args for call in chain.eq.call_args_list]


@pytest.mark.asyncio
async def test_create_obligation_inserts_patient_scoped_row(service, mock_db):
    patient_id = uuid4()
    payload = {"description": "Walk daily", "frequency": "daily"}
    created = {"id": str(uuid4()), **payload, "patient_id": str(patient_id)}
    chain = _chain(mock_db, data=[created])

    result = await service.create_obligation(patient_id, payload)

    assert result == created
    mock_db.table.assert_called_once_with("obligations")
    chain.insert.assert_called_once_with({"patient_id": str(patient_id), **payload})


@pytest.mark.asyncio
async def test_update_obligation_returns_existing_row_when_no_updates(service):
    obligation_id = uuid4()
    patient_id = uuid4()
    existing = {"id": str(obligation_id), "description": "Existing"}
    service._get = AsyncMock(return_value=existing)  # type: ignore[method-assign]

    result = await service.update_obligation(
        obligation_id,
        patient_id,
        {"description": None, "frequency": None},
    )

    assert result == existing
    service._get.assert_awaited_once_with(obligation_id, patient_id)


@pytest.mark.asyncio
async def test_update_obligation_raises_when_row_is_missing(service, mock_db):
    obligation_id = uuid4()
    patient_id = uuid4()
    _chain(mock_db, data=[])

    with pytest.raises(NotFoundError, match=str(obligation_id)):
        await service.update_obligation(obligation_id, patient_id, {"description": "Updated"})


@pytest.mark.asyncio
async def test_get_raises_when_obligation_is_missing(service, mock_db):
    obligation_id = uuid4()
    patient_id = uuid4()
    _chain(mock_db, data=None)

    with pytest.raises(NotFoundError, match=str(obligation_id)):
        await service._get(obligation_id, patient_id)
