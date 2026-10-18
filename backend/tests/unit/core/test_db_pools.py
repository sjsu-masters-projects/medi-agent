"""Slow notification reads cannot occupy the threads that Nora turns and the rest rely on."""

import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.db_pools import NOTIFICATION_POOL_SIZE, run_chat_turn_db, run_notification_db
from app.core.exceptions import ExternalServiceError
from app.models.auth import CurrentUser
from app.services import notification_centre_service as module
from app.services.notification_centre_service import NotificationCentreService


@pytest.mark.asyncio
async def test_saturated_notification_pool_leaves_chat_turn_and_default_threads_free():
    release = threading.Event()
    blockers = [
        asyncio.ensure_future(run_notification_db(lambda: release.wait(5)))
        for _ in range(NOTIFICATION_POOL_SIZE * 3)
    ]
    try:
        await asyncio.sleep(0.05)
        started = time.monotonic()
        assert await asyncio.wait_for(run_chat_turn_db(lambda: "saved"), 1) == "saved"
        assert await asyncio.wait_for(asyncio.to_thread(lambda: "history"), 1) == "history"
        assert time.monotonic() - started < 0.5
    finally:
        release.set()
        await asyncio.gather(*blockers)


def make_service():
    db = MagicMock()
    actor = CurrentUser(id=uuid4(), email="synthetic@example.com", role="patient", aal="aal1")
    return NotificationCentreService(db, actor), db


@pytest.mark.asyncio
async def test_a_slow_read_ends_as_a_notifications_unavailable_error(monkeypatch):
    service, db = make_service()
    release = threading.Event()
    db.rpc.return_value.execute.side_effect = lambda: release.wait(2)
    monkeypatch.setattr(module, "READ_TIMEOUT_SECONDS", 0.05)
    try:
        with pytest.raises(ExternalServiceError, match="Notifications unavailable"):
            await service.summary()
    finally:
        release.set()
    assert module._in_flight == {}


@pytest.mark.asyncio
async def test_identical_concurrent_reads_share_one_database_call():
    service, db = make_service()
    calls = []

    def execute():
        calls.append(1)
        time.sleep(0.1)
        return SimpleNamespace(data={"unread_count": 2, "action_item_count": 0})

    db.rpc.return_value.execute.side_effect = execute
    results = await asyncio.gather(*(service.summary() for _ in range(4)))
    assert len(calls) == 1
    assert {result.unread_count for result in results} == {2}
    assert module._in_flight == {}


@pytest.mark.asyncio
async def test_reads_for_different_people_are_not_shared():
    first, db_one = make_service()
    second, db_two = make_service()
    for db in (db_one, db_two):
        db.rpc.return_value.execute.return_value = SimpleNamespace(
            data={"unread_count": 1, "action_item_count": 0}
        )
    await asyncio.gather(first.summary(), second.summary())
    db_one.rpc.return_value.execute.assert_called_once()
    db_two.rpc.return_value.execute.assert_called_once()


@pytest.mark.asyncio
async def test_a_failed_shared_read_fails_every_waiter_and_is_not_cached():
    service, db = make_service()

    def execute():
        time.sleep(0.05)
        raise RuntimeError("database down")

    db.rpc.return_value.execute.side_effect = execute
    outcomes = await asyncio.gather(*(service.summary() for _ in range(3)), return_exceptions=True)
    assert all(isinstance(outcome, RuntimeError) for outcome in outcomes)
    db.rpc.return_value.execute.side_effect = None
    db.rpc.return_value.execute.return_value = SimpleNamespace(
        data={"unread_count": 0, "action_item_count": 0}
    )
    assert (await service.summary()).unread_count == 0
