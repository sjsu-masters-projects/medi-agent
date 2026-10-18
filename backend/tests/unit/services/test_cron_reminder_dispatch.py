"""Reminder dispatch end to end against an in-memory table store.

The store enforces the partial unique index on ``notifications.dedupe_key``, so the
windowing, dedupe and conflict fallback run through ``CronService.dispatch_reminders``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest

from app.services.reminder_schedule_service import DAY_ORDER
from tests.unit.services.cron_store import (
    DAY,
    PATIENT,
    Store,
    add_medication,
    add_visit,
    service_for,
)


@pytest.fixture
def store() -> Store:
    return Store()


async def _dispatch(store: Store, at: datetime, **kwargs: Any) -> dict[str, Any]:
    store.now = at
    result = await service_for(store).dispatch_reminders(**kwargs)
    return result["summary"]


@pytest.mark.asyncio
async def test_a_late_run_covers_the_gap_since_the_last_window(store: Store) -> None:
    add_medication(store, "med-1")
    first = await _dispatch(store, DAY + timedelta(hours=7, minutes=40))
    assert first["window_mode"] == "first_run"
    assert first["window_end"] == (DAY + timedelta(hours=7, minutes=55)).isoformat()
    assert first["medication_created"] == 0

    # Scheduler ran ten minutes late: the 08:00 dose sits between the two "now" values.
    late = await _dispatch(store, DAY + timedelta(hours=8, minutes=5))
    assert late["window_mode"] == "contiguous"
    assert late["window_start"] == first["window_end"]
    assert late["catch_up_minutes"] == 10.0
    assert late["medication_created"] == 1
    assert [row["dedupe_key"] for row in store.notifications()] == [
        f"medication:med-1:{(DAY + timedelta(hours=8)).isoformat()}"
    ]


@pytest.mark.asyncio
async def test_a_long_pause_never_replays_more_than_an_hour(store: Store) -> None:
    add_medication(store, "med-1")
    await _dispatch(store, DAY + timedelta(hours=5, minutes=45))
    resumed = await _dispatch(store, DAY + timedelta(hours=8, minutes=5))
    assert resumed["window_mode"] == "catch_up_capped"
    assert resumed["window_start"] == (DAY + timedelta(hours=8, minutes=5)).isoformat()
    assert resumed["catch_up_minutes"] == 0
    assert resumed["medication_candidates"] == 0
    assert store.notifications() == []


@pytest.mark.asyncio
async def test_a_dry_run_neither_sends_nor_moves_the_window(store: Store) -> None:
    add_medication(store, "med-1")
    await _dispatch(store, DAY + timedelta(hours=7, minutes=40))
    dry = await _dispatch(store, DAY + timedelta(hours=7, minutes=50), dry_run=True)
    assert dry["medication_candidates"] == 1 and store.notifications() == []
    real = await _dispatch(store, DAY + timedelta(hours=7, minutes=55))
    assert real["window_start"] == (DAY + timedelta(hours=7, minutes=55)).isoformat()
    assert real["medication_created"] == 1


@pytest.mark.asyncio
async def test_overlapping_windows_never_send_a_reminder_twice(store: Store) -> None:
    add_medication(store, "med-1")
    first = await _dispatch(store, DAY + timedelta(hours=7, minutes=50))
    assert first["medication_created"] == 1
    # A run recorded before windows were stored gives no previous end: the next window
    # starts at "now" and overlaps the last one.
    for run in store.tables["cron_job_runs"]:
        run["summary"].pop("window_end")
    overlap = await _dispatch(store, DAY + timedelta(hours=7, minutes=55))
    assert overlap["window_mode"] == "first_run"
    assert overlap["medication_candidates"] == 1
    assert overlap["medication_existing"] == 1 and overlap["medication_created"] == 0
    assert len(store.notifications()) == 1


@pytest.mark.asyncio
async def test_a_confirmed_visit_gets_its_day_before_reminder(store: Store) -> None:
    visit_at = DAY + timedelta(days=1, hours=17)
    add_visit(store, status="confirmed", at=visit_at)
    add_visit(store, status="cancelled", at=visit_at, visit_id="visit-cancelled")
    summary = await _dispatch(store, DAY + timedelta(hours=16, minutes=50))
    assert summary["appointment_24h_candidates"] == 1
    assert summary["appointment_24h_created"] == 1
    [reminder] = store.notifications()
    assert reminder["dedupe_key"] == f"appointment:visit-1:24h:{visit_at.isoformat()}"


@pytest.mark.asyncio
async def test_a_rescheduled_visit_is_reminded_once_for_its_new_time(store: Store) -> None:
    first_time = DAY + timedelta(days=1, hours=17)
    add_visit(store, status="confirmed", at=first_time)
    await _dispatch(store, DAY + timedelta(hours=16, minutes=50))
    assert len(store.notifications()) == 1

    new_time = DAY + timedelta(days=1, hours=17, minutes=30)
    # Stored in another valid offset form; the key normalises it to UTC.
    store.tables["appointments"][0]["scheduled_at"] = new_time.isoformat().replace("+00:00", "Z")
    moved = await _dispatch(store, DAY + timedelta(hours=17, minutes=20))
    assert moved["appointment_24h_created"] == 1
    for run in store.tables["cron_job_runs"]:
        run["summary"].pop("window_end")
    again = await _dispatch(store, DAY + timedelta(hours=17, minutes=25))
    assert again["appointment_24h_existing"] == 1 and again["appointment_24h_created"] == 0
    assert [row["dedupe_key"] for row in store.notifications()] == [
        f"appointment:visit-1:24h:{first_time.isoformat()}",
        f"appointment:visit-1:24h:{new_time.isoformat()}",
    ]


@pytest.mark.asyncio
async def test_a_conflict_in_the_batch_keeps_the_other_reminders(
    store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_medication(store, "med-1")
    add_medication(store, "med-2")
    # A concurrent run inserted one reminder after this run's pre-check.
    store.tables["notifications"] = [
        {"id": "other", "dedupe_key": f"medication:med-1:{(DAY + timedelta(hours=8)).isoformat()}"}
    ]

    async def nothing_seen(_keys: list[str]) -> set[str]:
        return set()

    service = service_for(store)
    monkeypatch.setattr(service, "_fetch_existing_notification_keys", nothing_seen)
    store.now = DAY + timedelta(hours=7, minutes=50)
    result = await service.dispatch_reminders()

    assert result["status"] == "success"
    assert result["summary"]["medication_created"] == 1
    assert result["summary"]["medication_existing"] == 1
    assert store.batch_inserts == 1  # the failed batch is not retried as a batch
    assert sorted(row["dedupe_key"] for row in store.notifications()) == sorted(
        f"medication:{med}:{(DAY + timedelta(hours=8)).isoformat()}" for med in ("med-1", "med-2")
    )
    [run] = store.tables["cron_job_runs"]
    assert run["status"] == "success" and run["summary"] == result["summary"]


@pytest.mark.asyncio
async def test_schedules_that_must_not_remind_are_counted_as_skipped(store: Store) -> None:
    add_medication(store, "med-active")
    add_medication(store, "med-stopped", active=False)
    add_medication(store, "med-prn", frequency="as needed")
    store.tables["reminder_schedules"].append(
        {
            "id": "schedule-missing",
            "patient_id": PATIENT,
            "target_type": "obligation",
            "target_id": "removed-item",
            "timezone": "UTC",
            "times_of_day": ["08:00"],
            "days_of_week": list(DAY_ORDER),
            "is_enabled": True,
        }
    )
    summary = await _dispatch(store, DAY + timedelta(hours=7, minutes=50))
    assert summary["skipped_inactive_target"] == 2
    assert summary["skipped_frequency_mismatch"] == 1
    assert summary["medication_created"] == 1


@pytest.mark.asyncio
async def test_visit_reminders_name_the_visits_own_clinic(store: Store) -> None:
    add_visit(store, status="confirmed", at=DAY + timedelta(days=1, hours=17))
    await _dispatch(store, DAY + timedelta(hours=16, minutes=50))
    [reminder] = store.notifications()
    assert "Clinic: Synthetic Visit Clinic." in reminder["body"]
    assert reminder["metadata"]["clinic_name"] == "Synthetic Visit Clinic"
    assert reminder["metadata"]["clinic_id"] == "clinic-visit"
