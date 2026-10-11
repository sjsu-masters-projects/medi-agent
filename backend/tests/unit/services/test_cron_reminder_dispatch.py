"""Reminder dispatch end to end against an in-memory table store.

The store enforces the partial unique index on ``notifications.dedupe_key`` the way
PostgreSQL does (a conflicting batch inserts nothing), so the windowing, dedupe and
conflict fallback are exercised through ``CronService.dispatch_reminders`` itself.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import count
from typing import Any

import pytest
from postgrest.exceptions import APIError

from app.services.cron_service import CronService
from app.services.reminder_schedule_service import DAY_ORDER

DAY = datetime(2026, 10, 12, tzinfo=UTC)
PATIENT = "00000000-0000-4000-8000-000000000001"


class _Result:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _Query:
    def __init__(self, store: _Store, table: str) -> None:
        self.store, self.table = store, table
        self.tests: list[Any] = []
        self.write: tuple[str, Any] | None = None
        self.ordering: tuple[str, bool] | None = None
        self.count: int | None = None

    def select(self, *_: Any) -> _Query:
        return self

    def eq(self, column: str, value: Any) -> _Query:
        self.tests.append(lambda row: row.get(column) == value)
        return self

    def in_(self, column: str, values: list[Any]) -> _Query:
        self.tests.append(lambda row: row.get(column) in set(values))
        return self

    def gte(self, column: str, value: str) -> _Query:
        self.tests.append(lambda row: str(row.get(column)) >= value)
        return self

    def lt(self, column: str, value: str) -> _Query:
        self.tests.append(lambda row: str(row.get(column)) < value)
        return self

    def order(self, column: str, *, desc: bool = False) -> _Query:
        self.ordering = (column, desc)
        return self

    def limit(self, value: int) -> _Query:
        self.count = value
        return self

    def insert(self, rows: Any) -> _Query:
        self.write = ("insert", rows)
        return self

    def update(self, values: dict[str, Any]) -> _Query:
        self.write = ("update", values)
        return self

    def execute(self) -> _Result:
        rows = self.store.tables.setdefault(self.table, [])
        if self.write and self.write[0] == "insert":
            return _Result(self.store.insert(self.table, self.write[1]))
        matched = [row for row in rows if all(test(row) for test in self.tests)]
        if self.write and self.write[0] == "update":
            for row in matched:
                row.update(self.write[1])
            return _Result([dict(row) for row in matched])
        if self.ordering:
            column, desc = self.ordering
            matched.sort(key=lambda row: str(row.get(column)), reverse=desc)
        return _Result([dict(row) for row in matched[: self.count or None]])


class _Store:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.now = DAY
        self._ids = count(1)
        self.batch_inserts = 0

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def insert(self, table: str, payload: Any) -> list[dict[str, Any]]:
        batch = [dict(row) for row in (payload if isinstance(payload, list) else [payload])]
        rows = self.tables.setdefault(table, [])
        if table == "notifications":
            if isinstance(payload, list):
                self.batch_inserts += 1
            taken = {row["dedupe_key"] for row in rows if row.get("dedupe_key")}
            for row in batch:
                if row.get("dedupe_key") in taken:
                    # A unique violation aborts the whole statement.
                    raise APIError(
                        {"code": "23505", "message": "duplicate key value violates unique"}
                    )
                taken.add(row.get("dedupe_key"))
        for row in batch:
            row.setdefault("id", f"{table}-{next(self._ids)}")
            if table == "cron_job_runs":
                row.setdefault("started_at", self.now.isoformat())
        rows.extend(batch)
        return [dict(row) for row in batch]

    def notifications(self) -> list[dict[str, Any]]:
        return self.tables.get("notifications", [])


@pytest.fixture
def store() -> _Store:
    return _Store()


def _service(store: _Store) -> CronService:
    service = CronService(store)  # type: ignore[arg-type]
    service._utc_now = lambda: store.now  # type: ignore[method-assign]
    return service


async def _dispatch(store: _Store, at: datetime, **kwargs: Any) -> dict[str, Any]:
    store.now = at
    result = await _service(store).dispatch_reminders(**kwargs)
    return result["summary"]


def _medication(store: _Store, med_id: str, *, active: bool = True, frequency: str = "daily"):
    store.tables.setdefault("medications", []).append(
        {
            "id": med_id,
            "name": "Synthetic tablet",
            "dosage": "1 tablet",
            "instructions": "",
            "frequency": frequency,
            "is_active": active,
        }
    )
    store.tables.setdefault("reminder_schedules", []).append(
        {
            "id": f"schedule-{med_id}",
            "patient_id": PATIENT,
            "target_type": "medication",
            "target_id": med_id,
            "timezone": "UTC",
            "times_of_day": ["08:00"],
            "days_of_week": list(DAY_ORDER),
            "is_enabled": True,
        }
    )


def _visit(store: _Store, *, status: str, at: datetime, visit_id: str = "visit-1") -> None:
    store.tables.setdefault("appointments", []).append(
        {
            "id": visit_id,
            "patient_id": PATIENT,
            "scheduled_at": at.isoformat(),
            "status": status,
            "clinician_name": "Dr. Synthetic",
            "location": "Synthetic Clinic",
            "appointment_type": "follow-up",
            "reason": "",
        }
    )


@pytest.mark.asyncio
async def test_a_late_run_covers_the_gap_since_the_last_window(store: _Store) -> None:
    _medication(store, "med-1")
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
async def test_a_long_pause_never_replays_more_than_an_hour(store: _Store) -> None:
    _medication(store, "med-1")
    await _dispatch(store, DAY + timedelta(hours=5, minutes=45))
    resumed = await _dispatch(store, DAY + timedelta(hours=8, minutes=5))
    assert resumed["window_mode"] == "catch_up_capped"
    assert resumed["window_start"] == (DAY + timedelta(hours=8, minutes=5)).isoformat()
    assert resumed["catch_up_minutes"] == 0
    assert resumed["medication_candidates"] == 0
    assert store.notifications() == []


@pytest.mark.asyncio
async def test_a_dry_run_neither_sends_nor_moves_the_window(store: _Store) -> None:
    _medication(store, "med-1")
    await _dispatch(store, DAY + timedelta(hours=7, minutes=40))
    dry = await _dispatch(store, DAY + timedelta(hours=7, minutes=50), dry_run=True)
    assert dry["medication_candidates"] == 1 and store.notifications() == []
    real = await _dispatch(store, DAY + timedelta(hours=7, minutes=55))
    assert real["window_start"] == (DAY + timedelta(hours=7, minutes=55)).isoformat()
    assert real["medication_created"] == 1


@pytest.mark.asyncio
async def test_overlapping_windows_never_send_a_reminder_twice(store: _Store) -> None:
    _medication(store, "med-1")
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
async def test_a_confirmed_visit_gets_its_day_before_reminder(store: _Store) -> None:
    visit_at = DAY + timedelta(days=1, hours=17)
    _visit(store, status="confirmed", at=visit_at)
    _visit(store, status="cancelled", at=visit_at, visit_id="visit-cancelled")
    summary = await _dispatch(store, DAY + timedelta(hours=16, minutes=50))
    assert summary["appointment_24h_candidates"] == 1
    assert summary["appointment_24h_created"] == 1
    [reminder] = store.notifications()
    assert reminder["dedupe_key"] == f"appointment:visit-1:24h:{visit_at.isoformat()}"


@pytest.mark.asyncio
async def test_a_rescheduled_visit_is_reminded_once_for_its_new_time(store: _Store) -> None:
    first_time = DAY + timedelta(days=1, hours=17)
    _visit(store, status="confirmed", at=first_time)
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
    store: _Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    _medication(store, "med-1")
    _medication(store, "med-2")
    # A concurrent run inserted one reminder after this run's pre-check.
    store.tables["notifications"] = [
        {"id": "other", "dedupe_key": f"medication:med-1:{(DAY + timedelta(hours=8)).isoformat()}"}
    ]

    async def nothing_seen(_keys: list[str]) -> set[str]:
        return set()

    service = _service(store)
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
async def test_schedules_that_must_not_remind_are_counted_as_skipped(store: _Store) -> None:
    _medication(store, "med-active")
    _medication(store, "med-stopped", active=False)
    _medication(store, "med-prn", frequency="as needed")
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
