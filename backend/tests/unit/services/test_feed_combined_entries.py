"""Identical activities of different plans show as one Today entry (PLAN-002)."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

from app.services.adherence_service import AdherenceService
from tests.unit.services.care_team_fake_db import OTHER_TEAM, PATIENT, TEAM, FakeDB
from tests.unit.services.test_feed_multi_plan import (
    CARDIO_PLAN,
    OLD_PLAN,
    ORTHO_PLAN,
    _db,
    _feed,
)

SCHEDULED = "2026-10-21T08:00:00+00:00"


def _add(
    db: FakeDB,
    plan: str,
    *,
    created: str,
    dose: str = "10 mg",
    instructions: str = "With food",
    name: str = "Ibuprofen",
    rxcui: str | None = "5640",
    schedule: dict[str, Any] | None = None,
    retired: bool = False,
    kind: str = "medication",
) -> dict[str, str]:
    version_id, item_id, row_id = str(uuid4()), str(uuid4()), str(uuid4())
    db.tables["care_plan_versions"].append(
        {
            "id": version_id,
            "patient_id": PATIENT,
            "care_plan_id": plan,
            "version_number": 1,
            "status": "approved",
        }
    )
    db.tables["care_plan_items"].append(
        {
            "id": item_id,
            "plan_version_id": version_id,
            "category": "medication" if kind == "medication" else "lifestyle",
            "schedule": schedule or {},
            "is_removed": False,
            "instructions": instructions,
            "frequency": "daily",
            "medication": {
                "name": name,
                "dosage": dose,
                "frequency": "daily",
                "route": "oral",
                "ingredient_rxcui": rxcui,
            }
            if kind == "medication"
            else None,
        }
    )
    if kind == "medication":
        db.tables["medications"].append(
            {
                "id": row_id,
                "patient_id": PATIENT,
                "name": name,
                "dosage": dose,
                "frequency": "daily",
                "instructions": instructions,
                "route": "oral",
                "care_plan_item_id": item_id,
                "created_at": created,
                "is_active": not retired,
            }
        )
    else:
        db.tables["obligations"].append(
            {
                "id": row_id,
                "patient_id": PATIENT,
                "description": name,
                "notes": instructions,
                "frequency": "daily",
                "care_plan_item_id": item_id,
                "created_at": created,
                "is_active": not retired,
            }
        )
    return {"id": row_id, "item": item_id}


def test_identical_duplicate_is_one_entry_with_two_owners() -> None:
    db = _db()
    first = _add(db, CARDIO_PLAN, created="2026-01-01")
    second = _add(db, ORTHO_PLAN, created="2026-02-01", name="IBUPROFEN ", rxcui=None)
    feed = _feed(db)
    assert len(feed["tasks"]) == 1 and feed["summary"]["total"] == 1
    task = feed["tasks"][0]
    assert task["target_id"] == first["id"]  # oldest is the entry
    assert task["combined_item_ids"] == [first["id"], second["id"]]
    assert [o["care_team_id"] for o in task["plan_owners"]] == [TEAM, OTHER_TEAM]
    assert task["plan_owner"] == task["plan_owners"][0]
    counts = {f["care_team_id"]: f["count"] for f in feed["care_team_filters"]}
    assert counts == {TEAM: 1, OTHER_TEAM: 1}


def test_one_reminder_per_entry_falls_back_to_the_first_member_that_has_one() -> None:
    from app.services.feed_service import FeedService

    db = _db()
    first = _add(db, CARDIO_PLAN, created="2026-01-01")
    second = _add(db, ORTHO_PLAN, created="2026-02-01")
    svc = FeedService(db)  # type: ignore[arg-type]
    meds = asyncio.run(svc._get_medications(UUID(PATIENT)))
    items = asyncio.run(svc._get_approved_plan_items(UUID(PATIENT)))
    schedule = {"times": ["08:00"]}
    groups, shown, _obls, reminders, _logs = svc._combine_identical(
        meds, [], items, {("medication", second["id"]): schedule}, []
    )
    assert [m["id"] for m in shown] == [first["id"]]
    assert reminders == {("medication", first["id"]): schedule}
    assert [m["id"] for m in groups[("medication", first["id"])]] == [first["id"], second["id"]]


def test_differing_dose_instructions_or_schedule_never_combine() -> None:
    for change in (
        {"dose": "20 mg"},
        {"instructions": "Empty stomach"},
        {"schedule": {"start_date": "2026-10-01"}},
        {"name": "Naproxen", "rxcui": "7258"},
    ):
        db = _db()
        _add(db, CARDIO_PLAN, created="2026-01-01")
        _add(db, ORTHO_PLAN, created="2026-02-01", **change)
        feed = _feed(db)
        assert len(feed["tasks"]) == 2, change
        assert all(len(t["combined_item_ids"]) == 1 for t in feed["tasks"])


def test_retiring_one_side_leaves_the_other_owner_with_its_history() -> None:
    db = _db()
    first = _add(db, CARDIO_PLAN, created="2026-01-01")
    _add(db, ORTHO_PLAN, created="2026-02-01", retired=True)
    task = _feed(db)["tasks"][0]
    assert task["target_id"] == first["id"] and len(_feed(db)["tasks"]) == 1
    assert [o["care_team_id"] for o in task["plan_owners"]] == [TEAM]
    assert task["combined_item_ids"] == [first["id"]]
    # the older side retires: the entry falls back to the remaining item
    db2 = _db()
    _add(db2, CARDIO_PLAN, created="2026-01-01", retired=True)
    remaining = _add(db2, ORTHO_PLAN, created="2026-02-01")
    task2 = _feed(db2)["tasks"][0]
    assert task2["target_id"] == remaining["id"]
    assert task2["plan_owner"]["care_team_id"] == OTHER_TEAM


def test_unowned_side_combines_with_owned_side_and_filter_keeps_the_group() -> None:
    db = _db()
    _add(db, OLD_PLAN, created="2026-01-01")
    _add(db, CARDIO_PLAN, created="2026-02-01")
    feed = _feed(db)
    task = feed["tasks"][0]
    assert len(feed["tasks"]) == 1
    assert [o["ownership_state"] for o in task["plan_owners"]] == ["unowned", "owned"]
    assert task["plan_owners"][0]["unowned_notice"] is True
    assert len(_feed(db, care_team_filter=TEAM)["tasks"]) == 1
    assert len(_feed(db, care_team_filter="unowned")["tasks"]) == 1
    assert _feed(db, care_team_filter=OTHER_TEAM)["tasks"] == []


def test_non_medication_combines_only_when_identical() -> None:
    db = _db()
    _add(db, CARDIO_PLAN, created="2026-01-01", name="Walk 20 minutes", kind="obligation")
    _add(db, ORTHO_PLAN, created="2026-02-01", name="walk  20 minutes", kind="obligation")
    _add(db, ORTHO_PLAN, created="2026-02-02", name="Check blood pressure", kind="obligation")
    names = sorted(t["name"] for t in _feed(db)["tasks"])
    assert len(names) == 2


def test_completion_fans_out_to_every_member_and_is_idempotent() -> None:
    db = _db()
    first = _add(db, CARDIO_PLAN, created="2026-01-01")
    second = _add(db, ORTHO_PLAN, created="2026-02-01")
    db.tables["adherence_logs"] = []
    payload = {
        "target_type": "medication",
        "target_id": second["id"],
        "status": "taken",
        "scheduled_time": SCHEDULED,
    }
    service = AdherenceService(db)  # type: ignore[arg-type]
    logged = asyncio.run(service.log_adherence(UUID(PATIENT), dict(payload)))
    assert logged["target_id"] == second["id"]  # response is the requested member's row
    rows = db.tables["adherence_logs"]
    assert sorted(r["target_id"] for r in rows) == sorted([first["id"], second["id"]])
    assert {(r["status"], r["scheduled_time"]) for r in rows} == {("taken", SCHEDULED)}
    asyncio.run(service.log_adherence(UUID(PATIENT), dict(payload)))
    assert len(db.tables["adherence_logs"]) == 2
    for row in db.tables["adherence_logs"]:
        row["logged_at"] = "2026-10-21T08:05:00+00:00"
    # the entry now reads as completed
    assert _feed(db)["tasks"][0]["status"] == "completed"


def test_barrier_fans_out_and_ungrouped_logs_a_single_row() -> None:
    db = _db()
    first = _add(db, CARDIO_PLAN, created="2026-01-01")
    second = _add(db, ORTHO_PLAN, created="2026-02-01")
    lone = _add(db, CARDIO_PLAN, created="2026-03-01", name="Atenolol", rxcui="1202")
    db.tables["adherence_logs"] = []
    service = AdherenceService(db)  # type: ignore[arg-type]
    asyncio.run(
        service.log_adherence(
            UUID(PATIENT),
            {
                "target_type": "medication",
                "target_id": first["id"],
                "status": "skipped",
                "barrier_code": "cost",
            },
        )
    )
    assert {r["target_id"] for r in db.tables["adherence_logs"]} == {first["id"], second["id"]}
    assert {r["barrier_code"] for r in db.tables["adherence_logs"]} == {"cost"}
    asyncio.run(
        service.log_adherence(
            UUID(PATIENT), {"target_type": "medication", "target_id": lone["id"], "status": "taken"}
        )
    )
    assert len(db.tables["adherence_logs"]) == 3
