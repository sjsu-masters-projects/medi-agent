"""Clinician read paths follow care-team ownership (PLAN-002, CLN-003 slice G).

Every test builds one patient with two care teams (cardiology: CLINICIAN, orthopaedics: OTHER)
over the in-memory fake database and asserts what each clinician is shown. Each assertion
fails if the ownership check it names is removed. Synthetic data only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.core.exceptions import AuthorizationError
from app.services.care_plan_activity_scope import ActivityScope, plan_owner_by_target
from app.services.care_team_access import CareTeamAccessService
from app.services.clinic_link_scope import ClinicLinkScope
from app.services.clinician_service import ClinicianService
from app.services.reminder_schedule_service import ReminderScheduleService
from app.services.risk_score_service import RiskScoreService
from tests.unit.services.care_team_fake_db import (
    CLINIC,
    CLINICIAN,
    OTHER,
    OTHER_TEAM,
    PATIENT,
    SECOND_PATIENT,
    TEAM,
    THIRD,
    FakeDB,
)

NOW = datetime.now(UTC)
ITEM_MINE, ITEM_THEIRS = (
    "bbbbbbbb-0000-4000-8000-000000000001",
    "bbbbbbbb-0000-4000-8000-000000000002",
)
VERSION_MINE, VERSION_THEIRS = (
    "cccccccc-0000-4000-8000-000000000001",
    "cccccccc-0000-4000-8000-000000000002",
)
PLAN_MINE, PLAN_THEIRS = (
    "dddddddd-0000-4000-8000-000000000001",
    "dddddddd-0000-4000-8000-000000000002",
)
PLAN_UNOWNED_ITEM = "bbbbbbbb-0000-4000-8000-000000000003"
VERSION_UNOWNED = "cccccccc-0000-4000-8000-000000000003"
PLAN_UNOWNED = "dddddddd-0000-4000-8000-000000000003"
OB_MINE, OB_THEIRS, OB_FREE, OB_UNOWNED = (
    f"eeeeeeee-0000-4000-8000-00000000000{i}" for i in range(1, 5)
)
MED_THEIRS = "ffffffff-0000-4000-8000-000000000001"


def plan_tables() -> dict[str, list[dict[str, Any]]]:
    """Two owned plans (one per team), one unowned plan; activities hang off their items."""
    return {
        "care_plans": [
            {
                "id": PLAN_MINE,
                "patient_id": PATIENT,
                "care_team_id": TEAM,
                "ownership_state": "owned",
            },
            {
                "id": PLAN_THEIRS,
                "patient_id": PATIENT,
                "care_team_id": OTHER_TEAM,
                "ownership_state": "owned",
            },
            {
                "id": PLAN_UNOWNED,
                "patient_id": PATIENT,
                "care_team_id": None,
                "ownership_state": "unowned",
            },
        ],
        "care_plan_versions": [
            {"id": VERSION_MINE, "care_plan_id": PLAN_MINE, "patient_id": PATIENT},
            {"id": VERSION_THEIRS, "care_plan_id": PLAN_THEIRS, "patient_id": PATIENT},
            {"id": VERSION_UNOWNED, "care_plan_id": PLAN_UNOWNED, "patient_id": PATIENT},
        ],
        "care_plan_items": [
            {"id": ITEM_MINE, "plan_version_id": VERSION_MINE},
            {"id": ITEM_THEIRS, "plan_version_id": VERSION_THEIRS},
            {"id": PLAN_UNOWNED_ITEM, "plan_version_id": VERSION_UNOWNED},
        ],
        "obligations": [
            {
                "id": OB_MINE,
                "patient_id": PATIENT,
                "care_plan_item_id": ITEM_MINE,
                "is_active": True,
                "obligation_type": "exercise",
                "description": "Walk",
                "frequency": "daily",
                "created_at": "2026-10-01T00:00:00+00:00",
            },
            {
                "id": OB_THEIRS,
                "patient_id": PATIENT,
                "care_plan_item_id": ITEM_THEIRS,
                "is_active": True,
                "obligation_type": "exercise",
                "description": "Ankle exercises",
                "frequency": "daily",
                "created_at": "2026-10-01T00:00:00+00:00",
            },
            {
                "id": OB_FREE,
                "patient_id": PATIENT,
                "care_plan_item_id": None,
                "is_active": True,
                "obligation_type": "diet",
                "description": "Low salt",
                "frequency": "daily",
                "created_at": "2026-10-01T00:00:00+00:00",
            },
            {
                "id": OB_UNOWNED,
                "patient_id": PATIENT,
                "care_plan_item_id": PLAN_UNOWNED_ITEM,
                "is_active": True,
                "obligation_type": "diet",
                "description": "Fluids",
                "frequency": "daily",
                "created_at": "2026-10-01T00:00:00+00:00",
            },
        ],
        "medications": [
            {
                "id": MED_THEIRS,
                "patient_id": PATIENT,
                "name": "Meloxicam",
                "is_active": True,
                "care_plan_item_id": ITEM_THEIRS,
                "prescribed_by_care_team_id": OTHER_TEAM,
                "recorded_by": {"care_team_id": OTHER_TEAM, "specialty": "Orthopaedics"},
                "created_at": "2026-10-01T00:00:00+00:00",
            },
        ],
    }


def log(target_type: str, target_id: str, status: str, days_ago: int = 1, **extra: Any):
    stamp = (NOW - timedelta(days=days_ago)).isoformat()
    return {
        "id": f"log-{target_id[-3:]}-{status}-{days_ago}-{len(extra)}",
        "patient_id": PATIENT,
        "target_type": target_type,
        "target_id": target_id,
        "status": status,
        "logged_at": stamp,
        **extra,
    }


def service_for(db: FakeDB) -> ClinicianService:
    service = ClinicianService(db=db)  # type: ignore[arg-type]
    service.memberships.link_scope = AsyncMock(  # type: ignore[method-assign]
        return_value=ClinicLinkScope({PATIENT: (CLINIC, "Synthetic clinic")})
    )
    service.document_workflows.fetch_patient_documents = AsyncMock(  # type: ignore[method-assign]
        return_value=[]
    )
    return service


@pytest.fixture(autouse=True)
def no_reminder_schedules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ReminderScheduleService, "get_schedule_map_for_patient", AsyncMock(return_value={})
    )


def summary_for(db: FakeDB) -> None:
    db.rpc_handlers["shared_clinical_summary"] = lambda params: {
        "medications": [],
        "allergies": [],
        "conditions": [],
        "some_conditions_private": False,
        "care_teams": [
            {
                "care_team_id": TEAM,
                "clinician_name": "Elena Park",
                "specialty": "Cardiology",
                "clinic_name": "Valley",
                "is_mine": params["p_clinician_id"] == CLINICIAN,
            },
            {
                "care_team_id": OTHER_TEAM,
                "clinician_name": "Omar Synthetic",
                "specialty": "Orthopaedics",
                "clinic_name": "Elsewhere",
                "is_mine": params["p_clinician_id"] == OTHER,
                "plan": {
                    "care_plan_id": PLAN_THEIRS,
                    "ownership_state": "owned",
                    "approved_at": "2026-10-01T00:00:00+00:00",
                },
            },
        ],
    }


def base_tables(**extra: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    tables: dict[str, list[dict[str, Any]]] = {
        "patients": [
            {
                "id": PATIENT,
                "first_name": "Lucia",
                "last_name": "Synthetic",
                "email": "lucia@example.test",
                "date_of_birth": "1961-07-14",
            }
        ],
        "symptom_reports": [],
        "chat_messages": [],
        "conditions": [],
        "allergies": [],
        "soap_notes": [],
        "adherence_logs": [],
        "adr_assessments": [],
        "medwatch_drafts": [],
        "medications": [],
        "obligations": [],
    }
    tables.update(extra)
    return tables


# ── Activity ownership helper ───────────────────────────────────────────────────────────


def test_plan_owner_by_target_resolves_each_activity_to_its_plans_team() -> None:
    db = FakeDB(plan_tables())
    owners = plan_owner_by_target(
        db,
        PATIENT,  # type: ignore[arg-type]
        [
            ("obligation", OB_MINE),
            ("obligation", OB_THEIRS),
            ("obligation", OB_FREE),
            ("obligation", OB_UNOWNED),
            ("medication", MED_THEIRS),
        ],
    )
    assert owners == {
        OB_MINE: TEAM,
        OB_THEIRS: OTHER_TEAM,
        OB_FREE: None,
        OB_UNOWNED: None,
        MED_THEIRS: OTHER_TEAM,
    }


def test_plan_owner_by_target_ignores_another_patients_activity() -> None:
    db = FakeDB(plan_tables())
    owners = plan_owner_by_target(db, SECOND_PATIENT, [("obligation", OB_THEIRS)])  # type: ignore[arg-type]
    assert owners == {OB_THEIRS: None}


def test_activity_scope_keeps_unowned_and_own_hides_other_teams() -> None:
    db = FakeDB(plan_tables())
    access = CareTeamAccessService(db).for_patient(CLINICIAN, PATIENT)  # type: ignore[arg-type]
    rows = [log("obligation", i, "completed") for i in (OB_MINE, OB_THEIRS, OB_FREE, OB_UNOWNED)]
    rows.append(log("medication", MED_THEIRS, "taken"))
    kept = ActivityScope(db, PATIENT, access).keep(rows)  # type: ignore[arg-type]
    assert {row["target_id"] for row in kept} == {OB_MINE, OB_FREE, OB_UNOWNED}


def test_activity_scope_two_links_see_both_teams_plans() -> None:
    db = FakeDB(plan_tables())
    db.tables["care_teams"].append(
        {
            "id": OTHER_TEAM + "x",
            "patient_id": PATIENT,
            "clinician_id": CLINICIAN,
            "clinic_id": CLINIC,
            "status": "active",
        }
    )
    # CLINICIAN also holds OTHER_TEAM through a second link
    db.tables["care_teams"][1]["clinician_id"] = CLINICIAN
    access = CareTeamAccessService(db).for_patient(CLINICIAN, PATIENT)  # type: ignore[arg-type]
    rows = [log("obligation", OB_MINE, "completed"), log("obligation", OB_THEIRS, "completed")]
    kept = ActivityScope(db, PATIENT, access).keep(rows)  # type: ignore[arg-type]
    assert {row["target_id"] for row in kept} == {OB_MINE, OB_THEIRS}


# ── Deep dive ───────────────────────────────────────────────────────────────────────────


def condition(name: str, sensitive: bool, team: str | None) -> dict[str, Any]:
    return {
        "id": f"cond-{name}",
        "patient_id": PATIENT,
        "name": name,
        "status": "active",
        "is_sensitive": sensitive,
        "recorded_by_care_team_id": team,
    }


@pytest.mark.asyncio
async def test_deep_dive_withholds_another_teams_sensitive_condition_and_says_so() -> None:
    db = FakeDB(
        base_tables(
            conditions=[
                condition("Hypertension", False, OTHER_TEAM),
                condition("Depression", True, OTHER_TEAM),
                condition("Migraine", True, TEAM),
            ]
        )
    )
    summary_for(db)
    result = await service_for(db).get_patient_deep_dive(UUID(CLINICIAN), UUID(PATIENT))
    assert {c["name"] for c in result["conditions"]} == {"Hypertension", "Migraine"}
    assert result["some_conditions_private"] is True
    assert "Depression" not in str(result)


@pytest.mark.asyncio
async def test_deep_dive_reports_no_private_conditions_when_none_are_withheld() -> None:
    db = FakeDB(
        base_tables(
            conditions=[
                condition("Hypertension", False, OTHER_TEAM),
                condition("Migraine", True, TEAM),
            ]
        )
    )
    summary_for(db)
    result = await service_for(db).get_patient_deep_dive(UUID(CLINICIAN), UUID(PATIENT))
    assert result["some_conditions_private"] is False
    assert {c["name"] for c in result["conditions"]} == {"Hypertension", "Migraine"}


@pytest.mark.asyncio
async def test_deep_dive_with_two_links_shows_both_teams_sensitive_conditions() -> None:
    db = FakeDB(
        base_tables(
            conditions=[
                condition("Depression", True, OTHER_TEAM),
                condition("Migraine", True, TEAM),
            ]
        )
    )
    db.tables["care_teams"][1]["clinician_id"] = CLINICIAN
    summary_for(db)
    result = await service_for(db).get_patient_deep_dive(UUID(CLINICIAN), UUID(PATIENT))
    assert {c["name"] for c in result["conditions"]} == {"Depression", "Migraine"}
    assert result["some_conditions_private"] is False


@pytest.mark.asyncio
async def test_deep_dive_lists_other_care_teams_and_keeps_the_recording_team_label() -> None:
    meds = plan_tables()["medications"]
    db = FakeDB(base_tables(medications=meds))
    summary_for(db)
    result = await service_for(db).get_patient_deep_dive(UUID(CLINICIAN), UUID(PATIENT))
    assert [t["specialty"] for t in result["care_teams"]] == ["Cardiology", "Orthopaedics"]
    assert result["care_teams"][1]["plan"]["approved_at"]
    assert "items" not in str(result["care_teams"][1]["plan"])
    assert result["medications"][0]["recorded_by"]["specialty"] == "Orthopaedics"
    assert db.rpc_calls[0] == (
        "shared_clinical_summary",
        {"p_clinician_id": CLINICIAN, "p_patient_id": PATIENT},
    )


@pytest.mark.asyncio
async def test_deep_dive_without_a_link_is_denied_before_any_patient_data() -> None:
    db = FakeDB(base_tables())
    summary_for(db)
    with pytest.raises(AuthorizationError):
        await service_for(db).get_patient_deep_dive(UUID(THIRD), UUID(PATIENT))
    assert db.rpc_calls == []
    assert not any(name == "patients" for name, _, _ in db.queries)


@pytest.mark.asyncio
async def test_deep_dive_asks_for_documents_as_this_clinician() -> None:
    db = FakeDB(base_tables())
    summary_for(db)
    service = service_for(db)
    await service.get_patient_deep_dive(UUID(CLINICIAN), UUID(PATIENT))
    service.document_workflows.fetch_patient_documents.assert_awaited_once_with(  # type: ignore[attr-defined]
        UUID(PATIENT), clinician_id=UUID(CLINICIAN)
    )


@pytest.mark.asyncio
async def test_deep_dive_shows_the_latest_soap_note_of_the_clinicians_own_team() -> None:
    notes = [
        {
            "id": "n-theirs",
            "patient_id": PATIENT,
            "clinician_id": OTHER,
            "care_team_id": OTHER_TEAM,
            "generated_at": "2026-10-10T00:00:00+00:00",
            "subjective": "s",
            "objective": "o",
            "assessment": "a",
            "plan": "p",
            "model_used": "m",
        },
        {
            "id": "n-mine",
            "patient_id": PATIENT,
            "clinician_id": CLINICIAN,
            "care_team_id": TEAM,
            "generated_at": "2026-10-01T00:00:00+00:00",
            "subjective": "s",
            "objective": "o",
            "assessment": "a",
            "plan": "p",
            "model_used": "m",
        },
    ]
    db = FakeDB(base_tables(soap_notes=notes))
    summary_for(db)
    for note in db.tables["soap_notes"]:
        note["id"] = {
            "n-theirs": "99999999-9999-4999-8999-999999999991",
            "n-mine": "99999999-9999-4999-8999-999999999992",
        }[note["id"]]
        note["clinician_id"] = note["clinician_id"]
        note["patient_id"] = PATIENT
    result = await service_for(db).get_patient_deep_dive(UUID(CLINICIAN), UUID(PATIENT))
    assert result["latest_soap_note"]["id"].endswith("992")
    other = await service_for(db).get_patient_deep_dive(UUID(OTHER), UUID(PATIENT))
    assert other["latest_soap_note"]["id"].endswith("991")


@pytest.mark.asyncio
async def test_deep_dive_shows_only_obligations_barriers_and_rates_of_visible_plans() -> None:
    tables = plan_tables()
    tables["adherence_logs"] = [
        log("obligation", OB_MINE, "completed"),
        log("obligation", OB_THEIRS, "skipped", barrier_code="cost", notes="n", id="b1"),
        log("obligation", OB_THEIRS, "skipped"),
        log("obligation", OB_FREE, "skipped", barrier_code="schedule", notes="n", id="b2"),
    ]
    db = FakeDB(base_tables(**tables))
    summary_for(db)
    result = await service_for(db).get_patient_deep_dive(UUID(CLINICIAN), UUID(PATIENT))
    assert {o["id"] for o in result["obligations"]} == {OB_MINE, OB_FREE, OB_UNOWNED}
    assert {b["target_id"] for b in result["adherence_barriers"]} == {OB_FREE}
    assert result["obligation_completion_rate"] == pytest.approx(0.5)
    assert sum(day["expected"] for day in result["adherence_series"]) == 2


# ── Risk radar ──────────────────────────────────────────────────────────────────────────


def risk_world() -> FakeDB:
    tables = plan_tables()
    tables["adherence_logs"] = [
        log("medication", MED_THEIRS, "skipped", days_ago=d + 1, id=f"s{d}") for d in range(8)
    ] + [log("obligation", OB_FREE, "completed", days_ago=d + 1, id=f"c{d}") for d in range(3)]
    tables["adr_assessments"] = [
        {
            "id": "a-pending",
            "patient_id": PATIENT,
            "status": "draft",
            "reviewed_by": None,
            "reviewed_by_care_team_id": None,
            "updated_at": NOW.isoformat(),
        },
        {
            "id": "a-asked",
            "patient_id": PATIENT,
            "status": "draft",
            "reviewed_by": OTHER,
            "reviewed_by_care_team_id": OTHER_TEAM,
            "updated_at": NOW.isoformat(),
        },
    ]
    return FakeDB(base_tables(**tables))


@pytest.mark.asyncio
async def test_risk_for_a_clinician_ignores_adherence_of_another_teams_plan() -> None:
    db = risk_world()
    mine = CareTeamAccessService(db).for_patient(CLINICIAN, PATIENT)  # type: ignore[arg-type]
    theirs = CareTeamAccessService(db).for_patient(OTHER, PATIENT)  # type: ignore[arg-type]
    service = RiskScoreService(db)  # type: ignore[arg-type]
    for_me = await service.get_patient_risk(UUID(PATIENT), access=mine)
    for_them = await service.get_patient_risk(UUID(PATIENT), access=theirs)
    assert for_me.adherence_score == 1.0
    assert for_them.adherence_score == pytest.approx(3 / 11)


@pytest.mark.asyncio
async def test_risk_counts_a_pending_adr_for_every_team_but_not_another_teams_request() -> None:
    db = risk_world()
    mine = CareTeamAccessService(db).for_patient(CLINICIAN, PATIENT)  # type: ignore[arg-type]
    theirs = CareTeamAccessService(db).for_patient(OTHER, PATIENT)  # type: ignore[arg-type]
    service = RiskScoreService(db)  # type: ignore[arg-type]
    assert (await service.get_patient_risk(UUID(PATIENT), access=mine)).open_adr_count == 1
    assert (await service.get_patient_risk(UUID(PATIENT), access=theirs)).open_adr_count == 2


@pytest.mark.asyncio
async def test_risk_snapshot_requires_a_link() -> None:
    db = risk_world()
    with pytest.raises(AuthorizationError):
        await service_for(db).get_patient_risk_snapshot(UUID(THIRD), UUID(PATIENT))
    snapshot = await service_for(db).get_patient_risk_snapshot(UUID(CLINICIAN), UUID(PATIENT))
    assert snapshot["adherence_score"] == 1.0


@pytest.mark.asyncio
async def test_risk_freshness_does_not_reveal_other_teams_adherence_dates() -> None:
    db = risk_world()
    for row in db.tables["adherence_logs"]:
        if row["target_id"] == MED_THEIRS:
            row["logged_at"] = (NOW - timedelta(minutes=1)).isoformat()
    mine = CareTeamAccessService(db).for_patient(CLINICIAN, PATIENT)  # type: ignore[arg-type]
    risk = await RiskScoreService(db).get_patient_risk(UUID(PATIENT), access=mine)  # type: ignore[arg-type]
    adherence = next(
        s for s in risk.risk_explanation.source_freshness if s.source == "adherence_logs"
    )
    assert adherence.latest_at is not None
    assert adherence.latest_at < NOW - timedelta(hours=12)
    assert "Logged obligation" in risk.last_activity


@pytest.mark.asyncio
async def test_deep_dive_payload_fits_the_response_model() -> None:
    from app.models.dashboard import PatientDeepDive

    db = FakeDB(base_tables(conditions=[condition("Depression", True, OTHER_TEAM)]))
    summary_for(db)
    result = await service_for(db).get_patient_deep_dive(UUID(CLINICIAN), UUID(PATIENT))
    model = PatientDeepDive.model_validate(result)
    assert model.some_conditions_private is True and len(model.care_teams) == 2
