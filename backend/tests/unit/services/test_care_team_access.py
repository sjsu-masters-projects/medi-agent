"""Care-team ownership rules for documents, facts, notes, reviews and sensitive conditions."""

from __future__ import annotations

import pytest

from app.core.exceptions import AuthorizationError
from app.services.care_team_access import CareTeamAccessService, ClinicianAccess, PatientAccess
from tests.unit.services.care_team_fake_db import (
    CLINICIAN,
    OTHER,
    OTHER_TEAM,
    PATIENT,
    SECOND_PATIENT,
    TEAM,
    THIRD,
    THIRD_TEAM,
    FakeDB,
)

MINE = PatientAccess(CLINICIAN, PATIENT, frozenset({TEAM}))
THEIRS = PatientAccess(OTHER, PATIENT, frozenset({OTHER_TEAM}))
NONE = PatientAccess(THIRD, PATIENT, frozenset())


def test_a_clinician_with_no_link_sees_nothing_of_any_kind() -> None:
    assert not NONE
    for row, rule in (
        ({"routing_state": "unrouted"}, NONE.can_see_document),
        ({"care_team_id": TEAM, "clinician_id": THIRD}, NONE.can_see_soap_note),
        ({"reviewed_by": None}, NONE.can_see_adr),
        ({"care_team_id": None}, NONE.can_see_medwatch_draft),
        ({"is_sensitive": False}, NONE.can_see_condition),
        ({"care_team_id": None, "clinician_id": THIRD}, NONE.can_see_import),
    ):
        assert rule(row) is False


def test_documents_are_owned_by_one_team_or_in_every_queue_until_claimed() -> None:
    routed_mine = {"routing_state": "routed", "care_team_id": TEAM}
    routed_theirs = {"routing_state": "routed", "care_team_id": OTHER_TEAM}
    open_doc = {"routing_state": "unrouted", "care_team_id": None}
    orphan = {"routing_state": "routed", "care_team_id": None}  # its team's link was deleted

    assert [MINE.can_see_document(d) for d in (routed_mine, routed_theirs, open_doc, orphan)] == [
        True,
        False,
        True,
        False,
    ]
    assert [THEIRS.can_see_document(d) for d in (routed_mine, routed_theirs, open_doc, orphan)] == [
        False,
        True,
        True,
        False,
    ]


def test_a_document_row_without_its_owner_columns_is_hidden_not_shown() -> None:
    assert MINE.can_see_document({"id": "x"}) is False
    assert MINE.can_see_soap_note({"id": "x"}) is False  # no team and no author


def test_soap_notes_follow_their_team_or_their_author_when_no_team_is_known() -> None:
    assert MINE.can_see_soap_note({"care_team_id": TEAM, "clinician_id": OTHER})
    assert not MINE.can_see_soap_note({"care_team_id": OTHER_TEAM, "clinician_id": CLINICIAN})
    assert MINE.can_see_soap_note({"care_team_id": None, "clinician_id": CLINICIAN})
    assert not THEIRS.can_see_soap_note({"care_team_id": None, "clinician_id": CLINICIAN})


def test_adr_assessments_are_open_while_pending_then_the_reviewing_teams() -> None:
    assert MINE.can_see_adr({"reviewed_by": None}) and THEIRS.can_see_adr({"reviewed_by": None})
    reviewed = {"reviewed_by": OTHER, "reviewed_by_care_team_id": OTHER_TEAM}
    assert THEIRS.can_see_adr(reviewed) and not MINE.can_see_adr(reviewed)
    # Reviewed with no recorded team: unassigned, visible to nobody (not even the reviewer).
    unassigned = {"reviewed_by": CLINICIAN, "reviewed_by_care_team_id": None}
    assert not MINE.can_see_adr(unassigned) and not THEIRS.can_see_adr(unassigned)


def test_medwatch_drafts_and_imports_follow_their_team() -> None:
    assert MINE.can_see_medwatch_draft({"care_team_id": TEAM})
    assert not MINE.can_see_medwatch_draft({"care_team_id": OTHER_TEAM})
    assert not MINE.can_see_medwatch_draft({"care_team_id": None})  # unassigned: nobody
    assert MINE.can_see_import({"care_team_id": TEAM, "clinician_id": OTHER})
    assert not MINE.can_see_import({"care_team_id": OTHER_TEAM, "clinician_id": CLINICIAN})
    assert MINE.can_see_import({"care_team_id": None, "clinician_id": CLINICIAN})
    assert not THEIRS.can_see_import({"care_team_id": None, "clinician_id": CLINICIAN})


CONDITIONS = [
    {"id": "1", "name": "Hypertension", "is_sensitive": False, "recorded_by_care_team_id": TEAM},
    {"id": "2", "name": "Anxiety", "is_sensitive": True, "recorded_by_care_team_id": OTHER_TEAM},
    {"id": "3", "name": "Unknown recorder", "is_sensitive": True, "recorded_by_care_team_id": None},
    {"id": "4", "name": "Asthma", "is_sensitive": False, "recorded_by_care_team_id": None},
]


