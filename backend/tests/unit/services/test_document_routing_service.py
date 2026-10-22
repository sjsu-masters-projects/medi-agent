"""Where a document goes at upload, who may claim it, and which queue shows it. Synthetic data."""

from __future__ import annotations

import pytest
from postgrest.exceptions import APIError

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.services.document_routing_service import DocumentRoutingService
from tests.unit.services.care_team_fake_db import (
    CLINIC,
    CLINICIAN,
    OTHER,
    OTHER_CLINIC,
    OTHER_TEAM,
    PATIENT,
    SECOND_PATIENT,
    TEAM,
    THIRD,
    FakeDB,
    standard_links,
)

TWO = "55555555-5555-4555-8555-555555555555"
TWO_A = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1"
TWO_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2"
DOC_MINE = "dddddddd-dddd-4ddd-8ddd-ddddddddddd1"
DOC_THEIRS = "dddddddd-dddd-4ddd-8ddd-ddddddddddd2"
DOC_OPEN = "dddddddd-dddd-4ddd-8ddd-ddddddddddd3"
DOC_TWO_B = "dddddddd-dddd-4ddd-8ddd-ddddddddddd4"
DOC_FOREIGN_PATIENT = "dddddddd-dddd-4ddd-8ddd-ddddddddddd5"


def _doc(doc_id, team, state="routed", patient=PATIENT):
    return {
        "id": doc_id,
        "patient_id": patient,
        "file_name": f"{doc_id[-1]}.pdf",
        "display_title": {},
        "document_type": "lab_report",
        "created_at": f"2026-10-0{doc_id[-1]}T10:00:00Z",
        "review_status": "pending",
        "uploaded_by_role": "patient",
        "parse_status": "completed",
        "routing_state": state,
        "care_team_id": team,
    }


def _db(extra_links=(), documents=None, **tables):
    links = standard_links() + list(extra_links)
    docs = (
        documents
        if documents is not None
        else [
            _doc(DOC_MINE, TEAM),
            _doc(DOC_THEIRS, OTHER_TEAM),
            _doc(DOC_OPEN, None, "unrouted"),
        ]
    )
    return FakeDB({"care_teams": links, "documents": docs, **tables})


def _two_links():
    return [
        {
            "id": TWO_A,
            "patient_id": PATIENT,
            "clinician_id": TWO,
            "clinic_id": CLINIC,
            "status": "active",
            "role": "specialist",
        },
        {
            "id": TWO_B,
            "patient_id": PATIENT,
            "clinician_id": TWO,
            "clinic_id": OTHER_CLINIC,
            "status": "active",
            "role": "specialist",
        },
    ]


# ── upload_target: patient ─────────────────────────────────────────────────────────────


def _patient_target(db, **kwargs):
    arguments = {"care_team_id": None, "not_sure": False, **kwargs}
    return DocumentRoutingService(db).upload_target(
        uploader_role="patient", uploader_id=PATIENT, patient_id=PATIENT, **arguments
    )


def test_a_patient_with_one_team_routes_to_it_without_choosing() -> None:
    db = FakeDB({"care_teams": [standard_links()[0]]})
    assert _patient_target(db) == {"care_team_id": TEAM, "routing_state": "routed"}


def test_a_patient_with_no_team_leaves_the_document_unrouted() -> None:
    assert _patient_target(FakeDB({"care_teams": []})) == {
        "care_team_id": None,
        "routing_state": "unrouted",
    }


def test_a_patient_with_two_teams_must_choose() -> None:
    with pytest.raises(ValidationError) as caught:
        _patient_target(_db())
    assert caught.value.code == "CARE_TEAM_REQUIRED"


def test_a_patient_may_name_one_of_their_teams_or_say_not_sure() -> None:
    assert _patient_target(_db(), care_team_id=OTHER_TEAM) == {
        "care_team_id": OTHER_TEAM,
        "routing_state": "routed",
    }
    assert _patient_target(_db(), not_sure=True) == {
        "care_team_id": None,
        "routing_state": "unrouted",
    }


def test_a_patient_cannot_name_a_team_and_not_sure_together() -> None:
    with pytest.raises(ValidationError):
        _patient_target(_db(), care_team_id=TEAM, not_sure=True)


