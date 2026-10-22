"""Today and Nora's context merge every approved care plan (PLAN-002). Synthetic data only."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.adk.agents.care_coordinator.prompts import CARE_COORDINATOR_INSTRUCTION
from app.services.chat_service import ChatService
from app.services.feed_service import FeedService
from tests.unit.services.care_team_fake_db import (
    CLINIC,
    CLINICIAN,
    OTHER,
    OTHER_CLINIC,
    OTHER_TEAM,
    PATIENT,
    SECOND_PATIENT,
    TEAM,
    FakeDB,
)

DAY = date(2026, 10, 21)
CARDIO_PLAN = str(uuid4())
ORTHO_PLAN = str(uuid4())
OLD_PLAN = str(uuid4())
DRAFT_PLAN = str(uuid4())


def _db() -> FakeDB:
    """Cardiology (owned), orthopaedics (owned), and a plan whose team ended (unowned)."""
    db = FakeDB(
        {
            "patients": [{"id": PATIENT, "timezone": "UTC", "preferred_language": "en-US"}],
            "clinicians": [
                {
                    "id": CLINICIAN,
                    "first_name": "Elena",
                    "last_name": "Park",
                    "specialty": "Cardiology",
                },
                {
                    "id": OTHER,
                    "first_name": "Sam",
                    "last_name": "Ortiz",
                    "specialty": "Orthopaedics",
                },
            ],
            "clinics": [
                {"id": CLINIC, "display_name": "Cedar Grove"},
                {"id": OTHER_CLINIC, "display_name": "Harbor Bone"},
            ],
            "care_plans": [
                {
                    "id": CARDIO_PLAN,
                    "patient_id": PATIENT,
                    "care_team_id": TEAM,
                    "ownership_state": "owned",
                    "owner_snapshot": {},
                },
                {
                    "id": ORTHO_PLAN,
                    "patient_id": PATIENT,
                    "care_team_id": OTHER_TEAM,
                    "ownership_state": "owned",
                    "owner_snapshot": {},
                },
                {
                    "id": OLD_PLAN,
                    "patient_id": PATIENT,
                    "care_team_id": None,
                    "ownership_state": "unowned",
                    "owner_snapshot": {
                        "clinician_name": "Ana Reyes",
                        "specialty": "ENT",
                        "clinic_name": "Old Clinic",
                        "clinic_id": str(uuid4()),
                    },
                },
                {
                    "id": DRAFT_PLAN,
                    "patient_id": PATIENT,
                    "care_team_id": TEAM,
                    "ownership_state": "owned",
                    "owner_snapshot": {},
                },
                {
                    "id": str(uuid4()),
                    "patient_id": SECOND_PATIENT,
                    "care_team_id": TEAM,
                    "ownership_state": "owned",
                    "owner_snapshot": {},
                },
            ],
        }
    )
    db.tables["care_plan_versions"] = []
    db.tables["care_plan_items"] = []
    db.tables["medications"] = []
    db.tables["obligations"] = []
    return db


def _approved(
    db: FakeDB,
    plan: str,
    name: str,
    *,
    status: str = "approved",
    patient: str = PATIENT,
    active: bool = True,
    removed: bool = False,
) -> dict[str, str]:
    version_id, item_id, med_id = str(uuid4()), str(uuid4()), str(uuid4())
    db.tables["care_plan_versions"].append(
        {
            "id": version_id,
            "patient_id": patient,
            "care_plan_id": plan,
            "version_number": 1,
            "status": status,
        }
    )
    db.tables["care_plan_items"].append(
        {
            "id": item_id,
            "plan_version_id": version_id,
            "category": "medication",
            "schedule": {},
            "is_removed": removed,
        }
    )
    db.tables["medications"].append(
        {
            "id": med_id,
            "patient_id": patient,
            "name": name,
            "dosage": "10 mg",
            "frequency": "daily",
            "instructions": None,
            "care_plan_item_id": item_id,
            "is_active": active,
        }
    )
    return {"med": med_id, "item": item_id}


def _feed(db: FakeDB, **kwargs: Any) -> dict[str, Any]:
    return asyncio.run(
        FeedService(db).get_today(UUID(PATIENT), DAY, "UTC", **kwargs)  # type: ignore[arg-type]
    )


def _owners(feed: dict[str, Any]) -> dict[str, dict[str, Any] | None]:
    return {t["name"].split()[0]: t["plan_owner"] for t in feed["tasks"]}


def test_two_approved_plans_merge_with_their_owners() -> None:
    db = _db()
    cardio = _approved(db, CARDIO_PLAN, "Atenolol")
    _approved(db, ORTHO_PLAN, "Meloxicam")
    feed = _feed(db)
    owners = _owners(feed)
    assert owners["Atenolol"] == {
        "care_plan_id": CARDIO_PLAN,
        "care_team_id": TEAM,
        "ownership_state": "owned",
        "specialty": "Cardiology",
        "clinician_name": "Elena Park",
        "clinic_id": CLINIC,
        "clinic_name": "Cedar Grove",
        "unowned_notice": False,
    }
    assert owners["Meloxicam"]["clinic_name"] == "Harbor Bone"
    assert owners["Meloxicam"]["care_team_id"] == OTHER_TEAM
    # activity ids stay the existing medication ids
    assert {t["target_id"] for t in feed["tasks"]} >= {cardio["med"]}
    assert feed["tasks"][0]["id"].startswith("medication:")
    assert feed["summary"]["total"] == 2
    assert {f["care_team_id"]: f["count"] for f in feed["care_team_filters"]} == {
        TEAM: 1,
        OTHER_TEAM: 1,
    }
    assert feed["contact_clinic"] is False


def test_unowned_plan_uses_snapshot_and_is_filterable() -> None:
    db = _db()
    _approved(db, CARDIO_PLAN, "Atenolol")
    _approved(db, OLD_PLAN, "Cetirizine")
    feed = _feed(db)
    old = _owners(feed)["Cetirizine"]
    assert old["care_team_id"] is None and old["ownership_state"] == "unowned"
    assert old["unowned_notice"] is True
    assert (old["clinician_name"], old["specialty"], old["clinic_name"]) == (
        "Ana Reyes",
        "ENT",
        "Old Clinic",
    )
    unowned_filter = [f for f in feed["care_team_filters"] if f["care_team_id"] is None]
    assert unowned_filter == [
        {
            "care_team_id": None,
            "ownership_state": "unowned",
            "specialty": "ENT",
            "clinician_name": "Ana Reyes",
            "clinic_name": "Old Clinic",
            "count": 1,
        }
    ]
    # the patient still has an active team, so no "contact your clinic"
    assert feed["contact_clinic"] is False


def test_filter_by_team_by_unowned_and_unknown() -> None:
    db = _db()
    _approved(db, CARDIO_PLAN, "Atenolol")
    _approved(db, ORTHO_PLAN, "Meloxicam")
    _approved(db, OLD_PLAN, "Cetirizine")
    legacy = {
        "id": str(uuid4()),
        "patient_id": PATIENT,
        "name": "Vitamin",
        "dosage": "1",
        "frequency": "daily",
        "care_plan_item_id": None,
        "is_active": True,
    }
    db.tables["medications"].append(legacy)

    by_team = _feed(db, care_team_filter=TEAM)
    assert [t["name"].split()[0] for t in by_team["tasks"]] == ["Atenolol"]
    assert by_team["summary"]["total"] == 1
    assert len(by_team["care_team_filters"]) == 3  # filters still describe the whole list
    assert [t["name"].split()[0] for t in _feed(db, care_team_filter="unowned")["tasks"]] == [
        "Cetirizine"
    ]
    for unknown in (str(uuid4()), "not-a-uuid", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3"):
        result = _feed(db, care_team_filter=unknown)
        assert result["tasks"] == [] and result["summary"]["total"] == 0
    unfiltered = _feed(db)
    assert len(unfiltered["tasks"]) == 4
    assert _owners(unfiltered)["Vitamin"] is None  # legacy record: no plan owner


def test_contact_clinic_only_without_active_team_and_with_unowned_activity() -> None:
    db = _db()
    _approved(db, OLD_PLAN, "Cetirizine")
    db.tables["care_teams"] = [{**t, "status": "ended"} for t in db.tables["care_teams"]]
    assert _feed(db)["contact_clinic"] is True
    # an owned-plan activity alone never asks to contact the clinic
    db2 = _db()
    _approved(db2, CARDIO_PLAN, "Atenolol")
    db2.tables["care_teams"] = [{**t, "status": "ended"} for t in db2.tables["care_teams"]]
    assert _feed(db2)["contact_clinic"] is False


def test_draft_unapproved_retired_and_other_patient_never_appear() -> None:
    db = _db()
    _approved(db, CARDIO_PLAN, "Atenolol")
    _approved(db, DRAFT_PLAN, "Draftdrug", status="draft")
    _approved(db, ORTHO_PLAN, "Superseded", status="superseded")
    _approved(db, ORTHO_PLAN, "Removed", removed=True)
    _approved(db, ORTHO_PLAN, "Inactive", active=False)
    retired = _approved(db, ORTHO_PLAN, "Retired")
    db.tables["care_plan_item_retirements"] = [{"item_id": retired["item"]}]
    _approved(db, CARDIO_PLAN, "Stranger", patient=SECOND_PATIENT)
    feed = _feed(db)
    assert [t["name"].split()[0] for t in feed["tasks"]] == ["Atenolol"]


def test_response_model_accepts_new_fields() -> None:
    from app.models.feed import TodayFeedResponse

    db = _db()
    _approved(db, OLD_PLAN, "Cetirizine")
    parsed = TodayFeedResponse.model_validate(_feed(db))
    assert parsed.tasks[0].plan_owner is not None
    assert parsed.tasks[0].plan_owner.unowned_notice is True
    assert parsed.care_team_filters[0].care_team_id is None


def _context(db: FakeDB) -> dict[str, Any]:
    return asyncio.run(ChatService(db).get_context(PATIENT, include_schedule=True))  # type: ignore[arg-type]


def test_nora_context_carries_plan_provenance_for_each_plan() -> None:
    db = _db()
    _approved(db, CARDIO_PLAN, "Atenolol")
    _approved(db, OLD_PLAN, "Cetirizine")
    context = _context(db)
    meds = {m["name"]: m for m in context["medications"]}
    assert meds["Atenolol"]["plan"] == {
        "care_plan_id": CARDIO_PLAN,
        "specialty": "Cardiology",
        "clinician_name": "Elena Park",
        "clinic_name": "Cedar Grove",
        "ownership_state": "owned",
    }
    assert meds["Cetirizine"]["plan"]["ownership_state"] == "unowned"
    assert meds["Cetirizine"]["plan"]["clinician_name"] == "Ana Reyes"
    assert "care_plan_item_id" not in meds["Atenolol"]
    activities = {a["name"].split()[0]: a for a in context["todays_plan_activities"]}
    assert activities["Atenolol"]["plan"]["care_plan_id"] == CARDIO_PLAN
    assert activities["Cetirizine"]["plan"]["ownership_state"] == "unowned"
    assert {p["care_plan_id"] for p in context["care_plans"]} == {CARDIO_PLAN, OLD_PLAN}


def test_nora_context_without_schedule_stays_light_and_plan_free() -> None:
    db = _db()
    _approved(db, CARDIO_PLAN, "Atenolol")
    context = asyncio.run(ChatService(db).get_context(PATIENT))  # type: ignore[arg-type]
    assert "care_plans" not in context and "plan" not in context["medications"][0]


def test_prompt_tells_nora_to_cite_plan_and_unowned_prescriber() -> None:
    assert "ownership_state" in CARE_COORDINATOR_INSTRUCTION
    assert "ask their care team before changing it" in CARE_COORDINATOR_INSTRUCTION


@pytest.mark.parametrize("state", ["unowned", "unassigned_legacy"])
def test_unowned_notice_true_for_both_ownerless_states(state: str) -> None:
    db = _db()
    for plan in db.tables["care_plans"]:
        if plan["id"] == OLD_PLAN:
            plan["ownership_state"] = state
    _approved(db, OLD_PLAN, "Cetirizine")
    assert _owners(_feed(db))["Cetirizine"]["unowned_notice"] is True