def test_sensitive_conditions_reach_only_the_recording_team_with_an_explicit_marker() -> None:
    mine, withheld_mine = MINE.split_conditions(CONDITIONS)
    theirs, withheld_theirs = THEIRS.split_conditions(CONDITIONS)

    assert [c["name"] for c in mine] == ["Hypertension", "Asthma"] and withheld_mine is True
    assert [c["name"] for c in theirs] == ["Hypertension", "Anxiety", "Asthma"]
    assert withheld_theirs is True  # the unknown-recorder condition is visible to no clinician
    everyone_sees_all, flag = MINE.split_conditions([CONDITIONS[0], CONDITIONS[3]])
    assert len(everyone_sees_all) == 2 and flag is False


def test_plan_detail_is_readable_only_by_the_owning_team_and_never_when_unowned() -> None:
    owned = {"ownership_state": "owned", "care_team_id": TEAM}
    assert MINE.can_read_plan(owned) and not THEIRS.can_read_plan(owned)
    assert not MINE.can_read_plan({"ownership_state": "unowned", "care_team_id": None})
    assert not MINE.can_read_plan({"ownership_state": "unassigned_legacy", "care_team_id": None})


def test_clinician_access_applies_each_patients_own_links_to_a_mixed_list() -> None:
    access = ClinicianAccess(
        CLINICIAN, {PATIENT: frozenset({TEAM}), SECOND_PATIENT: frozenset({THIRD_TEAM})}
    )
    docs = [
        {"patient_id": PATIENT, "routing_state": "routed", "care_team_id": TEAM},
        {"patient_id": PATIENT, "routing_state": "routed", "care_team_id": OTHER_TEAM},
        {"patient_id": SECOND_PATIENT, "routing_state": "unrouted", "care_team_id": None},
        {"patient_id": "unknown-patient", "routing_state": "unrouted", "care_team_id": None},
    ]

    kept = access.keep(docs, "document")

    assert [(d["patient_id"], d["care_team_id"]) for d in kept] == [
        (PATIENT, TEAM),
        (SECOND_PATIENT, None),
    ]


def test_the_service_loads_only_active_links_of_this_clinician_and_patient() -> None:
    db = FakeDB()
    db.tables["care_teams"].append(
        {"id": THIRD_TEAM, "patient_id": PATIENT, "clinician_id": CLINICIAN, "status": "inactive"}
    )
    service = CareTeamAccessService(db)  # type: ignore[arg-type]

    access = service.for_patient(CLINICIAN, PATIENT)

    assert access.team_ids == frozenset({TEAM})
    assert service.for_clinician(OTHER).for_patient(PATIENT).team_ids == frozenset({OTHER_TEAM})
    with pytest.raises(AuthorizationError):
        service.for_patient(THIRD, PATIENT)
    assert not service.for_patient(THIRD, PATIENT, require=False)


def fact_db() -> FakeDB:
    return FakeDB(
        {
            "documents": [
                {"id": "d-mine", "routing_state": "routed", "care_team_id": TEAM},
                {"id": "d-theirs", "routing_state": "routed", "care_team_id": OTHER_TEAM},
                {"id": "d-open", "routing_state": "unrouted", "care_team_id": None},
            ],
            "source_provenances": [
                {"id": "p-mine", "document_id": "d-mine", "care_team_id": None},
                {"id": "p-theirs", "document_id": "d-theirs", "care_team_id": None},
                {"id": "p-open", "document_id": "d-open", "care_team_id": None},
                {"id": "p-entry-mine", "document_id": None, "care_team_id": TEAM},
                {"id": "p-entry-theirs", "document_id": None, "care_team_id": OTHER_TEAM},
                {"id": "p-entry-legacy", "document_id": None, "care_team_id": None},
            ],
            "evidence_citations": [
                {"fact_id": "f-mine", "provenance_id": "p-mine"},
                {"fact_id": "f-theirs", "provenance_id": "p-theirs"},
                {"fact_id": "f-open", "provenance_id": "p-open"},
                {"fact_id": "f-mixed", "provenance_id": "p-mine"},
                {"fact_id": "f-mixed", "provenance_id": "p-theirs"},
                {"fact_id": "f-entry-mine", "provenance_id": "p-entry-mine"},
                {"fact_id": "f-entry-theirs", "provenance_id": "p-entry-theirs"},
                {"fact_id": "f-entry-legacy", "provenance_id": "p-entry-legacy"},
                {"fact_id": "f-dangling", "provenance_id": "p-missing"},
            ],
        }
    )


def test_a_fact_is_visible_only_if_every_source_behind_it_is() -> None:
    service = CareTeamAccessService(fact_db())  # type: ignore[arg-type]
    ids = [
        "f-mine",
        "f-theirs",
        "f-open",
        "f-mixed",
        "f-entry-mine",
        "f-entry-theirs",
        "f-entry-legacy",
        "f-dangling",
        "f-no-citation",
    ]

    visible = service.visible_fact_ids(MINE, ids)

    assert visible == {"f-mine", "f-open", "f-entry-mine", "f-entry-legacy", "f-no-citation"}
    assert service.visible_fact_ids(THEIRS, ids) == {
        "f-theirs",
        "f-open",
        "f-entry-theirs",
        "f-entry-legacy",
        "f-no-citation",
    }
    assert service.visible_fact_ids(NONE, ids) == set()
    assert service.visible_fact_ids(MINE, []) == set()
