"""Plan selection, listing, merged patient view and publication errors across care teams."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from postgrest.exceptions import APIError

from app.core.exceptions import AuthorizationError, ConflictError, NotFoundError, ValidationError
from app.services.care_plan_lineage import CarePlanLineageService
from app.services.care_plan_review_service import CarePlanReviewService
from app.services.care_plan_service import CarePlanService
from tests.unit.services.care_team_fake_db import (
    CLINIC,
    CLINICIAN,
    OTHER,
    OTHER_CLINIC,
    OTHER_TEAM,
    PATIENT,
    TEAM,
    THIRD,
    FakeDB,
)

MY_PLAN = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1"
THEIR_PLAN = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2"
UNOWNED_PLAN = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb3"
ADOPTED_PLAN = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb4"
MY_VERSION = "dddddddd-dddd-4ddd-8ddd-ddddddddddd1"
THEIR_VERSION = "dddddddd-dddd-4ddd-8ddd-ddddddddddd2"
UNOWNED_VERSION = "dddddddd-dddd-4ddd-8ddd-ddddddddddd3"


def uid(text: str) -> UUID:
    return UUID(text)


def world() -> FakeDB:
    db = FakeDB(
        {
            "clinic_memberships": [
                {
                    "clinician_id": CLINICIAN,
                    "clinic_id": CLINIC,
                    "status": "active",
                    "role": "provider",
                    "clinics": {"status": "active"},
                },
                {
                    "clinician_id": OTHER,
                    "clinic_id": OTHER_CLINIC,
                    "status": "active",
                    "role": "provider",
                    "clinics": {"status": "active"},
                },
            ],
            "care_plans": [
                {
                    "id": MY_PLAN,
                    "patient_id": PATIENT,
                    "care_team_id": TEAM,
                    "origin_care_team_id": TEAM,
                    "origin": "native",
                    "ownership_state": "owned",
                    "owner_snapshot": {},
                    "created_at": "1",
                },
                {
                    "id": THEIR_PLAN,
                    "patient_id": PATIENT,
                    "care_team_id": OTHER_TEAM,
                    "origin_care_team_id": OTHER_TEAM,
                    "origin": "native",
                    "ownership_state": "owned",
                    "owner_snapshot": {},
                    "created_at": "2",
                },
                {
                    "id": UNOWNED_PLAN,
                    "patient_id": PATIENT,
                    "care_team_id": None,
                    "origin_care_team_id": None,
                    "origin": "legacy",
                    "ownership_state": "unassigned_legacy",
                    "created_at": "3",
                    "owner_snapshot": {
                        "clinician_name": "Dr Gone",
                        "specialty": "ENT",
                        "clinic_name": "Elm",
                        "clinic_id": None,
                    },
                },
            ],
            "care_plan_versions": [
                {
                    "id": MY_VERSION,
                    "patient_id": PATIENT,
                    "care_plan_id": MY_PLAN,
                    "version_number": 2,
                    "status": "draft",
                    "approved_at": None,
                },
                {
                    "id": "dddddddd-dddd-4ddd-8ddd-ddddddddddd9",
                    "patient_id": PATIENT,
                    "care_plan_id": MY_PLAN,
                    "version_number": 1,
                    "status": "approved",
                    "approved_at": "2026-10-01",
                },
                {
                    "id": THEIR_VERSION,
                    "patient_id": PATIENT,
                    "care_plan_id": THEIR_PLAN,
                    "version_number": 1,
                    "status": "approved",
                    "approved_at": "2026-10-02",
                },
                {
                    "id": UNOWNED_VERSION,
                    "patient_id": PATIENT,
                    "care_plan_id": UNOWNED_PLAN,
                    "version_number": 1,
                    "status": "approved",
                    "approved_at": "2026-09-01",
                },
            ],
        }
    )
    for link in db.tables["care_teams"]:
        link["specialty_context"] = "Cardiology" if link["id"] == TEAM else "Orthopaedics"
        link["clinicians"] = {
            "first_name": "Elena" if link["id"] == TEAM else "Omar",
            "last_name": "Park",
            "specialty": "x",
        }
        link["clinics"] = {"display_name": "Cedar Grove" if link["id"] == TEAM else "Birch"}
        link["created_at"] = "1"
    return db


def service(db: FakeDB) -> CarePlanService:
    svc = CarePlanService(db)  # type: ignore[arg-type]
    svc.scopes = svc.lineage.scopes  # type: ignore[assignment]
    return svc


def test_a_clinician_selects_only_their_own_plan() -> None:
    lineage = CarePlanLineageService(world())  # type: ignore[arg-type]

    assert lineage.select_owned_plan(uid(CLINICIAN), uid(PATIENT))["id"] == MY_PLAN  # type: ignore[index]
    assert lineage.select_owned_plan(uid(OTHER), uid(PATIENT))["id"] == THEIR_PLAN  # type: ignore[index]


def test_a_clinician_cannot_name_another_teams_plan_or_team() -> None:
    lineage = CarePlanLineageService(world())  # type: ignore[arg-type]

    with pytest.raises(NotFoundError):
        lineage.select_owned_plan(uid(CLINICIAN), uid(PATIENT), care_plan_id=uid(THEIR_PLAN))
    with pytest.raises(NotFoundError):
        lineage.select_owned_plan(uid(CLINICIAN), uid(PATIENT), care_team_id=uid(OTHER_TEAM))
    with pytest.raises(AuthorizationError):
        lineage.select_owned_plan(uid(THIRD), uid(PATIENT))


def test_a_version_of_another_teams_unowned_or_foreign_plan_is_simply_not_found() -> None:
    lineage = CarePlanLineageService(world())  # type: ignore[arg-type]

    for version in (THEIR_VERSION, UNOWNED_VERSION, "dddddddd-dddd-4ddd-8ddd-dddddddddd00"):
        with pytest.raises(NotFoundError):
            lineage.require_owned_version(uid(CLINICIAN), uid(PATIENT), uid(version))
    version, plan = lineage.require_owned_version(uid(CLINICIAN), uid(PATIENT), uid(MY_VERSION))
    assert plan["id"] == MY_PLAN and version["id"] == MY_VERSION


def test_two_links_with_two_plans_require_a_named_care_team() -> None:
    db = world()
    db.tables["care_teams"].append(
        {
            "id": THIRD,
            "patient_id": PATIENT,
            "clinician_id": CLINICIAN,
            "clinic_id": OTHER_CLINIC,
            "status": "active",
        }
    )
    db.tables["clinic_memberships"].append(
        {
            "clinician_id": CLINICIAN,
            "clinic_id": OTHER_CLINIC,
            "status": "active",
            "clinics": {"status": "active"},
        }
    )
    db.tables["care_plans"].append(
        {
            "id": ADOPTED_PLAN,
            "patient_id": PATIENT,
            "care_team_id": THIRD,
            "origin": "native",
            "ownership_state": "owned",
            "created_at": "4",
            "owner_snapshot": {},
        }
    )
    lineage = CarePlanLineageService(db)  # type: ignore[arg-type]

    with pytest.raises(ValidationError) as caught:
        lineage.select_owned_plan(uid(CLINICIAN), uid(PATIENT))
    assert caught.value.code == "CARE_TEAM_REQUIRED"
    assert (
        lineage.select_owned_plan(uid(CLINICIAN), uid(PATIENT), care_team_id=uid(THIRD))["id"]
        == ADOPTED_PLAN
    )  # type: ignore[index]


def test_the_plan_list_shows_other_teams_metadata_only_and_who_may_adopt_an_unowned_plan() -> None:
    plans = service(world()).plans_for_clinician(uid(CLINICIAN), uid(PATIENT))
    by_id = {plan["care_plan_id"]: plan for plan in plans}

    mine, theirs, unowned = by_id[MY_PLAN], by_id[THEIR_PLAN], by_id[UNOWNED_PLAN]
    assert mine["is_mine"] and mine["draft_version_id"] == MY_VERSION
    assert mine["active_version_id"] == "dddddddd-dddd-4ddd-8ddd-ddddddddddd9"
    assert theirs["is_mine"] is False and theirs["approved_at"] == "2026-10-02"
    assert theirs["owner"] == {
        "specialty": "Orthopaedics",
        "clinician_name": "Omar Park",
        "clinic_id": OTHER_CLINIC,
        "clinic_name": "Birch",
    }
    for hidden in ("draft_version_id", "active_version_id", "generation", "latest_version_number"):
        assert hidden not in theirs and hidden not in unowned
    assert unowned["adoptable_by_care_team_ids"] == [TEAM]
    assert unowned["owner"]["clinician_name"] == "Dr Gone"


def test_the_patient_sees_every_approved_plan_merged_with_each_items_owner() -> None:
    db = world()
    db.tables["care_plan_items"] = [
        {
            "id": "i1",
            "plan_version_id": "dddddddd-dddd-4ddd-8ddd-ddddddddddd9",
            "is_removed": False,
            "title": "A",
            "created_at": "1",
        },
        {
            "id": "i2",
            "plan_version_id": THEIR_VERSION,
            "is_removed": False,
            "title": "B",
            "created_at": "1",
        },
        {
            "id": "i3",
            "plan_version_id": UNOWNED_VERSION,
            "is_removed": False,
            "title": "C",
            "created_at": "1",
        },
        {
            "id": "i4",
            "plan_version_id": UNOWNED_VERSION,
            "is_removed": False,
            "title": "D",
            "created_at": "1",
        },
    ]
    db.tables["care_plan_item_retirements"] = [{"item_id": "i4", "care_plan_id": UNOWNED_PLAN}]
    svc = service(db)
    svc._hydrate_plan = lambda version: {  # type: ignore[method-assign]
        **version,
        "items": [
            dict(i) for i in db.tables["care_plan_items"] if i["plan_version_id"] == version["id"]
        ],
    }

    merged = svc.get_for_patient(uid(PATIENT))

    assert merged is not None
    owners = {item["id"]: item["plan_owner"] for item in merged["items"]}
    assert set(owners) == {"i1", "i2", "i3"}  # i4 was retired
    assert owners["i1"]["specialty"] == "Cardiology" and owners["i1"]["unowned_notice"] is False
    assert owners["i3"]["ownership_state"] == "unassigned_legacy" and owners["i3"]["unowned_notice"]
    assert owners["i3"]["clinician_name"] == "Dr Gone"
    assert len(merged["plans"]) == 3
    assert merged["approved_at"] == "2026-10-02"


def test_a_patient_with_no_approved_plan_has_none() -> None:
    assert service(FakeDB()).get_for_patient(uid(PATIENT)) is None


def _api_error(code: str, message: str) -> APIError:
    return APIError({"message": message, "code": code, "details": None, "hint": None})


def _publishing(db: FakeDB, error: APIError) -> CarePlanService:
    svc = service(db)
    svc.publication_snapshot = MagicMock()  # type: ignore[method-assign]

    def fail(name: str, params: dict[str, Any]) -> Any:
        chain = MagicMock()
        chain.execute.side_effect = error
        return chain

    db.rpc = fail  # type: ignore[method-assign,assignment]
    return svc


def test_a_cross_plan_blocker_becomes_a_conflict_with_both_instructions() -> None:
    db = world()
    svc = _publishing(
        db, _api_error("CP001", "resolve each cross-plan conflict before publication")
    )
    svc.cross_plan_review = MagicMock(
        return_value={  # type: ignore[method-assign]
            "interaction_coverage": "not_checked",
            "conflicts": [{"severity": "blocker", "fingerprint": "f"}, {"severity": "warning"}],
        }
    )

    with pytest.raises(ConflictError) as caught:
        svc.approve(uid(CLINICIAN), uid(PATIENT), uid(MY_VERSION), "ok")

    assert caught.value.code == "CROSS_PLAN_CONFLICT"
    assert caught.value.details == {
        "conflicts": [{"severity": "blocker", "fingerprint": "f"}],
        "interaction_coverage": "not_checked",
    }


@pytest.mark.parametrize(
    "code,message,expected,error_code",
    [
        ("42501", "care plan unavailable", NotFoundError, "NOT_FOUND"),
        (
            "22023",
            "this idempotency key was used for a different request",
            ConflictError,
            "IDEMPOTENCY_KEY_REUSED",
        ),
        ("P0001", "care plan draft is not eligible for approval", ConflictError, "CONFLICT"),
        (
            "P0001",
            "all care-plan blockers must be resolved before approval",
            ValidationError,
            "VALIDATION_ERROR",
        ),
    ],
)
def test_publication_database_errors_map_to_neutral_api_errors(
    code, message, expected, error_code
) -> None:
    svc = _publishing(world(), _api_error(code, message))

    with pytest.raises(expected) as caught:
        svc.approve(uid(CLINICIAN), uid(PATIENT), uid(MY_VERSION), "ok")

    assert caught.value.code == error_code


def test_approve_sends_the_key_the_exclusions_and_the_reviewer() -> None:
    db = world()
    svc = service(db)
    svc.publication_snapshot = MagicMock()  # type: ignore[method-assign]
    db.rpc_handlers["publish_care_plan_version"] = lambda params: {"status": "approved"}
    key, item = UUID(int=5), UUID(int=6)

    svc.approve(
        uid(CLINICIAN),
        uid(PATIENT),
        uid(MY_VERSION),
        " note ",
        idempotency_key=key,
        excluded_item_ids=[item],
    )

    ((name, params),) = db.rpc_calls
    assert name == "publish_care_plan_version"
    assert params == {
        "p_plan_version_id": MY_VERSION,
        "p_reviewer_id": CLINICIAN,
        "p_note": "note",
        "p_idempotency_key": str(key),
        "p_excluded_item_ids": [str(item)],
    }
    svc.publication_snapshot.assert_called_once()
    assert svc.publication_snapshot.call_args.kwargs["excluded"] == [item]


def test_another_teams_draft_cannot_be_published_or_reviewed() -> None:
    svc = service(world())

    for call in (
        lambda: svc.approve(uid(CLINICIAN), uid(PATIENT), uid(THEIR_VERSION), "ok"),
        lambda: svc.cross_plan_review(uid(CLINICIAN), uid(PATIENT), uid(THEIR_VERSION)),
        lambda: svc.record_conflict_resolution(
            uid(CLINICIAN),
            uid(PATIENT),
            uid(THEIR_VERSION),
            fingerprint="f",
            resolution="keep_both",
            reason="r",
        ),
    ):
        with pytest.raises(NotFoundError):
            call()


def test_unowned_activities_open_only_for_an_unowned_plan_of_the_patient() -> None:
    db = world()
    db.tables["care_plan_items"] = [
        {
            "id": "i3",
            "plan_version_id": UNOWNED_VERSION,
            "is_removed": False,
            "title": "C",
            "category": "other",
            "instructions": "x",
            "frequency": "daily",
            "medication": {},
            "wording": {},
            "created_at": "1",
            "source_fact_id": "secret-fact",
        }
    ]
    svc = service(db)

    opened = svc.unowned_activities(uid(CLINICIAN), uid(PATIENT), uid(UNOWNED_PLAN))

    assert [a["id"] for a in opened["activities"]] == ["i3"]
    assert "source_fact_id" not in opened["activities"][0]
    with pytest.raises(NotFoundError):
        svc.unowned_activities(uid(CLINICIAN), uid(PATIENT), uid(THEIR_PLAN))


def test_review_items_list_only_my_teams_and_admin_items_carry_no_patient() -> None:
    db = world()
    db.tables["care_plan_review_items"] = [
        {
            "id": "r1",
            "patient_id": PATIENT,
            "target_care_team_id": TEAM,
            "status": "open",
            "kind": "unowned_plan",
            "created_at": "1",
        },
        {
            "id": "r2",
            "patient_id": PATIENT,
            "target_care_team_id": OTHER_TEAM,
            "status": "open",
            "kind": "unowned_plan",
            "created_at": "1",
        },
        {
            "id": "r3",
            "care_plan_id": UNOWNED_PLAN,
            "patient_id": PATIENT,
            "target_clinic_id": CLINIC,
            "status": "open",
            "kind": "unowned_plan",
            "created_at": "1",
        },
    ]
    db.tables["clinic_memberships"][0]["role"] = "admin"

    listing = CarePlanReviewService(db).list_for_clinician(uid(CLINICIAN))  # type: ignore[arg-type]

    assert [i["id"] for i in listing["items"]] == ["r1"]
    assert [i["id"] for i in listing["clinic_items"]] == ["r3"]


def test_adoption_and_retirement_require_the_callers_own_link_to_that_patient() -> None:
    db = world()
    svc = CarePlanReviewService(db)  # type: ignore[arg-type]

    for call in (
        lambda: svc.adopt(
            uid(CLINICIAN), uid(UNOWNED_PLAN), care_team_id=uid(OTHER_TEAM), note="n"
        ),
        lambda: svc.retire_items(
            uid(THIRD),
            uid(UNOWNED_PLAN),
            care_team_id=uid(TEAM),
            item_ids=[UUID(int=1)],
            reason="r",
        ),
    ):
        with pytest.raises((NotFoundError, AuthorizationError)):
            call()
    assert db.rpc_calls == []


def test_a_lost_adoption_race_is_a_conflict() -> None:
    db = world()
    svc = CarePlanReviewService(db)  # type: ignore[arg-type]

    def lose(name: str, params: dict[str, Any]) -> Any:
        chain = MagicMock()
        chain.execute.side_effect = _api_error("40001", "care plan was adopted by someone else")
        return chain

    db.rpc = lose  # type: ignore[method-assign,assignment]
    with pytest.raises(ConflictError) as caught:
        svc.adopt(uid(CLINICIAN), uid(UNOWNED_PLAN), care_team_id=uid(TEAM), note="n")
    assert caught.value.code == "PLAN_ALREADY_ADOPTED"
