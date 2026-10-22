"""An in-memory table store for CronService tests.

It enforces the partial unique index on ``notifications.dedupe_key`` the way PostgreSQL
does (a conflicting batch inserts nothing), and records cron runs with the store's clock.
"""

from __future__ import annotations

from datetime import UTC, datetime
from itertools import count
from typing import Any

from postgrest.exceptions import APIError

from app.services.cron_service import CronService
from app.services.reminder_schedule_service import DAY_ORDER

DAY = datetime(2026, 10, 12, tzinfo=UTC)
PATIENT = "00000000-0000-4000-8000-000000000001"


class _Result:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class _Query:
    def __init__(self, store: Store, table: str) -> None:
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


class _Rpc:
    """What ``db.rpc(...)`` returns: a builder whose ``execute()`` yields the result."""

    def __init__(self, data: Any) -> None:
        self._data = data

    def execute(self) -> _Result:
        return _Result(self._data)


class Store:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.now = DAY
        self._ids = count(1)
        self.batch_inserts = 0
        # Canned RPC results by function name, and the arguments each call was made with.
        self.rpc_results: dict[str, Any] = {}
        self.rpc_calls: list[tuple[str, Any]] = []

    def table(self, name: str) -> _Query:
        return _Query(self, name)

    def rpc(self, name: str, params: Any = None) -> _Rpc:
        self.rpc_calls.append((name, params))
        return _Rpc(self.rpc_results.get(name))

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


def service_for(store: Store) -> CronService:
    service = CronService(store)  # type: ignore[arg-type]
    service._utc_now = lambda: store.now  # type: ignore[method-assign]
    return service


def add_medication(store: Store, med_id: str, *, active: bool = True, frequency: str = "daily"):
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


def add_visit(store: Store, *, status: str, at: datetime, visit_id: str = "visit-1") -> None:
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
            "clinic_id": "clinic-visit",
            "clinics": {"display_name": "Synthetic Visit Clinic"},
        }
    )
