"""Integration tests for canonical-fixture mapping through a Supabase-like transport."""

from __future__ import annotations

from collections import defaultdict
from types import SimpleNamespace
from typing import Any

import pytest
from scripts import seed_demo_environment as seed_adapter

from app.db.seed.demo_data import load_canonical_fixture


class InMemoryQuery:
    def __init__(self, client: InMemorySupabase, table: str) -> None:
        self.client = client
        self.table_name = table
        self.filters: dict[str, Any] = {}
        self._insert: dict[str, Any] | None = None
        self._update: dict[str, Any] | None = None
        self._delete = False
        self._in_filter: tuple[str, list[str]] | None = None

    def select(self, _columns: str) -> InMemoryQuery:
        return self

    def eq(self, column: str, value: Any) -> InMemoryQuery:
        self.filters[column] = value
        return self

    def limit(self, _value: int) -> InMemoryQuery:
        return self

    def insert(self, payload: dict[str, Any]) -> InMemoryQuery:
        self._insert = dict(payload)
        return self

    def update(self, payload: dict[str, Any]) -> InMemoryQuery:
        self._update = dict(payload)
        return self

    def delete(self) -> InMemoryQuery:
        self._delete = True
        return self

    def in_(self, column: str, values: list[str]) -> InMemoryQuery:
        self._in_filter = (column, values)
        return self

    def execute(self) -> SimpleNamespace:
        rows = self.client.rows[self.table_name]
        matching = [
            row
            for row in rows
            if all(str(row.get(key)) == str(value) for key, value in self.filters.items())
        ]
        if self._insert is not None:
            payload = {
                **self._insert,
                "id": self._insert.get("id") or self.client.next_id(self.table_name),
            }
            rows.append(payload)
            return SimpleNamespace(data=[payload])
        if self._update is not None:
            for row in matching:
                row.update(self._update)
            return SimpleNamespace(data=matching)
        if self._delete:
            if self._in_filter is not None:
                column, values = self._in_filter
                self.client.rows[self.table_name] = [
                    row for row in rows if row.get(column) not in values
                ]
            return SimpleNamespace(data=[])
        return SimpleNamespace(data=matching)


class InMemoryAdmin:
    def __init__(self) -> None:
        self.users: list[SimpleNamespace] = []

    def create_user(self, payload: dict[str, Any]) -> SimpleNamespace:
        user = SimpleNamespace(id=f"auth-{len(self.users) + 1}", email=payload["email"])
        self.users.append(user)
        return SimpleNamespace(user=user)

    def list_users(self, *, page: int, per_page: int) -> list[SimpleNamespace]:
        start = (page - 1) * per_page
        return self.users[start : start + per_page]

    def delete_user(self, user_id: str) -> None:
        self.users = [user for user in self.users if user.id != user_id]


class InMemorySupabase:
    def __init__(self) -> None:
        self.rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.auth = SimpleNamespace(admin=InMemoryAdmin())

    def next_id(self, table: str) -> str:
        return f"{table}-{len(self.rows[table]) + 1}"

    def table(self, table: str) -> InMemoryQuery:
        return InMemoryQuery(self, table)


