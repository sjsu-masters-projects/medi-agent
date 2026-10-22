"""A small in-memory Supabase stand-in for care-team ownership tests.

Tables are lists of dicts. Filters are applied exactly as sent, so a query that forgets a
patient or team filter returns another team's row and the test fails. RPCs are registered
as callables; every call is recorded. Synthetic data only.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

PATIENT = "11111111-1111-4111-8111-111111111111"
SECOND_PATIENT = "11111111-1111-4111-8111-222222222222"
CLINICIAN = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"
THIRD = "44444444-4444-4444-8444-444444444444"
TEAM = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"
OTHER_TEAM = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2"
THIRD_TEAM = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3"
CLINIC = "cccccccc-cccc-4ccc-8ccc-ccccccccccc1"
OTHER_CLINIC = "cccccccc-cccc-4ccc-8ccc-ccccccccccc2"


def standard_links() -> list[dict[str, Any]]:
    """Cardiology (CLINICIAN) and orthopaedics (OTHER) both treat PATIENT; THIRD treats nobody."""
    return [
        {
            "id": TEAM,
            "patient_id": PATIENT,
            "clinician_id": CLINICIAN,
            "clinic_id": CLINIC,
            "status": "active",
            "role": "specialist",
        },
        {
            "id": OTHER_TEAM,
            "patient_id": PATIENT,
            "clinician_id": OTHER,
            "clinic_id": OTHER_CLINIC,
            "status": "active",
            "role": "specialist",
        },
    ]


class FakeQuery:
    def __init__(self, db: FakeDB, table: str) -> None:
        self.db = db
        self.table_name = table
        self.filters: list[Callable[[dict[str, Any]], bool]] = []
        self.described: list[tuple[str, str, Any]] = []
        self._negate = False
        self._order: list[tuple[str, bool]] = []
        self._limit: int | None = None
        self._single = False
        self._range: tuple[int, int] | None = None
        self._write: tuple[str, Any] | None = None
        self.selected: str | None = None

    # reads --------------------------------------------------------------------------
    def select(self, columns: str = "*", **_kwargs: Any) -> FakeQuery:
        self.selected = columns
        return self

    def _add(self, kind: str, column: str, value: Any, test: Callable[[dict[str, Any]], bool]):
        self.described.append((kind, column, value))
        if "." in column:
            # Filters on an embedded resource are not simulated; the row passes.
            self._negate = False
            return self
        negate, self._negate = self._negate, False
        self.filters.append((lambda row: not test(row)) if negate else test)
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        return self._add("eq", column, value, lambda row: str(row.get(column)) == str(value))

    def neq(self, column: str, value: Any) -> FakeQuery:
        return self._add("neq", column, value, lambda row: str(row.get(column)) != str(value))

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        allowed = {str(value) for value in values}
        return self._add("in", column, values, lambda row: str(row.get(column)) in allowed)

    def is_(self, column: str, value: str) -> FakeQuery:
        assert value == "null"
        return self._add("is", column, value, lambda row: row.get(column) is None)

    def gte(self, column: str, value: Any) -> FakeQuery:
        return self._add("gte", column, value, lambda row: str(row.get(column)) >= str(value))

    def lte(self, column: str, value: Any) -> FakeQuery:
        return self._add("lte", column, value, lambda row: str(row.get(column)) <= str(value))

    def lt(self, column: str, value: Any) -> FakeQuery:
        return self._add("lt", column, value, lambda row: str(row.get(column)) < str(value))

    @property
    def not_(self) -> FakeQuery:
        self._negate = True
        return self

    def order(self, column: str, *, desc: bool = False, **_kwargs: Any) -> FakeQuery:
        self._order.append((column, desc))
        return self

    def limit(self, count: int, **kwargs: Any) -> FakeQuery:
        if not kwargs:  # a limit on an embedded resource does not limit these rows
            self._limit = count
        return self

    def range(self, start: int, end: int) -> FakeQuery:
        self._range = (start, end)
        return self

    def single(self) -> FakeQuery:
        self._single = True
        return self

    maybe_single = single

    # writes -------------------------------------------------------------------------
    def insert(self, payload: Any) -> FakeQuery:
        self._write = ("insert", payload)
        return self

    def update(self, payload: dict[str, Any]) -> FakeQuery:
        self._write = ("update", payload)
        return self

    def delete(self) -> FakeQuery:
        self._write = ("delete", None)
        return self

    def execute(self) -> Any:
        rows = self.db.tables.setdefault(self.table_name, [])
        self.db.queries.append(
            (self.table_name, self._write[0] if self._write else "select", list(self.described))
        )
        if self._write and self._write[0] == "insert":
            payload = self._write[1]
            batch = payload if isinstance(payload, list) else [payload]
            created = [{"id": str(uuid4()), **copy.deepcopy(row)} for row in batch]
            rows.extend(created)
            return SimpleNamespace(data=created)
        matched = [row for row in rows if all(test(row) for test in self.filters)]
        if self._write and self._write[0] == "update":
            for row in matched:
                row.update(copy.deepcopy(self._write[1]))
            return SimpleNamespace(data=[copy.deepcopy(row) for row in matched])
        if self._write and self._write[0] == "delete":
            self.db.tables[self.table_name] = [row for row in rows if row not in matched]
            return SimpleNamespace(data=matched)
        for column, desc in reversed(self._order):
            matched = sorted(matched, key=lambda row: str(row.get(column)), reverse=desc)
        total = len(matched)
        if self._range is not None:
            matched = matched[self._range[0] : self._range[1] + 1]
        if self._limit is not None:
            matched = matched[: self._limit]
        data: Any = [copy.deepcopy(row) for row in matched]
        if self._single:
            data = data[0] if data else None
        return SimpleNamespace(data=data, count=total)


class FakeRpc:
    def __init__(self, db: FakeDB, name: str, params: dict[str, Any]) -> None:
        self.db, self.name, self.params = db, name, params

    def execute(self) -> Any:
        self.db.rpc_calls.append((self.name, self.params))
        handler = self.db.rpc_handlers.get(self.name)
        return SimpleNamespace(data=handler(self.params) if handler else None)


class FakeDB:
    def __init__(self, tables: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            name: [dict(row) for row in rows] for name, rows in (tables or {}).items()
        }
        self.tables.setdefault("care_teams", standard_links())
        self.queries: list[tuple[str, str, list[tuple[str, str, Any]]]] = []
        self.rpc_calls: list[tuple[str, dict[str, Any]]] = []
        self.rpc_handlers: dict[str, Callable[[dict[str, Any]], Any]] = {}

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)

    def rpc(self, name: str, params: dict[str, Any] | None = None) -> FakeRpc:
        return FakeRpc(self, name, params or {})

    def reads_of(self, table: str) -> list[list[tuple[str, str, Any]]]:
        return [
            filters for name, kind, filters in self.queries if name == table and kind == "select"
        ]
