"""One reminder per occurrence for a combined Today entry (PLAN-002 decision 5).

Identical activities of several plans are one entry in Today. The dispatcher asks the same
grouping the feed uses, keeps one schedule per entry and keys the reminder on the entry's id,
so retries and concurrent runs collapse on the existing unique key.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from app.services.feed_service import FeedService
from tests.unit.services.cron_store import DAY, Store, add_medication, service_for

EIGHT = DAY + timedelta(hours=8)


def groups(monkeypatch: pytest.MonkeyPatch, value: list[list[tuple[str, str]]]) -> list[int]:
    calls: list[int] = []

    async def fake(self: FeedService, patient_id: Any, target_date: Any) -> Any:
        calls.append(1)
        return value

    monkeypatch.setattr(FeedService, "combined_groups", fake)
    return calls


async def run(store: Store, minutes: int = 5) -> dict[str, Any]:
    store.now = EIGHT + timedelta(minutes=minutes)
    # Open a contiguous window around 08:00 on the first run.
    first_now = EIGHT - timedelta(minutes=20)
    store.now = first_now
    await service_for(store).dispatch_reminders()
    store.now = EIGHT + timedelta(minutes=5)
    return (await service_for(store).dispatch_reminders())["summary"]


@pytest.mark.asyncio
async def test_identical_activities_send_one_reminder_keyed_on_the_entry(monkeypatch) -> None:
    store = Store()
    add_medication(store, "med-a")
    add_medication(store, "med-b")
    groups(monkeypatch, [[("medication", "med-a"), ("medication", "med-b")]])

    summary = await run(store)

    assert summary["medication_created"] == 1
    assert summary["skipped_combined_duplicate"] == 1
    (row,) = store.notifications()
    assert row["dedupe_key"] == f"medication:med-a:{EIGHT.isoformat()}"
    assert row["metadata"]["target_id"] == "med-a"


@pytest.mark.asyncio
async def test_a_retry_or_second_run_adds_nothing(monkeypatch) -> None:
    store = Store()
    add_medication(store, "med-a")
    add_medication(store, "med-b")
    groups(monkeypatch, [[("medication", "med-a"), ("medication", "med-b")]])
    await run(store)

    again = await service_for(store).dispatch_reminders()

    assert len(store.notifications()) == 1
    assert again["summary"]["medication_created"] == 0


@pytest.mark.asyncio
async def test_a_group_where_only_one_member_is_scheduled_sends_that_one_reminder(
    monkeypatch,
) -> None:
    store = Store()
    add_medication(store, "med-a")
    add_medication(store, "med-b")
    store.tables["reminder_schedules"] = [
        row for row in store.tables["reminder_schedules"] if row["target_id"] == "med-b"
    ]
    groups(monkeypatch, [[("medication", "med-a"), ("medication", "med-b")]])

    summary = await run(store)

    assert summary["medication_created"] == 1
    assert len(store.notifications()) == 1


@pytest.mark.asyncio
async def test_the_entry_with_no_schedule_of_its_own_uses_the_first_scheduled_member(
    monkeypatch,
) -> None:
    store = Store()
    for med in ("med-a", "med-b", "med-c"):
        add_medication(store, med)
    store.tables["reminder_schedules"] = [
        row for row in store.tables["reminder_schedules"] if row["target_id"] != "med-a"
    ]
    groups(
        monkeypatch, [[("medication", "med-a"), ("medication", "med-b"), ("medication", "med-c")]]
    )

    await run(store)

    (row,) = store.notifications()
    # Keyed on the entry (med-a) so the key is stable, from the first member that has a schedule.
    assert row["dedupe_key"].startswith("medication:med-a:")


@pytest.mark.asyncio
async def test_differing_activities_each_keep_their_own_reminder(monkeypatch) -> None:
    store = Store()
    add_medication(store, "med-a")
    add_medication(store, "med-b")
    groups(monkeypatch, [])

    summary = await run(store)

    assert summary["medication_created"] == 2
    assert sorted(row["metadata"]["target_id"] for row in store.notifications()) == [
        "med-a",
        "med-b",
    ]


@pytest.mark.asyncio
async def test_retiring_one_side_leaves_one_reminder_for_the_remaining_activity(
    monkeypatch,
) -> None:
    store = Store()
    add_medication(store, "med-a")
    add_medication(store, "med-b", active=False)  # retired: no longer live
    groups(monkeypatch, [])  # a single live member forms no group

    summary = await run(store)

    assert summary["medication_created"] == 1
    assert summary["skipped_inactive_target"] == 1
    (row,) = store.notifications()
    assert row["metadata"]["target_id"] == "med-a"


@pytest.mark.asyncio
async def test_if_grouping_cannot_be_read_reminders_still_go_out(monkeypatch) -> None:
    store = Store()
    add_medication(store, "med-a")
    add_medication(store, "med-b")

    async def broken(self: FeedService, patient_id: Any, target_date: Any) -> Any:
        raise RuntimeError("read unavailable")

    monkeypatch.setattr(FeedService, "combined_groups", broken)

    summary = await run(store)

    assert summary["medication_created"] == 2
    assert summary["grouping_unavailable"] == 1