@pytest.mark.parametrize("chosen", [TWO_A, "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa9"])
def test_a_patient_cannot_route_to_another_patients_or_an_unknown_team(chosen) -> None:
    db = _db(extra_links=[{**_two_links()[0], "patient_id": SECOND_PATIENT}])
    with pytest.raises(ValidationError) as caught:
        _patient_target(db, care_team_id=chosen)
    assert caught.value.code != "CARE_TEAM_REQUIRED"


def test_a_patient_cannot_route_to_an_ended_team() -> None:
    links = standard_links()
    links[1]["status"] = "ended"
    with pytest.raises(ValidationError):
        _patient_target(FakeDB({"care_teams": links}), care_team_id=OTHER_TEAM)
    # ...and the remaining active team is the implicit target.
    assert _patient_target(FakeDB({"care_teams": links}))["care_team_id"] == TEAM


# ── upload_target: clinician ───────────────────────────────────────────────────────────


def _clinician_target(db, clinician=CLINICIAN, **kwargs):
    arguments = {"care_team_id": None, "not_sure": False, **kwargs}
    return DocumentRoutingService(db).upload_target(
        uploader_role="clinician", uploader_id=clinician, patient_id=PATIENT, **arguments
    )


def test_a_clinician_upload_goes_to_their_only_link() -> None:
    assert _clinician_target(_db()) == {"care_team_id": TEAM, "routing_state": "routed"}


def test_a_clinician_cannot_choose_not_sure() -> None:
    with pytest.raises(ValidationError):
        _clinician_target(_db(), not_sure=True)


def test_a_clinician_cannot_route_to_a_team_that_is_not_theirs() -> None:
    with pytest.raises(ValidationError):
        _clinician_target(_db(), care_team_id=OTHER_TEAM)


def test_a_clinician_with_no_link_is_refused() -> None:
    with pytest.raises(AuthorizationError):
        _clinician_target(_db(), clinician=THIRD)


def test_a_clinician_with_two_links_must_say_which() -> None:
    db = _db(extra_links=_two_links())
    with pytest.raises(ValidationError) as caught:
        _clinician_target(db, clinician=TWO)
    assert caught.value.code == "CARE_TEAM_REQUIRED"
    assert _clinician_target(db, clinician=TWO, care_team_id=TWO_B)["care_team_id"] == TWO_B


# ── patient_options ────────────────────────────────────────────────────────────────────


def test_patient_options_list_active_teams_with_names_only() -> None:
    db = _db(
        clinicians=[
            {
                "id": CLINICIAN,
                "first_name": "Ana",
                "last_name": "Cole",
                "specialty": "Cardiology",
                "phone": "555-0100",
            },
            {"id": OTHER, "first_name": "Ben", "last_name": "Ito", "specialty": "Orthopaedics"},
        ],
        clinics=[
            {"id": CLINIC, "display_name": "North Clinic"},
            {"id": OTHER_CLINIC, "display_name": "South Clinic"},
        ],
    )
    db.tables["care_teams"][1]["specialty_context"] = "Sports medicine"
    options = DocumentRoutingService(db).patient_options(PATIENT)
    assert {item["care_team_id"] for item in options} == {TEAM, OTHER_TEAM}
    by_team = {item["care_team_id"]: item for item in options}
    assert by_team[TEAM] == {
        "care_team_id": TEAM,
        "specialty": "Cardiology",
        "clinician_name": "Ana Cole",
        "clinic_name": "North Clinic",
        "clinic_id": CLINIC,
    }
    assert by_team[OTHER_TEAM]["specialty"] == "Sports medicine"
    assert "phone" not in str(options)


def test_patient_options_leave_out_ended_teams_and_other_patients() -> None:
    links = standard_links()
    links[1]["status"] = "ended"
    links.append({**_two_links()[0], "patient_id": SECOND_PATIENT})
    options = DocumentRoutingService(FakeDB({"care_teams": links})).patient_options(PATIENT)
    assert [item["care_team_id"] for item in options] == [TEAM]


# ── claim ──────────────────────────────────────────────────────────────────────────────


def _claim(db, clinician=CLINICIAN, document=DOC_OPEN, team=TEAM):
    return DocumentRoutingService(db).claim(
        clinician_id=clinician, document_id=document, care_team_id=team
    )


