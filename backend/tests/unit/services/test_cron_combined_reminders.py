"""One reminder per occurrence for a combined Today entry (PLAN-002 decision 5).

Identical activities of several plans are one entry in Today. The dispatcher asks the same
grouping the feed uses, keeps one schedule per entry and keys the reminder on the entry's id,
so retries and concurrent runs collapse on the existing unique key.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from app.services.cron_service import CronService
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


def broken_grouping(monkeypatch: pytest.MonkeyPatch, *, fail_times: int | None = None) -> list[int]:
    """Make the grouping read fail (always, or ``fail_times`` times) and count the attempts."""
    attempts: list[int] = []

    async def flaky(self: FeedService, patient_id: Any, target_date: Any) -> Any:
        attempts.append(1)
        if fail_times is None or len(attempts) <= fail_times:
            raise RuntimeError("read unavailable")
        return [[("medication", "med-a"), ("medication", "med-b")]]

    monkeypatch.setattr(FeedService, "combined_groups", flaky)
    return attempts


@pytest.fixture(autouse=True)
def no_real_backoff(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    delays: list[float] = []

    async def record(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr("app.services.cron_service.asyncio.sleep", record)
    return delays


@pytest.mark.asyncio
async def test_a_transient_grouping_failure_is_retried_and_still_groups(
    monkeypatch, no_real_backoff
) -> None:
    store = Store()
    add_medication(store, "med-a")
    add_medication(store, "med-b")
    attempts = broken_grouping(monkeypatch, fail_times=2)

    summary = await run(store)

    # The first dispatch needed three attempts, with the bounded backoff between them.
    assert no_real_backoff == [0.2, 0.5]
    assert len(attempts) == 4  # three for the first dispatch, one for the second
    assert "grouping_unavailable" not in summary
    assert summary["medication_created"] == 1 and summary["skipped_combined_duplicate"] == 1
    assert len(store.notifications()) == 1


@pytest.mark.asyncio
async def test_retries_are_bounded_by_attempts_and_by_the_run_budget(
    monkeypatch, no_real_backoff
) -> None:
    store = Store()
    add_medication(store, "med-a")
    add_medication(store, "med-b")
    attempts = broken_grouping(monkeypatch)
    monkeypatch.setattr(CronService, "GROUPING_RETRY_BUDGET_SECONDS", 0.0)

    summary = await run(store)

    # No budget left: a single attempt per dispatch, no sleeping at all.
    assert no_real_backoff == []
    assert summary["grouping_unavailable"] == 1
    assert len(attempts) == 2  # one per dispatch (first run has no summary of its own to inspect)


@pytest.mark.asyncio
async def test_unreadable_grouping_sends_one_reminder_per_identity_when_it_cannot_wait(
    monkeypatch,
) -> None:
    store = Store()
    add_medication(store, "med-b")
    add_medication(store, "med-a")
    broken_grouping(monkeypatch)

    summary = await run(store)

    # Both are due at 08:00; the run starts at 08:05, so waiting would be late.
    assert summary["grouping_unavailable"] == 1
    assert summary["medication_created"] == 1
    assert summary["reminders_deduped_by_identity"] == 1
    assert "reminders_deferred" not in summary
    (row,) = store.notifications()
    # The lowest id represents identical activities, so the key is stable across runs.
    assert row["metadata"]["target_id"] == "med-a"


@pytest.mark.asyncio
async def test_unreadable_grouping_never_merges_activities_that_differ(monkeypatch) -> None:
    store = Store()
    add_medication(store, "med-a")
    add_medication(store, "med-b")
    store.tables["medications"][1]["dosage"] = "2 tablets"
    broken_grouping(monkeypatch)

    summary = await run(store)

    assert summary["medication_created"] == 2
    assert "reminders_deduped_by_identity" not in summary


@pytest.mark.asyncio
async def test_unreadable_grouping_sends_the_same_reminder_once_across_reruns(monkeypatch) -> None:
    store = Store()
    add_medication(store, "med-a")
    add_medication(store, "med-b")
    broken_grouping(monkeypatch)
    await run(store)

    again = await service_for(store).dispatch_reminders()

    assert len(store.notifications()) == 1
    assert again["summary"]["medication_created"] == 0


@pytest.mark.asyncio
async def test_a_reminder_with_time_to_spare_waits_for_the_next_run_and_is_then_sent_once(
    monkeypatch,
) -> None:
    store = Store()
    add_medication(store, "med-a")
    add_medication(store, "med-b")
    attempts = broken_grouping(monkeypatch)

    # 07:45 run covers [07:45, 08:00) is empty; the 07:50 run covers up to 08:05, and 08:00
    # is 10 minutes ahead: the next run (about 08:05) delivers it within the lateness bound.
    store.now = EIGHT - timedelta(minutes=30)
    await service_for(store).dispatch_reminders()
    store.now = EIGHT - timedelta(minutes=10)
    first = (await service_for(store).dispatch_reminders())["summary"]

    assert first["reminders_deferred"] == 2
    assert first["resume_from"] == EIGHT.isoformat()
    assert store.notifications() == []
    assert first["medication_created"] == 0

    # The next run resumes at the deferred time instead of the window end, so nothing is lost.
    store.now = EIGHT - timedelta(minutes=5) + timedelta(minutes=10)
    second = (await service_for(store).dispatch_reminders())["summary"]

    assert second["window_start"] == EIGHT.isoformat()
    assert second["medication_created"] == 1
    assert len(store.notifications()) == 1
    assert len(attempts) >= 3


@pytest.mark.asyncio
async def test_a_deferral_is_bounded_to_one_run_even_if_grouping_stays_down(monkeypatch) -> None:
    store = Store()
    add_medication(store, "med-a")
    broken_grouping(monkeypatch)
    # A single schedule cannot be combined: it never waits.
    summary = await run(store)

    assert summary["medication_created"] == 1
    assert "reminders_deferred" not in summary and "grouping_unavailable" not in summary


@pytest.mark.asyncio
async def test_a_dry_run_that_defers_does_not_move_the_next_window(monkeypatch) -> None:
    store = Store()
    add_medication(store, "med-a")
    add_medication(store, "med-b")
    broken_grouping(monkeypatch)
    store.now = EIGHT - timedelta(minutes=30)
    await service_for(store).dispatch_reminders()
    store.now = EIGHT - timedelta(minutes=10)

    dry = (await service_for(store).dispatch_reminders(dry_run=True))["summary"]

    assert dry["reminders_deferred"] == 2
    assert store.notifications() == []
    assert await service_for(store)._previous_reminder_window_end("reminders_dispatch") != EIGHT
