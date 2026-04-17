"""Tests for shared Supabase execution helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import ExternalServiceError
from app.db.supabase_execute import execute_async, execute_sync, is_transient_supabase_error


class _Owner:
    def __init__(self, db):
        self.db = db


def _query(*, result=None, side_effect=None):
    query = MagicMock()
    if side_effect is not None:
        query.execute.side_effect = side_effect
    else:
        query.execute.return_value = result
    return query


def test_is_transient_supabase_error_classifies_transport_failures():
    assert is_transient_supabase_error(Exception("Resource temporarily unavailable"))
    assert is_transient_supabase_error(Exception("connection reset by peer"))
    assert not is_transient_supabase_error(Exception("duplicate key value violates unique constraint"))


def test_execute_sync_retries_transient_failure_and_refreshes_client():
    original_db = MagicMock()
    refreshed_db = MagicMock()
    owner = _Owner(original_db)
    first_query = _query(side_effect=[Exception("Resource temporarily unavailable")])
    second_query = _query(result=SimpleNamespace(data=[{"id": "ok"}]))

    with patch("app.db.supabase_execute.refresh_client", return_value=refreshed_db) as refresh_client:
        result = execute_sync(
            owner,
            lambda db: first_query if db is original_db else second_query,
            operation="clinic lookup",
            retry_transient=True,
        )

    assert result.data == [{"id": "ok"}]
    assert owner.db is refreshed_db
    refresh_client.assert_called_once_with(original_db)
    assert first_query.execute.call_count == 1
    assert second_query.execute.call_count == 1


def test_execute_sync_does_not_retry_non_transient_failure():
    owner = _Owner(MagicMock())
    query = _query(side_effect=[Exception("duplicate key value violates unique constraint")])

    with pytest.raises(Exception, match="duplicate key value"):
        execute_sync(
            owner,
            lambda _db: query,
            operation="clinic lookup",
            retry_transient=True,
        )

    assert query.execute.call_count == 1


@pytest.mark.asyncio
async def test_execute_async_retries_transient_failure_and_refreshes_client():
    original_db = MagicMock()
    refreshed_db = MagicMock()
    owner = _Owner(original_db)
    first_query = _query(side_effect=[Exception("ReadError")])
    second_query = _query(result=SimpleNamespace(data={"id": "ok"}))

    with patch("app.db.supabase_execute.refresh_client", return_value=refreshed_db) as refresh_client:
        result = await execute_async(
            owner,
            lambda db: first_query if db is original_db else second_query,
            operation="staff lookup",
            retry_transient=True,
        )

    assert result.data == {"id": "ok"}
    assert owner.db is refreshed_db
    refresh_client.assert_called_once_with(original_db)
    assert first_query.execute.call_count == 1
    assert second_query.execute.call_count == 1


@pytest.mark.asyncio
async def test_execute_async_raises_external_service_error_after_retries():
    owner = _Owner(MagicMock())
    query = _query(
        side_effect=[
            Exception("Resource temporarily unavailable"),
            Exception("Resource temporarily unavailable"),
        ]
    )

    with patch("app.db.supabase_execute.refresh_client", return_value=owner.db) as refresh_client:
        with pytest.raises(ExternalServiceError, match="temporarily unavailable"):
            await execute_async(
                owner,
                lambda _db: query,
                operation="clinic lookup",
                retry_transient=True,
            )

    assert query.execute.call_count == 2
    assert refresh_client.call_count == 1