def test_claim_calls_the_rpc_for_the_clinicians_own_team() -> None:
    db = _db()
    db.rpc_handlers["claim_document"] = lambda params: {
        "document_id": params["p_document_id"],
        "care_team_id": params["p_care_team_id"],
        "status": "claimed",
        "replayed": False,
    }
    assert _claim(db) == {
        "document_id": DOC_OPEN,
        "care_team_id": TEAM,
        "status": "claimed",
        "replayed": False,
    }
    assert db.rpc_calls == [
        (
            "claim_document",
            {"p_document_id": DOC_OPEN, "p_actor_id": CLINICIAN, "p_care_team_id": TEAM},
        )
    ]


@pytest.mark.parametrize(
    ("clinician", "team"),
    [(CLINICIAN, OTHER_TEAM), (THIRD, TEAM), (OTHER, TEAM)],
)
def test_claim_is_refused_before_the_rpc_for_a_team_the_caller_does_not_hold(
    clinician, team
) -> None:
    db = _db()
    with pytest.raises(NotFoundError):
        _claim(db, clinician=clinician, team=team)
    assert db.rpc_calls == []


def test_claim_of_an_unknown_document_is_not_found() -> None:
    db = _db()
    with pytest.raises(NotFoundError):
        _claim(db, document="dddddddd-dddd-4ddd-8ddd-ddddddddd999")
    assert db.rpc_calls == []


def _raise(message: str, code: str):
    def handler(_params):
        raise APIError({"message": message, "code": code})

    return handler


def test_claim_maps_database_refusals_to_neutral_errors() -> None:
    db = _db()
    db.rpc_handlers["claim_document"] = _raise("document unavailable", "42501")
    with pytest.raises(NotFoundError):
        _claim(db)
    db.rpc_handlers["claim_document"] = _raise("document was claimed by someone else", "40001")
    with pytest.raises(ValidationError) as caught:
        _claim(db)
    assert caught.value.code == "DOCUMENT_ALREADY_CLAIMED"


# ── queue ──────────────────────────────────────────────────────────────────────────────


def _ids(rows):
    return {row["id"] for row in rows}


def test_each_clinician_sees_their_teams_documents_plus_the_unrouted_ones() -> None:
    db = _db()
    service = DocumentRoutingService(db)
    mine = service.queue(clinician_id=CLINICIAN)
    assert _ids(mine) == {DOC_MINE, DOC_OPEN}
    assert _ids(service.queue(clinician_id=OTHER)) == {DOC_THEIRS, DOC_OPEN}
    assert service.queue(clinician_id=THIRD) == []


def test_unrouted_rows_need_a_claim_and_list_the_clinicians_claimable_teams() -> None:
    rows = {row["id"]: row for row in DocumentRoutingService(_db()).queue(clinician_id=CLINICIAN)}
    assert rows[DOC_OPEN]["needs_claim"] is True
    assert rows[DOC_OPEN]["claimable_care_team_ids"] == [TEAM]
    assert rows[DOC_MINE]["needs_claim"] is False


def test_a_clinician_with_two_links_sees_both_teams_documents() -> None:
    documents = [_doc(DOC_MINE, TWO_A), _doc(DOC_TWO_B, TWO_B), _doc(DOC_THEIRS, OTHER_TEAM)]
    db = _db(extra_links=_two_links(), documents=documents)
    rows = DocumentRoutingService(db).queue(clinician_id=TWO)
    assert _ids(rows) == {DOC_MINE, DOC_TWO_B}


def test_the_queue_can_be_narrowed_to_one_patient_and_never_crosses_patients() -> None:
    documents = [_doc(DOC_MINE, TEAM), _doc(DOC_FOREIGN_PATIENT, None, "unrouted", SECOND_PATIENT)]
    service = DocumentRoutingService(_db(documents=documents))
    assert _ids(service.queue(clinician_id=CLINICIAN)) == {DOC_MINE}
    assert service.queue(clinician_id=CLINICIAN, patient_id=SECOND_PATIENT) == []
    assert _ids(service.queue(clinician_id=CLINICIAN, patient_id=PATIENT)) == {DOC_MINE}


def test_a_routed_row_without_its_owner_column_is_never_shown() -> None:
    documents = [{**_doc(DOC_MINE, None), "routing_state": "routed"}]
    assert DocumentRoutingService(_db(documents=documents)).queue(clinician_id=CLINICIAN) == []
