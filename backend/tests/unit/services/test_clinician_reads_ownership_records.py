"""SOAP notes, ADR reviews, MedWatch drafts, the timeline and lists follow ownership.

Companion to test_clinician_reads_ownership.py: same patient, two care teams (cardiology:
CLINICIAN, orthopaedics: OTHER), same in-memory databases. Synthetic data only.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.models.adr import (
    ADRReviewAction,
    ADRReviewDecisionRequest,
    MedWatchDraftCreateRequest,
    MedWatchDraftDiscardRequest,
)
from app.models.dashboard import SoapNote
from app.services.care_conversation_service import CareConversationService
from app.services.care_team_access import CareTeamAccessService
from app.services.clinic_link_scope import ClinicLinkScope
from app.services.medwatch_service import MedWatchService
from app.services.patient_timeline_service import PatientTimelineService
from app.services.soap_note_prompts import build_soap_prompt
from app.services.soap_note_service import SoapNoteService
from tests.unit.services import medwatch_fake_db as mw
from tests.unit.services.care_team_fake_db import (
    CLINIC,
    CLINICIAN,
    OTHER,
    OTHER_TEAM,
    PATIENT,
    TEAM,
    THIRD,
    FakeDB,
)
from tests.unit.services.test_clinician_reads_ownership import (
    OB_THEIRS,
    base_tables,
    condition,
    log,
    plan_tables,
    service_for,
)
from tests.unit.services.test_medwatch_service import (
    ASSESSMENT,
    _approval,
    _draft_row,
    _sources_db,
)

NOTE = SoapNote(subjective="s", objective="o", assessment="a", plan="p")


def two_links(db: FakeDB) -> None:
    """Give CLINICIAN both teams (cardiology at one clinic, a second link at another)."""
    db.tables["care_teams"][1]["clinician_id"] = CLINICIAN


# ── SOAP notes ──────────────────────────────────────────────────────────────────────────


def soap_world() -> FakeDB:
    tables = plan_tables()
    tables["adherence_logs"] = [
        log("obligation", OB_THEIRS, "skipped", id=f"x{i}") for i in range(5)
    ] + [log("obligation", "eeeeeeee-0000-4000-8000-000000000004", "completed", id="y")]
    tables["conditions"] = [
        condition("Hypertension", False, OTHER_TEAM),
        condition("Depression", True, OTHER_TEAM),
    ]
    tables["adr_assessments"] = [
        {
            "id": "p",
            "patient_id": PATIENT,
            "status": "draft",
            "reviewed_by": None,
            "created_at": "2026-10-03",
            "naranjo_score": 5,
            "causality": "Possible",
        },
        {
            "id": "r",
            "patient_id": PATIENT,
            "status": "reviewed",
            "reviewed_by": OTHER,
            "reviewed_by_care_team_id": OTHER_TEAM,
            "created_at": "2026-10-02",
            "naranjo_score": 7,
            "causality": "Probable",
        },
    ]
    tables["allergies"] = [
        {
            "id": "al",
            "patient_id": PATIENT,
            "allergen": "Penicillin",
            "severity": "severe",
            "recorded_by_care_team_id": OTHER_TEAM,
        }
    ]
    return FakeDB(base_tables(**tables))


@pytest.mark.asyncio
async def test_soap_context_holds_only_what_the_clinician_may_read() -> None:
    db = soap_world()
    access = CareTeamAccessService(db).for_patient(CLINICIAN, PATIENT)  # type: ignore[arg-type]
    context = await SoapNoteService(db).gather(PATIENT, 30, access=access)
    prompt = build_soap_prompt(context)
    assert "Depression" not in str(context) and "Depression" not in prompt
    assert "Hypertension" in prompt
    assert "kept private by the patient" in prompt  # the generic marker only
    assert context["some_conditions_private"] is True
    assert [a["id"] for a in context["adr_assessments"]] == ["p"]  # pending only
    assert context["adherence_stats"]["obligation_log_count"] == 1  # other plan's logs left out
    assert context["allergies"][0]["allergen"] == "Penicillin"  # allergies are shared


@pytest.mark.asyncio
async def test_soap_context_for_the_owning_team_keeps_its_own_records() -> None:
    db = soap_world()
    access = CareTeamAccessService(db).for_patient(OTHER, PATIENT)  # type: ignore[arg-type]
    context = await SoapNoteService(db).gather(PATIENT, 30, access=access)
    assert {c["name"] for c in context["conditions"]} == {"Hypertension", "Depression"}
    assert context["some_conditions_private"] is False
    assert {a["id"] for a in context["adr_assessments"]} == {"p", "r"}
    assert context["adherence_stats"]["obligation_log_count"] == 6


@pytest.mark.asyncio
async def test_soap_note_is_saved_for_the_clinicians_exact_link() -> None:
    db = soap_world()
    service = SoapNoteService(db)
    with patch.object(service, "compose", AsyncMock(return_value=NOTE)):
        result = await service.generate(patient_id=PATIENT, clinician_id=CLINICIAN)
    assert result.status == "success"
    assert db.tables["soap_notes"][0]["care_team_id"] == TEAM
    assert db.tables["soap_notes"][0]["clinician_id"] == CLINICIAN


@pytest.mark.asyncio
async def test_soap_note_with_two_links_needs_a_choice_and_accepts_only_their_own() -> None:
    db = soap_world()
    two_links(db)
    service = SoapNoteService(db)
    with patch.object(service, "compose", AsyncMock(return_value=NOTE)):
        with pytest.raises(ValidationError) as ambiguous:
            await service.generate(patient_id=PATIENT, clinician_id=CLINICIAN)
        assert ambiguous.value.code == "CARE_TEAM_REQUIRED"
        assert db.tables.get("soap_notes", []) == []
        with pytest.raises(AuthorizationError):
            await service.generate(
                patient_id=PATIENT, clinician_id=CLINICIAN, care_team_id=str(uuid4())
            )
        await service.generate(patient_id=PATIENT, clinician_id=CLINICIAN, care_team_id=OTHER_TEAM)
    assert db.tables["soap_notes"][0]["care_team_id"] == OTHER_TEAM


@pytest.mark.asyncio
async def test_soap_note_for_an_unlinked_clinician_is_denied_and_nothing_is_read() -> None:
    db = soap_world()
    service = SoapNoteService(db)
    compose = AsyncMock(return_value=NOTE)
    with patch.object(service, "compose", compose), pytest.raises(AuthorizationError):
        await service.generate(patient_id=PATIENT, clinician_id=THIRD)
    compose.assert_not_awaited()
    assert not any(table == "conditions" for table, _, _ in db.queries)


# ── ADR assessments ─────────────────────────────────────────────────────────────────────


def adr_world() -> FakeDB:
    def adr(identifier: str, **extra: Any) -> dict[str, Any]:
        return {
            "id": identifier,
            "patient_id": PATIENT,
            "status": "draft",
            "reviewed_by": None,
            "reviewed_by_care_team_id": None,
            "created_at": f"2026-10-0{identifier[-1]}",
            "naranjo_assessment": {"missing_questions": []},
            **extra,
        }

    db = FakeDB(
        base_tables(
            adr_assessments=[
                adr("00000000-0000-4000-8000-000000000001"),
                adr(
                    "00000000-0000-4000-8000-000000000002",
                    status="reviewed",
                    reviewed_by=CLINICIAN,
                    reviewed_by_care_team_id=TEAM,
                ),
                adr(
                    "00000000-0000-4000-8000-000000000003",
                    status="reviewed",
                    reviewed_by=OTHER,
                    reviewed_by_care_team_id=OTHER_TEAM,
                ),
            ]
        )
    )

    def review(params: dict[str, Any]) -> list[dict[str, Any]]:
        row = next(r for r in db.tables["adr_assessments"] if r["id"] == params["p_assessment_id"])
        row.update(status="reviewed", reviewed_by=params["p_actor_id"])
        return [dict(row)]

    db.rpc_handlers["review_adr_assessment"] = review
    return db


def ids(result: dict[str, Any]) -> set[str]:
    return {item["id"][-1] for item in result["items"]}


@pytest.mark.asyncio
async def test_adr_queue_shows_pending_to_every_team_and_reviewed_to_its_team_only() -> None:
    db = adr_world()
    mine = await service_for(db).list_adr_review_queue(UUID(CLINICIAN), status_filter="all")
    theirs = await service_for(db).list_adr_review_queue(UUID(OTHER), status_filter="all")
    assert ids(mine) == {"1", "2"}
    assert ids(theirs) == {"1", "3"}


@pytest.mark.asyncio
async def test_adr_queue_with_two_links_shows_both_teams_reviews() -> None:
    db = adr_world()
    two_links(db)
    both = await service_for(db).list_adr_review_queue(UUID(CLINICIAN), status_filter="all")
    assert ids(both) == {"1", "2", "3"}


@pytest.mark.asyncio
async def test_adr_detail_of_another_teams_review_is_a_404() -> None:
    db = adr_world()
    service = service_for(db)
    assert (
        await service.get_adr_review_item(
            UUID(CLINICIAN), UUID("00000000-0000-4000-8000-000000000001")
        )
    )["id"].endswith("1")
    with pytest.raises(NotFoundError):
        await service.get_adr_review_item(
            UUID(CLINICIAN), UUID("00000000-0000-4000-8000-000000000003")
        )
    with pytest.raises(NotFoundError):
        await service.get_adr_review_item(UUID(THIRD), UUID("00000000-0000-4000-8000-000000000001"))


@pytest.mark.asyncio
async def test_reviewing_a_pending_assessment_stamps_the_reviewing_team() -> None:
    db = adr_world()
    decision = ADRReviewDecisionRequest(action=ADRReviewAction.MARK_REVIEWED, note="ok")
    first = UUID("00000000-0000-4000-8000-000000000001")
    await service_for(db).review_adr_assessment(UUID(OTHER), first, decision)
    row = next(r for r in db.tables["adr_assessments"] if r["id"].endswith("1"))
    assert (row["reviewed_by"], row["reviewed_by_care_team_id"]) == (OTHER, OTHER_TEAM)
    # afterwards it is the reviewing team's: the first team no longer sees it
    with pytest.raises(NotFoundError):
        await service_for(db).get_adr_review_item(UUID(CLINICIAN), first)


@pytest.mark.asyncio
async def test_another_teams_reviewed_assessment_cannot_be_acted_on() -> None:
    db = adr_world()
    decision = ADRReviewDecisionRequest(action=ADRReviewAction.MARK_REVIEWED, note="ok")
    with pytest.raises(NotFoundError):
        await service_for(db).review_adr_assessment(
            UUID(CLINICIAN), UUID("00000000-0000-4000-8000-000000000003"), decision
        )
    assert db.rpc_calls == []


@pytest.mark.asyncio
async def test_review_with_two_links_requires_a_choice() -> None:
    db = adr_world()
    two_links(db)
    first = UUID("00000000-0000-4000-8000-000000000001")
    with pytest.raises(ValidationError) as ambiguous:
        await service_for(db).review_adr_assessment(
            UUID(CLINICIAN),
            first,
            ADRReviewDecisionRequest(action=ADRReviewAction.MARK_REVIEWED, note="ok"),
        )
    assert ambiguous.value.code == "CARE_TEAM_REQUIRED"
    assert db.rpc_calls == []
    await service_for(db).review_adr_assessment(
        UUID(CLINICIAN),
        first,
        ADRReviewDecisionRequest(
            action=ADRReviewAction.MARK_REVIEWED, note="ok", care_team_id=UUID(OTHER_TEAM)
        ),
    )
    row = next(r for r in db.tables["adr_assessments"] if r["id"].endswith("1"))
    assert row["reviewed_by_care_team_id"] == OTHER_TEAM


@pytest.mark.asyncio
async def test_review_without_a_link_is_denied() -> None:
    db = adr_world()
    with pytest.raises(AuthorizationError):
        await service_for(db).review_adr_assessment(
            UUID(THIRD),
            UUID("00000000-0000-4000-8000-000000000001"),
            ADRReviewDecisionRequest(action=ADRReviewAction.MARK_REVIEWED, note="ok"),
        )
    assert db.rpc_calls == []


# ── Dashboard counts ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dashboard_counts_leave_out_other_teams_owned_items() -> None:
    db = adr_world()
    db.tables["medwatch_drafts"] = [
        {
            "id": "m1",
            "patient_id": PATIENT,
            "status": "draft",
            "discarded_at": None,
            "care_team_id": TEAM,
        },
        {
            "id": "m2",
            "patient_id": PATIENT,
            "status": "draft",
            "discarded_at": None,
            "care_team_id": OTHER_TEAM,
        },
        {
            "id": "m3",
            "patient_id": PATIENT,
            "status": "draft",
            "discarded_at": None,
            "care_team_id": None,
        },
    ]
    # An assessment another team already acted on while still a draft.
    db.tables["adr_assessments"].append(
        {
            "id": "00000000-0000-4000-8000-000000000004",
            "patient_id": PATIENT,
            "status": "draft",
            "reviewed_by": OTHER,
            "reviewed_by_care_team_id": OTHER_TEAM,
        }
    )
    service = service_for(db)
    for clinician, adr_count, draft_count in ((CLINICIAN, 1, 2), (OTHER, 2, 2)):
        links = service.care_access.for_clinician(clinician)
        assert await service._get_pending_adr_review_count([UUID(PATIENT)], links) == adr_count
        assert await service._get_pending_medwatch_count([UUID(PATIENT)], links) == draft_count


@pytest.mark.asyncio
async def test_dashboard_scores_each_patient_for_the_requesting_clinician() -> None:
    tables = plan_tables()
    tables["adherence_logs"] = [
        log("obligation", OB_THEIRS, "skipped", id=f"s{i}") for i in range(4)
    ] + [log("obligation", "eeeeeeee-0000-4000-8000-000000000004", "completed", id="c")]
    db = FakeDB(base_tables(**tables))
    service = service_for(db)
    mine = await service.get_dashboard_data(UUID(CLINICIAN))
    theirs = await service.get_dashboard_data(UUID(OTHER))
    assert mine["patients"][0]["adherence_score"] == 1.0
    assert theirs["patients"][0]["adherence_score"] == pytest.approx(0.2)


@pytest.mark.asyncio
async def test_patient_list_holds_only_the_clinicians_own_links() -> None:
    db = FakeDB(base_tables())
    db.tables["care_teams"][0]["patients"] = {"id": PATIENT, "first_name": "A"}
    db.tables["care_teams"][1]["patients"] = {"id": PATIENT, "first_name": "A"}
    service = service_for(db)
    mine = await service.get_patients(UUID(CLINICIAN))
    assert [p["care_team_id"] for p in mine] == [TEAM]
    assert await service.get_patients(UUID(THIRD)) == []


@pytest.mark.asyncio
async def test_sent_messages_are_the_requesting_clinicians_own() -> None:
    db = FakeDB(
        base_tables(
            clinician_messages=[
                {
                    "id": "m1",
                    "clinician_id": CLINICIAN,
                    "patient_id": PATIENT,
                    "body": "mine",
                    "created_at": "2026-10-01",
                },
                {
                    "id": "m2",
                    "clinician_id": OTHER,
                    "patient_id": PATIENT,
                    "body": "theirs",
                    "created_at": "2026-10-02",
                },
            ]
        )
    )
    service = service_for(db)
    assert [
        m["body"] for m in await service.list_patient_messages(UUID(CLINICIAN), UUID(PATIENT))
    ] == ["mine"]
    assert [m["body"] for m in await service.list_all_sent_messages(UUID(OTHER))] == ["theirs"]
    with pytest.raises(AuthorizationError):
        await service.list_patient_messages(UUID(THIRD), UUID(PATIENT))


# ── Timeline ────────────────────────────────────────────────────────────────────────────

T = "2026-10-05T08:00:00+00:00"
FACT_MINE, FACT_THEIRS = (
    "f0000000-0000-4000-8000-000000000001",
    "f0000000-0000-4000-8000-000000000002",
)


def timeline_world() -> FakeDB:
    tables = plan_tables()
    for version in tables["care_plan_versions"]:
        version["care_plan_versions.patient_id"] = PATIENT

    def doc(i: int, state: str, team: str | None) -> dict[str, Any]:
        return {
            "id": f"d0000000-0000-4000-8000-00000000000{i}",
            "patient_id": PATIENT,
            "created_at": T,
            "reviewed_at": T,
            "file_name": f"doc{i}.pdf",
            "review_status": "approved",
            "routing_state": state,
            "care_team_id": team,
        }

    def plan_event(i: int, version: str) -> dict[str, Any]:
        return {
            "id": f"e0000000-0000-4000-8000-00000000000{i}",
            "plan_version_id": version,
            "event_type": "approved",
            "created_at": T,
            "care_plan_versions.patient_id": PATIENT,
        }

    def adr_event(i: int, assessment: str) -> dict[str, Any]:
        return {
            "id": f"a0000000-0000-4000-8000-00000000000{i}",
            "adr_assessment_id": assessment,
            "event_type": "reviewed",
            "created_at": T,
            "adr_assessments.patient_id": PATIENT,
        }

    def fact_event(i: int, fact: str) -> dict[str, Any]:
        return {
            "id": f"c0000000-0000-4000-8000-00000000000{i}",
            "fact_id": fact,
            "event_type": "accepted",
            "created_at": T,
            "clinical_facts.patient_id": PATIENT,
        }

    tables.update(
        documents=[doc(1, "routed", TEAM), doc(2, "routed", OTHER_TEAM), doc(3, "unrouted", None)],
        appointments=[
            {
                "id": "b0000000-0000-4000-8000-000000000001",
                "patient_id": PATIENT,
                "care_team_id": TEAM,
                "created_at": T,
                "scheduled_at": T,
                "status": "confirmed",
                "appointment_type": "follow_up",
            },
            {
                "id": "b0000000-0000-4000-8000-000000000002",
                "patient_id": PATIENT,
                "care_team_id": OTHER_TEAM,
                "created_at": T,
                "scheduled_at": T,
                "status": "confirmed",
                "appointment_type": "follow_up",
            },
        ],
        care_plan_audit_events=[
            plan_event(1, "cccccccc-0000-4000-8000-000000000001"),
            plan_event(2, "cccccccc-0000-4000-8000-000000000002"),
        ],
        adr_assessment_audit_events=[
            adr_event(1, "1a000000-0000-4000-8000-000000000001"),
            adr_event(2, "1a000000-0000-4000-8000-000000000002"),
        ],
        adr_assessments=[
            {
                "id": "1a000000-0000-4000-8000-000000000001",
                "patient_id": PATIENT,
                "reviewed_by": CLINICIAN,
                "reviewed_by_care_team_id": TEAM,
            },
            {
                "id": "1a000000-0000-4000-8000-000000000002",
                "patient_id": PATIENT,
                "reviewed_by": OTHER,
                "reviewed_by_care_team_id": OTHER_TEAM,
            },
        ],
        clinical_fact_audit_events=[fact_event(1, FACT_MINE), fact_event(2, FACT_THEIRS)],
        evidence_citations=[
            {"fact_id": FACT_MINE, "provenance_id": "p1"},
            {"fact_id": FACT_THEIRS, "provenance_id": "p2"},
        ],
        source_provenances=[
            {"id": "p1", "document_id": "d0000000-0000-4000-8000-000000000001"},
            {"id": "p2", "document_id": "d0000000-0000-4000-8000-000000000002"},
        ],
        adherence_logs=[
            {
                **log("obligation", OB_THEIRS, "taken", id="theirs-log"),
                "id": "10000000-0000-4000-8000-000000000001",
            },
            {
                **log("obligation", "eeeeeeee-0000-4000-8000-000000000004", "taken"),
                "id": "10000000-0000-4000-8000-000000000002",
            },
        ],
        medications=[
            {
                "id": "20000000-0000-4000-8000-000000000001",
                "patient_id": PATIENT,
                "name": "Meloxicam",
                "created_at": T,
            }
        ],
        care_conversations=[],
    )
    db = FakeDB(base_tables(**tables))
    db.rpc_handlers["care_conversation_operation"] = lambda params: {"items": []}
    return db


async def timeline_for(db: FakeDB, clinician: str) -> dict[str, set[str]]:
    result = await PatientTimelineService(db, AsyncMock()).get_timeline(  # type: ignore[arg-type]
        UUID(clinician), UUID(PATIENT)
    )
    assert all(s.status == "available" for s in result.sources), [
        (s.source, s.status) for s in result.sources
    ]
    grouped: dict[str, set[str]] = {}
    for event in result.events:
        grouped.setdefault(event.source_table, set()).add(str(event.source_id)[-1])
    return grouped


@pytest.mark.asyncio
async def test_timeline_events_follow_the_owner_of_what_they_are_about() -> None:
    db = timeline_world()
    mine = await timeline_for(db, CLINICIAN)
    theirs = await timeline_for(db, OTHER)
    assert mine["documents"] == {"1", "3"} and theirs["documents"] == {"2", "3"}
    assert mine["appointments"] == {"1"} and theirs["appointments"] == {"2"}
    assert mine["care_plan_audit_events"] == {"1"} and theirs["care_plan_audit_events"] == {"2"}
    assert mine["adr_assessment_audit_events"] == {"1"}
    assert theirs["adr_assessment_audit_events"] == {"2"}
    assert mine["clinical_fact_audit_events"] == {"1"}
    assert theirs["clinical_fact_audit_events"] == {"2"}
    assert mine["adherence_logs"] == {"2"} and theirs["adherence_logs"] == {"1", "2"}
    assert mine["medications"] == theirs["medications"] == {"1"}  # shared


@pytest.mark.asyncio
async def test_timeline_with_two_links_shows_both_teams() -> None:
    db = timeline_world()
    two_links(db)
    both = await timeline_for(db, CLINICIAN)
    assert both["documents"] == {"1", "2", "3"}
    assert both["care_plan_audit_events"] == {"1", "2"}
    assert both["appointments"] == {"1", "2"}


@pytest.mark.asyncio
async def test_timeline_without_a_link_is_denied_by_the_gate() -> None:
    db = timeline_world()
    service = service_for(db)
    with pytest.raises(AuthorizationError):
        await service.get_patient_timeline(UUID(THIRD), UUID(PATIENT))


@pytest.mark.asyncio
async def test_timeline_marks_a_source_unavailable_when_ownership_cannot_be_checked() -> None:
    db = timeline_world()
    original = PatientTimelineService._fetch

    def broken(self: Any, table: str, columns: str, found: list[str]) -> Any:
        if table == "documents":
            raise RuntimeError("lookup failed")
        return original(self, table, columns, found)

    with patch.object(PatientTimelineService, "_fetch", broken):
        result = await PatientTimelineService(db, AsyncMock()).get_timeline(  # type: ignore[arg-type]
            UUID(CLINICIAN), UUID(PATIENT)
        )
    assert not any(e.source_table == "documents" for e in result.events)
    assert any(
        s.source.startswith("documents") and s.status == "unavailable" for s in result.sources
    )


# ── MedWatch ────────────────────────────────────────────────────────────────────────────

MW_OTHER_TEAM = "team-2"


def mw_world(**tables: list[dict[str, Any]]) -> FakeDB:
    db = _sources_db(**tables)
    db.tables["care_teams"].append(
        {
            "id": MW_OTHER_TEAM,
            "patient_id": mw.PATIENT_ID,
            "clinician_id": mw.OTHER_CLINICIAN_ID,
            "clinic_id": mw.CLINIC_ID,
            "clinic_name": None,
            "status": "active",
        }
    )
    return db


def mw_service(db: FakeDB) -> MedWatchService:
    return MedWatchService(db)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_medwatch_list_shows_a_draft_to_its_team_and_unowned_ones_to_all() -> None:
    mine = _draft_row(care_team_id="team-1")
    theirs = _draft_row(care_team_id=MW_OTHER_TEAM)
    unowned = _draft_row(care_team_id=None)
    db = mw_world(medwatch_drafts=[mine, theirs, unowned])
    scope = ClinicLinkScope({mw.PATIENT_ID: (mw.CLINIC_ID, "Synthetic")})
    with patch(
        "app.services.medwatch_service.ClinicMembershipService.link_scope",
        new=AsyncMock(return_value=scope),
    ):
        first = await mw_service(db).list_drafts(UUID(mw.CLINICIAN_ID))
        second = await mw_service(db).list_drafts(UUID(mw.OTHER_CLINICIAN_ID))
    assert {i["id"] for i in first["items"]} == {mine["id"], unowned["id"]}
    assert {i["id"] for i in second["items"]} == {theirs["id"], unowned["id"]}


@pytest.mark.asyncio
async def test_every_medwatch_action_on_another_teams_draft_is_a_404() -> None:
    theirs = _draft_row(care_team_id=MW_OTHER_TEAM)
    db = mw_world(medwatch_drafts=[theirs])
    service, me, draft = mw_service(db), UUID(mw.CLINICIAN_ID), UUID(theirs["id"])
    calls = [
        service.get_draft(me, draft),
        service.preview_pdf(me, draft),
        service.get_preview(me, draft),
        service.export_draft(me, draft),
        service.export_pdf(me, draft),
        service.approve_draft(me, draft, _approval()),
        service.discard_draft(
            me, draft, MedWatchDraftDiscardRequest(reason="x", expected_revision=1)
        ),
    ]
    for call in calls:
        with pytest.raises(NotFoundError):
            await call
    assert db.rpc_calls == []
    # the owning team's clinician reads it
    assert (await service.get_draft(UUID(mw.OTHER_CLINICIAN_ID), draft))["id"] == theirs["id"]


@pytest.mark.asyncio
async def test_creating_a_draft_stamps_the_assessment_and_draft_with_the_acting_team() -> None:
    db = mw_world()
    item = await mw_service(db).create_draft(
        UUID(mw.OTHER_CLINICIAN_ID),
        UUID(ASSESSMENT),
        MedWatchDraftCreateRequest(decision="prepare_draft", reportability_rationale="Signal."),
    )
    assert db.tables["medwatch_drafts"][0]["care_team_id"] == MW_OTHER_TEAM
    assessment = db.tables["adr_assessments"][0]
    assert assessment["reviewed_by_care_team_id"] == MW_OTHER_TEAM
    assert item["id"] == db.tables["medwatch_drafts"][0]["id"]


@pytest.mark.asyncio
async def test_creating_a_draft_with_two_links_requires_a_choice() -> None:
    db = mw_world()
    db.tables["care_teams"][1]["clinician_id"] = mw.CLINICIAN_ID
    request = MedWatchDraftCreateRequest(
        decision="prepare_draft", reportability_rationale="Signal."
    )
    with pytest.raises(ValidationError) as error:
        await mw_service(db).create_draft(UUID(mw.CLINICIAN_ID), UUID(ASSESSMENT), request)
    assert error.value.code == "CARE_TEAM_REQUIRED"
    assert db.rpc_calls == []


@pytest.mark.asyncio
async def test_a_draft_cannot_start_from_another_teams_reviewed_assessment() -> None:
    db = mw_world()
    db.tables["adr_assessments"][0].update(
        reviewed_by=mw.OTHER_CLINICIAN_ID, reviewed_by_care_team_id=MW_OTHER_TEAM, status="reviewed"
    )
    with pytest.raises(NotFoundError):
        await mw_service(db).create_draft(
            UUID(mw.CLINICIAN_ID),
            UUID(ASSESSMENT),
            MedWatchDraftCreateRequest(decision="prepare_draft", reportability_rationale="Signal."),
        )
    assert db.rpc_calls == []


@pytest.mark.asyncio
async def test_the_filed_form_never_carries_a_condition_kept_private_from_the_team() -> None:
    db = mw_world()
    db.tables["conditions"].append(
        {
            "patient_id": mw.PATIENT_ID,
            "name": "Depression",
            "status": "active",
            "is_sensitive": True,
            "recorded_by_care_team_id": MW_OTHER_TEAM,
        }
    )
    await mw_service(db).create_draft(
        UUID(mw.CLINICIAN_ID),
        UUID(ASSESSMENT),
        MedWatchDraftCreateRequest(decision="prepare_draft", reportability_rationale="Signal."),
    )
    [(_, payload)] = db.rpc_calls
    assert "Depression" not in str(payload)
    assert "Hypertension" in str(payload)


# ── Appointments and conversations (already scoped; pinned here) ────────────────────────


@pytest.mark.asyncio
async def test_appointment_list_holds_only_visits_at_the_clinicians_own_links() -> None:
    from app.services.appointment_service import AppointmentService

    other_clinic = "cccccccc-cccc-4ccc-8ccc-ccccccccccc9"
    db = FakeDB(
        {
            "appointments": [
                {
                    "id": "a1",
                    "patient_id": PATIENT,
                    "clinic_id": CLINIC,
                    "scheduled_at": "2026-10-20",
                },
                {
                    "id": "a2",
                    "patient_id": PATIENT,
                    "clinic_id": other_clinic,
                    "scheduled_at": "2026-10-21",
                },
            ]
        }
    )
    db.rpc_handlers["expire_appointment_proposals"] = lambda params: {}
    scope = ClinicLinkScope({PATIENT: (CLINIC, "Synthetic")})
    with patch(
        "app.services.appointment_service.ClinicMembershipService.link_scope",
        new=AsyncMock(return_value=scope),
    ):
        rows = await AppointmentService(db).list_for_user(  # type: ignore[arg-type]
            user_id=UUID(CLINICIAN), role="clinician"
        )
    assert [r["id"] for r in rows] == ["a1"]


@pytest.mark.asyncio
async def test_care_conversations_reach_the_database_as_the_acting_clinician_only() -> None:
    db = FakeDB()
    db.rpc_handlers["care_conversation_operation"] = lambda params: {"items": []}
    actor = SimpleNamespace(id=UUID(CLINICIAN), role="clinician")
    service = CareConversationService(db, actor)  # type: ignore[arg-type]
    service.recipients  # noqa: B018
    await service._call("list")
    [(name, params)] = db.rpc_calls
    assert name == "care_conversation_operation"
    assert params["p_actor_id"] == CLINICIAN and params["p_actor_role"] == "clinician"