def test_seed_maps_each_source_scenario_to_distinct_supported_rows() -> None:
    fixture = load_canonical_fixture()
    client = InMemorySupabase()

    seed_adapter.seed(client, "synthetic-password")

    patients_by_email = {row["email"]: row for row in client.rows["patients"]}
    staff_by_email = {row["email"]: row for row in client.rows["clinicians"]}
    assert len(patients_by_email) == 8
    assert [row["preferred_language"] for row in patients_by_email.values()].count("en-US") == 5
    assert [row["preferred_language"] for row in patients_by_email.values()].count("es-MX") == 3
    assert all(row["gender"] is None for row in patients_by_email.values())

    for scenario in fixture.patients:
        patient_id = patients_by_email[seed_adapter.fixture_email(scenario.source_id)]["id"]
        assert {
            row["name"] for row in client.rows["conditions"] if row["patient_id"] == patient_id
        } == {condition.label for condition in scenario.conditions}
        assert {
            (row["name"], row["dosage"], row["route"], row["is_active"])
            for row in client.rows["medications"]
            if row["patient_id"] == patient_id
        } == {
            (
                medication.label,
                medication.dose_text,
                seed_adapter.ROUTE_MAP[medication.route],
                medication.status == "active",
            )
            for medication in scenario.medications
        }
        assert {
            row["ai_summary"] for row in client.rows["documents"] if row["patient_id"] == patient_id
        } == {document.title for document in scenario.documents}
        assert {
            row["clinician_id"]
            for row in client.rows["care_teams"]
            if row["patient_id"] == patient_id
        } == {
            staff_by_email[seed_adapter.fixture_email(assignment.staff_source_id)]["id"]
            for assignment in fixture.care_team_assignments
            if assignment.patient_source_id == scenario.source_id
            and assignment.grants_record_access
            and assignment.staff_source_id in {staff.source_id for staff in fixture.staff}
        }


def test_seed_maps_only_source_supported_event_types_without_inventing_rows() -> None:
    fixture = load_canonical_fixture()
    client = InMemorySupabase()

    seed_adapter.seed(client, "synthetic-password")

    expected_portal_concerns = {
        event.summary
        for scenario in fixture.patients
        for event in scenario.timeline_events
        if event.source_id in seed_adapter.PORTAL_CONCERN_EVENT_IDS
    }
    expected_appointments = {
        event.summary
        for scenario in fixture.patients
        for event in scenario.timeline_events
        if event.event_type == "appointment_scheduled"
    }
    expected_portal_notifications = {
        event.summary
        for scenario in fixture.patients
        for event in scenario.timeline_events
        if event.event_type == "notification_sent" and event.channel == "portal_message"
    }

    assert {row["content"] for row in client.rows["chat_messages"]} == expected_portal_concerns
    assert len(client.rows["chat_messages"]) == 5
    unsupported_concerns = {
        event.summary
        for scenario in fixture.patients
        for event in scenario.timeline_events
        if event.source_id in {"SYN-EVT-002-06", "SYN-EVT-004-02", "SYN-EVT-008-05"}
    }
    assert unsupported_concerns.isdisjoint({row["content"] for row in client.rows["chat_messages"]})
    assert {row["reason"] for row in client.rows["appointments"]} == expected_appointments
    assert {row["body"] for row in client.rows["notifications"]} == expected_portal_notifications
    assert not client.rows["obligations"]
    assert not client.rows["adherence_logs"]
    assert not client.rows["symptom_reports"]


def test_reseeding_is_idempotent_for_all_persisted_rows() -> None:
    client = InMemorySupabase()

    seed_adapter.seed(client, "synthetic-password")
    first_counts = {table: len(rows) for table, rows in client.rows.items()}
    seed_adapter.seed(client, "synthetic-password")

    assert {table: len(rows) for table, rows in client.rows.items()} == first_counts


def test_reset_deletes_only_exact_canonical_fixture_users(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "staging")
    fixture = load_canonical_fixture()
    client = InMemorySupabase()
    client.auth.admin.users = [
        SimpleNamespace(
            id="fixture", email=seed_adapter.fixture_email(fixture.patients[0].source_id)
        ),
        SimpleNamespace(id="unrelated", email="other@demo.mediagent.local"),
    ]

    seed_adapter.reset(client)

    assert [user.id for user in client.auth.admin.users] == ["unrelated"]


def test_schema_preflight_rejects_unsynchronized_ledger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed_adapter, "_expected_migration_checksums", lambda: {"020.sql": "abc"})
    client = InMemorySupabase()

    with pytest.raises(RuntimeError, match="020.sql"):
        seed_adapter.assert_schema_ready(client)
