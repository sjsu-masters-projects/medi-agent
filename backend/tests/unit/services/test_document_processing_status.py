"""Duplicate presentation is derived from authorized rows and the latest run only."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.document_processing_status import attach_duplicate_status


def database(runs):
    db = MagicMock()
    query = db.table.return_value
    for method in ("select", "in_", "order"):
        getattr(query, method).return_value = query
    query.execute.return_value = MagicMock(data=runs)
    return db, query


@pytest.mark.asyncio
async def test_duplicate_is_visible_without_changing_review_or_source():
    db, query = database([{"document_id": "own", "status": "duplicate", "attempt": 1}])
    document = {"id": "own", "parse_status": "completed", "review_status": "pending"}
    await attach_duplicate_status(db, [document])
    assert document == {
        "id": "own",
        "parse_status": "duplicate",
        "review_status": "pending",
        "summary_status": "not_required",
    }
    query.in_.assert_called_once_with("document_id", ["own"])
    query.update.assert_not_called()


@pytest.mark.asyncio
async def test_latest_attempt_wins_and_foreign_rows_cannot_attach():
    db, _ = database(
        [
            {"document_id": "own", "status": "completed", "attempt": 2},
            {"document_id": "own", "status": "duplicate", "attempt": 1},
            {"document_id": "foreign", "status": "duplicate", "attempt": 1},
        ]
    )
    document = {"id": "own", "parse_status": "completed"}
    await attach_duplicate_status(db, [document])
    assert document["parse_status"] == "completed"


@pytest.mark.asyncio
async def test_pending_state_is_not_overridden_by_old_terminal_run():
    db, _ = database([])
    document = {"id": "own", "parse_status": "pending"}
    await attach_duplicate_status(db, [document])
    db.table.assert_not_called()
    assert document["parse_status"] == "pending"


@pytest.mark.asyncio
async def test_clinician_executor_is_used_and_reads_are_batched():
    db, query = database([])
    execute = AsyncMock(return_value=MagicMock(data=[]))
    documents = [{"id": str(index), "parse_status": "completed"} for index in range(201)]
    await attach_duplicate_status(db, documents, execute)
    assert execute.await_count == 2
    assert len(query.in_.call_args_list[0].args[1]) == 200
    assert len(query.in_.call_args_list[1].args[1]) == 1
    query.execute.assert_not_called()
