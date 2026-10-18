"""An in-memory stand-in for the Supabase client used by the MedWatch service tests.

Tables are lists of dicts; the RPCs follow migrations 048 and 064 closely enough for the
service's save, load, approve, export, discard and submission paths. Synthetic data only.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from postgrest.exceptions import APIError

CLINICIAN_ID = "55555555-5555-4555-8555-555555555555"
OTHER_CLINICIAN_ID = "99999999-9999-4999-8999-999999999999"
PATIENT_ID = "11111111-1111-4111-8111-111111111111"
CLINIC_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
APPROVED_AT = "2026-10-12T18:00:00+00:00"


def api_error(code: str) -> APIError:
    return APIError(
        {"message": "Synthetic database detail", "code": code, "hint": None, "details": "SECRET"}
    )


class FakeQuery:
    def __init__(self, db: FakeDB, table: str) -> None:
        self.db = db
        self.table = table
        self.filters: list[Callable[[dict[str, Any]], bool]] = []
        self.negate = False
        self.sort: tuple[str, bool] | None = None
        self.count: int | None = None

    def select(self, *_args: Any, **_kwargs: Any) -> FakeQuery:
        return self

    def eq(self, column: str, value: Any) -> FakeQuery:
        self.filters.append(lambda row: str(row.get(column)) == str(value))
        return self

    def in_(self, column: str, values: list[Any]) -> FakeQuery:
        allowed = {str(value) for value in values}
        self.filters.append(lambda row: str(row.get(column)) in allowed)
        return self

    @property
    def not_(self) -> FakeQuery:
        self.negate = True
        return self

    def is_(self, column: str, value: str) -> FakeQuery:
        assert value == "null"
        negate, self.negate = self.negate, False
        self.filters.append(lambda row: (row.get(column) is None) != negate)
        return self

    def order(self, column: str, desc: bool = False) -> FakeQuery:
        self.sort = (column, desc)
        return self

    def limit(self, count: int) -> FakeQuery:
        self.count = count
        return self

    def execute(self) -> Any:
        self.db.queries.append(self.table)
        rows = [
            copy.deepcopy(row)
            for row in self.db.tables.get(self.table, [])
            if all(check(row) for check in self.filters)
        ]
        if self.sort:
            column, desc = self.sort
            rows.sort(key=lambda row: str(row.get(column)), reverse=desc)
        if self.count is not None:
            rows = rows[: self.count]
        return SimpleNamespace(data=rows)


class FakeRpc:
    def __init__(self, db: FakeDB, name: str, params: dict[str, Any]) -> None:
        self.db, self.name, self.params = db, name, params

    def execute(self) -> Any:
        self.db.rpc_calls.append((self.name, copy.deepcopy(self.params)))
        if self.name in self.db.errors:
            raise self.db.errors[self.name]
        handler = getattr(self.db, "_" + self.name)
        return SimpleNamespace(data=[copy.deepcopy(handler(self.params))])


@dataclass
class FakeDB:
    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    rpc_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    errors: dict[str, Exception] = field(default_factory=dict)
    queries: list[str] = field(default_factory=list)
    clock: int = 0

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)

    def rpc(self, name: str, params: dict[str, Any]) -> FakeRpc:
        return FakeRpc(self, name, params)

    # Helpers

    def now(self) -> str:
        self.clock += 1
        return f"2026-10-13T17:00:{self.clock:02d}+00:00"

    def draft(self, draft_id: str) -> dict[str, Any]:
        return next(row for row in self.tables["medwatch_drafts"] if row["id"] == draft_id)

    def audit(self, draft_id: str, event_type: str, data: dict[str, Any]) -> None:
        self.tables.setdefault("medwatch_draft_audit_events", []).append(
            {"medwatch_draft_id": draft_id, "event_type": event_type, "event_data": data}
        )

    def _revision(self, row: dict[str, Any], expected: int) -> None:
        if row["revision"] != expected:
            raise api_error("40001")

    # RPCs (048 and 064)

    def _create_medwatch_draft(self, p: dict[str, Any]) -> dict[str, Any]:
        assessment = next(
            row for row in self.tables["adr_assessments"] if row["id"] == p["p_assessment_id"]
        )
        now = self.now()
        row = {
            "id": p["p_draft_id"],
            "adr_assessment_id": p["p_assessment_id"],
            "patient_id": assessment["patient_id"],
            "form_data": p["p_form_data"],
            "source_evidence": p["p_source_evidence"],
            "clinician_edited_fields": [],
            "de_identified": False,
            "status": "draft",
            "patient_reference": p["p_form_data"]["section_a"]["identifier"],
            "created_by": p["p_actor_id"],
            "approved_by": None,
            "approved_at": None,
            "approval_note": None,
            "submitted_at": None,
            "discarded_at": None,
            "discarded_by": None,
            "discard_reason": None,
            "revision": 1,
            "export_version": "fda-3500-2025-09",
            "created_at": now,
            "updated_at": now,
        }
        self.tables.setdefault("medwatch_drafts", []).append(row)
        assessment["status"] = "reviewed"
        self.audit(row["id"], "created", {"revision": 1})
        return row

    def _update_medwatch_draft(self, p: dict[str, Any]) -> dict[str, Any]:
        row = self.draft(p["p_draft_id"])
        if row["status"] != "draft" or row["discarded_at"]:
            raise api_error("23514")
        self._revision(row, p["p_expected_revision"])
        row["form_data"] = p["p_form_data"]
        row["export_version"] = (
            "fda-3500-2025-09"
            if p["p_form_data"].get("form_version") == "fda-3500-2025-09"
            else "fda-3500-legacy-048"
        )
        row["clinician_edited_fields"] = sorted(
            set(row["clinician_edited_fields"]) | set(p["p_changed_fields"])
        )
        row["revision"] += 1
        self.audit(row["id"], "edited", {"changed_fields": p["p_changed_fields"]})
        return row

    def _approve_medwatch_draft(self, p: dict[str, Any]) -> dict[str, Any]:
        row = self.draft(p["p_draft_id"])
        if row["status"] != "draft" or row["discarded_at"]:
            raise api_error("23514")
        self._revision(row, p["p_expected_revision"])
        section_b = row["form_data"].get("section_b") or {}
        if not section_b.get("report_date"):
            section_b["report_date"] = "2026-10-12"
        row.update(
            status="reviewed",
            approved_by=p["p_actor_id"],
            approved_at=APPROVED_AT,
            approval_note=p["p_approval_note"],
        )
        row["revision"] += 1
        self.audit(row["id"], "approved", dict(p["p_approval"]))
        return row

    def _record_medwatch_draft_export(self, p: dict[str, Any]) -> dict[str, Any]:
        row = self.draft(p["p_draft_id"])
        self.audit(row["id"], "exported", {"format": p.get("p_format", "json")})
        return row

    def _record_medwatch_draft_preview_viewed(self, p: dict[str, Any]) -> dict[str, Any]:
        row = self.draft(p["p_draft_id"])
        self.audit(row["id"], "preview_viewed", {"actor_id": p["p_actor_id"]})
        return row

    def _discard_medwatch_draft(self, p: dict[str, Any]) -> dict[str, Any]:
        row = self.draft(p["p_draft_id"])
        self._revision(row, p["p_expected_revision"])
        row.update(
            discarded_at=self.now(),
            discarded_by=p["p_actor_id"],
            discard_reason=p["p_reason"],
        )
        row["revision"] += 1
        self.audit(row["id"], "discarded", {"reason": p["p_reason"]})
        return row

    def _submission(self, p: dict[str, Any], **extra: Any) -> dict[str, Any]:
        row = self.draft(p["p_draft_id"])
        submission = {
            "id": str(uuid4()),
            "medwatch_draft_id": row["id"],
            "recorded_by": p["p_actor_id"],
            "submitted_on": date.fromisoformat(p["p_submitted_on"]).isoformat(),
            "method": p["p_method"],
            "method_detail": p["p_method_detail"],
            "fda_reference": p["p_fda_reference"],
            "amends_id": None,
            "amend_reason": None,
            "created_at": self.now(),
            **extra,
        }
        self.tables.setdefault("medwatch_external_submissions", []).append(submission)
        return submission

    def _record_medwatch_external_submission(self, p: dict[str, Any]) -> dict[str, Any]:
        row = self.draft(p["p_draft_id"])
        self._revision(row, p["p_expected_revision"])
        self._submission(p)
        row.update(status="submitted", submitted_at=self.now())
        row["revision"] += 1
        self.audit(row["id"], "submission_recorded", {})
        return row

    def _amend_medwatch_external_submission(self, p: dict[str, Any]) -> dict[str, Any]:
        row = self.draft(p["p_draft_id"])
        history = [
            item
            for item in self.tables.get("medwatch_external_submissions", [])
            if item["medwatch_draft_id"] == row["id"]
        ]
        amended = {item["amends_id"] for item in history}
        current = [item for item in history if item["id"] not in amended]
        if not current or current[-1]["id"] != p["p_amends_id"]:
            raise api_error("40001")
        self._submission(p, amends_id=p["p_amends_id"], amend_reason=p["p_reason"])
        self.audit(row["id"], "submission_amended", {})
        return row


def seeded(**tables: list[dict[str, Any]]) -> FakeDB:
    """A database with one synthetic patient, an assigned clinician and their clinic."""
    base: dict[str, list[dict[str, Any]]] = {
        "patients": [
            {
                "id": PATIENT_ID,
                "first_name": "Lucía",
                "last_name": "Ramírez",
                "email": "lucia.ramirez@example.test",
                "date_of_birth": "1961-07-14",
                "gender": "female",
            }
        ],
        "care_teams": [
            {
                "id": "team-1",
                "patient_id": PATIENT_ID,
                "clinician_id": CLINICIAN_ID,
                "clinic_id": CLINIC_ID,
                "clinic_name": None,
                "status": "active",
            }
        ],
        "clinicians": [
            {
                "id": CLINICIAN_ID,
                "first_name": "Elena",
                "last_name": "Park",
                "email": "elena.park@example.test",
                "specialty": "Internal medicine",
                "clinic_name": "Synthetic Valley Clinic",
                "clinic_id": CLINIC_ID,
            },
            {
                "id": OTHER_CLINICIAN_ID,
                "first_name": "Omar",
                "last_name": "Synthetic",
                "email": "omar@example.test",
                "clinic_name": "Elsewhere Clinic",
            },
        ],
        "clinics": [{"id": CLINIC_ID, "display_name": "Synthetic Valley Health"}],
    }
    for name, rows in tables.items():
        base.setdefault(name, []).extend(rows)
    return FakeDB(tables=base)
