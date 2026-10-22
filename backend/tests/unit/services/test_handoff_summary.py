"""Care-handoff summary sections, service rules and FHIR export (CON-001). Synthetic data."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from postgrest.exceptions import APIError

from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from app.models.dashboard import PatientTimelineEvent, PatientTimelineResponse
from app.models.handoff import HandoffCreateRequest, HandoffDetail, HandoffSaveRequest
from app.services.care_team_access import CareTeamAccessService
from app.services.handoff_fhir_export import build_handoff_bundle
from app.services.handoff_summary_builder import HandoffSummaryBuilder
from app.services.handoff_summary_service import HandoffSummaryService
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

NOW = datetime.now(UTC)
ID = "99999999-0000-4000-8000-0000000000"
PLAN_MINE, PLAN_THEIRS = f"{ID}01", f"{ID}02"
VER_MINE, VER_THEIRS = f"{ID}11", f"{ID}12"
ITEM_MINE, ITEM_THEIRS = f"{ID}21", f"{ID}22"
MED_MINE = f"{ID}31"
MED_THEIRS = f"{ID}32"
OB_MINE, OB_THEIRS = f"{ID}41", f"{ID}42"
ADR_MINE, ADR_THEIRS, ADR_PENDING = f"{ID}51", f"{ID}52", f"{ID}53"
VISIT_MINE, VISIT_THEIRS = f"{ID}61", f"{ID}62"
SYMPTOM = f"{ID}71"
SUMMARY = uuid4()


def when(days: int) -> str:
    return (NOW + timedelta(days=days)).isoformat()


def tables() -> dict[str, list[dict[str, Any]]]:
    return {
        "patients": [
            {
                "id": PATIENT,
                "first_name": "Lucia",
                "last_name": "Synthetic",
                "date_of_birth": "1961-07-14",
                "preferred_language": "es-MX",
            }
        ],
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
        ],
        "care_plan_versions": [
            {
                "id": VER_MINE,
                "care_plan_id": PLAN_MINE,
                "status": "approved",
                "version_number": 3,
                "approved_at": when(-5),
            },
            {
                "id": VER_THEIRS,
                "care_plan_id": PLAN_THEIRS,
                "status": "approved",
                "version_number": 1,
                "approved_at": when(-4),
            },
        ],
        "care_plan_items": [
            {
                "id": ITEM_MINE,
                "plan_version_id": VER_MINE,
                "title": "Walk after meals",
                "frequency": "daily",
                "instructions": "Ten minutes",
                "is_removed": False,
                "created_at": when(-5),
            },
            {
                "id": ITEM_THEIRS,
                "plan_version_id": VER_THEIRS,
                "title": "Ankle exercises",
                "frequency": "daily",
                "instructions": "Orthopaedic secret plan",
                "is_removed": False,
                "created_at": when(-4),
            },
        ],
        "obligations": [
            {"id": OB_MINE, "patient_id": PATIENT, "care_plan_item_id": ITEM_MINE},
            {"id": OB_THEIRS, "patient_id": PATIENT, "care_plan_item_id": ITEM_THEIRS},
        ],
        "medications": [
            {"id": MED_MINE, "patient_id": PATIENT, "care_plan_item_id": None},
            {"id": MED_THEIRS, "patient_id": PATIENT, "care_plan_item_id": ITEM_THEIRS},
        ],
        "adherence_logs": [
            {
                "id": "log-1",
                "patient_id": PATIENT,
                "target_type": "obligation",
                "target_id": OB_MINE,
                "status": "completed",
                "logged_at": when(-1),
            },
            {
                "id": "log-2",
                "patient_id": PATIENT,
                "target_type": "obligation",
                "target_id": OB_MINE,
                "status": "missed",
                "logged_at": when(-2),
            },
            {
                "id": "log-3",
                "patient_id": PATIENT,
                "target_type": "obligation",
                "target_id": OB_THEIRS,
                "status": "missed",
                "logged_at": when(-2),
            },
        ],
        "symptom_reports": [
            {
                "id": SYMPTOM,
                "patient_id": PATIENT,
                "symptom": "Ankle swelling",
                "severity": 4,
                "created_at": when(-3),
                "confirmation_state": "patient_confirmed",
            },
            {
                "id": f"{ID}72",
                "patient_id": PATIENT,
                "symptom": "Unconfirmed guess",
                "severity": 9,
                "created_at": when(-3),
                "confirmation_state": "legacy_unconfirmed",
            },
        ],
        "adr_assessments": [
            _adr(ADR_MINE, "Lisinopril", TEAM),
            _adr(ADR_THEIRS, "Meloxicam", OTHER_TEAM),
            _adr(ADR_PENDING, "Pending drug", None),
        ],
        "appointments": [
            _visit(VISIT_MINE, TEAM, 7),
            _visit(VISIT_THEIRS, OTHER_TEAM, 8),
            {**_visit(f"{ID}63", TEAM, -7)},
        ],
    }


def _adr(adr_id: str, drug: str, team: str | None) -> dict[str, Any]:
    return {
        "id": adr_id,
        "patient_id": PATIENT,
        "suspect_medication_name": drug,
        "causality": "possible",
        "naranjo_score": 5,
        "status": "reviewed" if team else "draft",
        "reviewed_by": (CLINICIAN if team == TEAM else OTHER) if team else None,
        "reviewed_by_care_team_id": team,
        "created_at": when(-6),
    }


def _visit(visit_id: str, team: str, days: int) -> dict[str, Any]:
    return {
        "id": visit_id,
        "patient_id": PATIENT,
        "care_team_id": team,
        "scheduled_at": when(days),
        "status": "scheduled",
        "appointment_type": "follow_up",
    }


def shared_core(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "medications": [
            {
                "id": MED_MINE,
                "name": "Lisinopril",
                "dosage": "10 mg",
                "frequency": "daily",
                "recorded_by": "Elena Park",
                "recorded_by_care_team_id": TEAM,
            }
        ],
        "allergies": [
            {
                "id": f"{ID}81",
                "allergen": "Penicillin",
                "reaction": "Rash",
                "severity": "moderate",
                "recorded_by_care_team_id": OTHER_TEAM,
            }
        ],
        "conditions": [{"id": f"{ID}91", "name": "Hypertension", "recorded_by_care_team_id": TEAM}],
        "some_conditions_private": True,
        "care_teams": [
            {"care_team_id": TEAM, "clinician_name": "Elena Park", "clinic_name": "Valley"},
            {
                "care_team_id": OTHER_TEAM,
                "clinician_name": "Omar Synthetic",
                "clinic_name": "Elsewhere",
            },
        ],
    }


def make_db(extra_links: bool = False, **overrides: list[dict[str, Any]]) -> FakeDB:
    data = tables()
    data.update(overrides)
    db = FakeDB(data)
    db.rpc_handlers["shared_clinical_summary"] = shared_core
    if extra_links:
        db.tables["care_teams"].append(
            {
                "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa9",
                "patient_id": PATIENT,
                "clinician_id": CLINICIAN,
                "clinic_id": CLINIC,
                "status": "active",
                "role": "specialist",
            }
        )
    return db


def timeline(*events: PatientTimelineEvent, unavailable: tuple[str, ...] = ()):
    from app.models.dashboard import TimelineSourceCoverage

    return PatientTimelineResponse(
        patient_id=UUID(PATIENT),
        retrieved_at=NOW,
        events=list(events),
        sources=[
            TimelineSourceCoverage(source=name, status="unavailable", limit=40)
            for name in unavailable
        ],
    )


def event(domain: str, table: str, title: str) -> PatientTimelineEvent:
    source_id = uuid4()
    return PatientTimelineEvent(
        id=f"{table}-created_at-{source_id}",
        domain=domain,
        source_table=table,
        source_id=source_id,
        occurred_at=NOW - timedelta(days=1),
        timestamp_label="Recorded",
        title=title,
        details={"name": "Lisinopril"},
        source_href=f"/patients/{PATIENT}?tab=timeline#source-{table}",
    )


async def allow(_clinician: UUID, _patient: UUID) -> None:
    return None


def service(db: FakeDB) -> HandoffSummaryService:
    return HandoffSummaryService(db, allow)  # type: ignore[arg-type]


def patched_timeline(response: PatientTimelineResponse | None = None):
    return patch(
        "app.services.handoff_summary_builder.PatientTimelineService.get_timeline",
        new=AsyncMock(
            return_value=response
            or timeline(event("medication", "medications", "Medication recorded"))
        ),
    )


async def build(db: FakeDB, response: PatientTimelineResponse | None = None):
    access = CareTeamAccessService(db).for_patient(CLINICIAN, PATIENT)  # type: ignore[arg-type]
    with patched_timeline(response):
        return await HandoffSummaryBuilder(db, allow).build(  # type: ignore[arg-type]
            UUID(CLINICIAN), UUID(PATIENT), TEAM, access
        )


def by_key(sections):
    return {s.key: s for s in sections}


# ── deterministic sections ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sections_hold_the_authors_team_and_shared_records_only() -> None:
    sections = by_key(await build(make_db()))
    rendered = json.dumps([s.model_dump(mode="json") for s in sections.values()])

    assert "Walk after meals" in rendered
    assert "Lisinopril" in rendered and "Penicillin" in rendered and "Hypertension" in rendered
    assert "Ankle swelling" in rendered
    for other_team_only in (
        "Ankle exercises",
        "Orthopaedic secret plan",
        "Meloxicam",
        "Pending drug",
        VISIT_THEIRS,
        "Unconfirmed guess",
    ):
        assert other_team_only not in rendered
    assert [i.id for i in sections["upcoming_visits"].items] == [f"appointments-{VISIT_MINE}"]
    assert [i.source.id for i in sections["open_adr"].items] == [ADR_MINE]
    # 1 completed + 1 missed of my team's activity; the other team's missed log is not counted.
    assert "2 responses" in sections["team_activity"].items[0].text
    assert "1 missed" in sections["team_activity"].items[0].text


@pytest.mark.asyncio
async def test_private_conditions_are_a_marker_never_a_name() -> None:
    sections = by_key(await build(make_db()))
    texts = [i.text for i in sections["shared_core"].items]
    assert "Some conditions are private and are not included in this summary." in texts
    marker = next(i for i in sections["shared_core"].items if i.id == "conditions-private-marker")
    assert marker.source.kind == "rule"


@pytest.mark.asyncio
async def test_every_line_names_its_source_and_recording_team() -> None:
    sections = await build(make_db())
    for section in sections:
        for item in section.items:
            assert item.source.label
            if item.source.kind == "record":
                assert item.source.table
    allergy = next(
        i
        for s in sections
        if s.key == "shared_core"
        for i in s.items
        if i.id.startswith("allergies")
    )
    assert "Omar Synthetic" in allergy.source.label and "Elsewhere" in allergy.source.label


@pytest.mark.asyncio
async def test_empty_patient_reports_empty_sections_not_missing_ones() -> None:
    empty = {name: [] for name in tables()}
    empty["patients"] = tables()["patients"]
    db = make_db(**empty)
    db.rpc_handlers["shared_clinical_summary"] = lambda _p: {
        "medications": [],
        "allergies": [],
        "conditions": [],
        "some_conditions_private": False,
        "care_teams": [],
    }
    sections = by_key(await build(db, timeline()))
    assert sections["patient"].status == "available"
    for key in (
        "shared_core",
        "team_plan",
        "team_activity",
        "symptoms",
        "open_adr",
        "upcoming_visits",
        "timeline",
    ):
        assert sections[key].status == "empty" and sections[key].note and not sections[key].items


@pytest.mark.asyncio
async def test_a_failed_read_is_unavailable_not_empty() -> None:
    db = make_db()
    original = db.table

    def table(name: str):
        if name == "symptom_reports":
            raise RuntimeError("boom with Lucia's chart text")
        return original(name)

    db.table = table  # type: ignore[method-assign]
    sections = by_key(await build(db))
    assert sections["symptoms"].status == "unavailable"
    assert "Lucia" not in (sections["symptoms"].note or "")
    assert sections["shared_core"].status == "available"


@pytest.mark.asyncio
async def test_timeline_highlights_leave_out_private_threads_and_flag_gaps() -> None:
    response = timeline(
        event("message", "care_conversation_messages", "Private message"),
        event("medication", "medications", "Medication recorded"),
        unavailable=("adherence_logs.logged_at",),
    )
    section = by_key(await build(make_db(), response))["timeline"]
    assert [i.source.table for i in section.items] == ["medications"]
    assert "adherence_logs.logged_at" in (section.note or "")


@pytest.mark.asyncio
async def test_the_timeline_section_is_unavailable_when_the_timeline_fails() -> None:
    db = make_db()
    access = CareTeamAccessService(db).for_patient(CLINICIAN, PATIENT)  # type: ignore[arg-type]
    with patch(
        "app.services.handoff_summary_builder.PatientTimelineService.get_timeline",
        new=AsyncMock(side_effect=RuntimeError("down")),
    ):
        sections = await HandoffSummaryBuilder(db, allow).build(  # type: ignore[arg-type]
            UUID(CLINICIAN), UUID(PATIENT), TEAM, access
        )
    assert by_key(sections)["timeline"].status == "unavailable"


# ── service rules ───────────────────────────────────────────────────────────────────────


def create_handler(db: FakeDB):
    def handler(params: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": params["p_summary_id"],
            "patient_id": params["p_patient_id"],
            "care_team_id": params["p_care_team_id"],
            "author_id": params["p_actor_id"],
            "title": params["p_title"],
            "purpose": params["p_purpose"],
            "recipient_label": params["p_recipient_label"],
            "status": "draft",
            "current_version": 1,
            "created_at": NOW.isoformat(),
            "updated_at": NOW.isoformat(),
            "replayed": False,
        }

    db.rpc_handlers["create_care_handoff_summary"] = handler


@pytest.mark.asyncio
async def test_create_builds_deterministic_sections_for_the_authors_team() -> None:
    db = make_db()
    create_handler(db)
    with patched_timeline():
        header = await service(db).create(
            UUID(CLINICIAN), UUID(PATIENT), HandoffCreateRequest(purpose="transition")
        )
    assert header.status == "draft" and header.title == "Transition-of-care summary"
    (_, params) = db.rpc_calls[-1]
    assert params["p_care_team_id"] == TEAM and params["p_actor_id"] == CLINICIAN
    assert {s["key"] for s in params["p_sections"]} >= {"shared_core", "team_plan", "timeline"}


@pytest.mark.asyncio
async def test_an_unassigned_clinician_cannot_build_anything() -> None:
    db = make_db()
    create_handler(db)
    with patched_timeline() as timeline_call, pytest.raises(AuthorizationError) as denied:
        await service(db).create(
            UUID(THIRD), UUID(PATIENT), HandoffCreateRequest(purpose="colleague")
        )
    assert denied.value.reason_code == "NO_CARE_TEAM_ASSIGNMENT"
    assert not db.rpc_calls
    timeline_call.assert_not_called()
    assert {name for name, *_ in db.queries} == {"care_teams"}


@pytest.mark.asyncio
async def test_two_links_require_a_choice_and_a_foreign_team_is_refused() -> None:
    db = make_db(extra_links=True)
    create_handler(db)
    with pytest.raises(ValidationError) as needed:
        await service(db).create(
            UUID(CLINICIAN), UUID(PATIENT), HandoffCreateRequest(purpose="colleague")
        )
    assert needed.value.code == "CARE_TEAM_REQUIRED"
    with pytest.raises(AuthorizationError):
        await service(db).create(
            UUID(CLINICIAN),
            UUID(PATIENT),
            HandoffCreateRequest(purpose="colleague", care_team_id=UUID(OTHER_TEAM)),
        )
    assert not db.rpc_calls


def api_error(code: str, message: str = "x", hint: str | None = None) -> APIError:
    return APIError({"message": message, "code": code, "hint": hint, "details": None})


def detail_payload(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": str(SUMMARY),
        "patient_id": PATIENT,
        "care_team_id": TEAM,
        "author_id": CLINICIAN,
        "title": "Handoff",
        "purpose": "colleague",
        "recipient_label": "Dr. Rivera",
        "status": "draft",
        "current_version": 2,
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
        "version": {
            "version": 2,
            "sections": [
                {
                    "key": "shared_core",
                    "title": "Shared record",
                    "status": "available",
                    "items": [
                        {
                            "id": "medications-1",
                            "text": "Medication: Lisinopril",
                            "source": {
                                "kind": "record",
                                "table": "medications",
                                "id": MED_MINE,
                                "label": "Recorded by Elena Park",
                            },
                        }
                    ],
                }
            ],
            "narrative": "Stable on current plan.",
            "notes": None,
            "built_at": NOW.isoformat(),
            "created_by": CLINICIAN,
            "created_at": NOW.isoformat(),
        },
        "versions": [{"version": 2, "created_by": CLINICIAN, "created_at": NOW.isoformat()}],
        "events": [],
    }
    base.update(overrides)
    return base


def approved_payload() -> dict[str, Any]:
    return detail_payload(
        status="approved",
        approved_version=2,
        approved_by=CLINICIAN,
        approved_at=NOW.isoformat(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (api_error("42501"), NotFoundError),
        (api_error("40001", "HANDOFF_VERSION_CONFLICT: changed"), ConflictError),
        (api_error("22023", "HANDOFF_NOT_APPROVED: no", "HANDOFF_NOT_APPROVED"), ValidationError),
    ],
)
async def test_database_answers_become_the_right_http_errors(error, expected) -> None:
    db = make_db()
    db.rpc_handlers["read_care_handoff_summary"] = lambda _p: detail_payload()

    def fail(_p: dict[str, Any]) -> Any:
        raise error

    db.rpc_handlers["save_care_handoff_version"] = fail
    db.rpc_handlers["approve_care_handoff_summary"] = fail
    db.rpc_handlers["record_care_handoff_export"] = fail
    svc = service(db)
    save = HandoffSaveRequest(expected_version=2, narrative="n")
    with pytest.raises(expected):
        await svc.save(UUID(CLINICIAN), UUID(PATIENT), SUMMARY, save)
    with pytest.raises(expected):
        await svc.approve(UUID(CLINICIAN), UUID(PATIENT), SUMMARY, 2)
    with pytest.raises(expected):
        await svc.export(UUID(CLINICIAN), UUID(PATIENT), SUMMARY, 2, "print")


@pytest.mark.asyncio
async def test_a_summary_of_another_patient_or_team_reads_as_not_found() -> None:
    db = make_db()

    def other_patient(_p: dict[str, Any]) -> Any:
        return detail_payload(patient_id=str(uuid4()))

    db.rpc_handlers["read_care_handoff_summary"] = other_patient
    with pytest.raises(NotFoundError):
        await service(db).get(UUID(CLINICIAN), UUID(PATIENT), SUMMARY)

    def unavailable(_p: dict[str, Any]) -> Any:
        raise api_error("42501")

    db.rpc_handlers["read_care_handoff_summary"] = unavailable
    with pytest.raises(NotFoundError):
        await service(db).get(UUID(OTHER), UUID(PATIENT), SUMMARY)


@pytest.mark.asyncio
async def test_a_clinician_with_no_link_is_denied_before_any_summary_read() -> None:
    db = make_db()
    db.rpc_handlers["read_care_handoff_summary"] = lambda _p: detail_payload()
    for call in (
        service(db).get(UUID(THIRD), UUID(PATIENT), SUMMARY),
        service(db).list(UUID(THIRD), UUID(PATIENT)),
        service(db).approve(UUID(THIRD), UUID(PATIENT), SUMMARY, 2),
        service(db).export(UUID(THIRD), UUID(PATIENT), SUMMARY, 2, "fhir"),
        service(db).save(
            UUID(THIRD), UUID(PATIENT), SUMMARY, HandoffSaveRequest(expected_version=1)
        ),
    ):
        with pytest.raises(AuthorizationError):
            await call
    assert not db.rpc_calls


@pytest.mark.asyncio
async def test_approval_is_refused_while_a_section_is_unavailable() -> None:
    db = make_db()
    payload = detail_payload()
    payload["version"]["sections"][0]["status"] = "unavailable"
    payload["version"]["sections"][0]["items"] = []
    db.rpc_handlers["read_care_handoff_summary"] = lambda _p: payload
    db.rpc_handlers["approve_care_handoff_summary"] = lambda _p: payload
    with pytest.raises(ValidationError) as refused:
        await service(db).approve(UUID(CLINICIAN), UUID(PATIENT), SUMMARY, 2)
    assert refused.value.code == "HANDOFF_SECTION_UNAVAILABLE"
    assert all(name != "approve_care_handoff_summary" for name, _ in db.rpc_calls)


@pytest.mark.asyncio
async def test_refresh_rebuilds_sections_for_the_summarys_own_team() -> None:
    db = make_db()
    db.rpc_handlers["read_care_handoff_summary"] = lambda _p: detail_payload()
    db.rpc_handlers["save_care_handoff_version"] = lambda _p: {}
    with patched_timeline():
        await service(db).save(
            UUID(CLINICIAN),
            UUID(PATIENT),
            SUMMARY,
            HandoffSaveRequest(expected_version=2, refresh=True),
        )
    saves = [p for name, p in db.rpc_calls if name == "save_care_handoff_version"]
    assert saves[0]["p_sections"] and saves[0]["p_expected_version"] == 2


# ── export ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fhir_export_is_a_valid_document_bundle_with_provenance() -> None:
    db = make_db()
    db.rpc_handlers["read_care_handoff_summary"] = lambda _p: approved_payload()
    db.rpc_handlers["record_care_handoff_export"] = lambda _p: approved_payload()
    result = await service(db).export(UUID(CLINICIAN), UUID(PATIENT), SUMMARY, 2, "fhir")
    bundle = result.bundle
    assert bundle and bundle["type"] == "document"
    kinds = [e["resource"]["resourceType"] for e in bundle["entry"]]
    assert kinds[0] == "Composition" and "Provenance" in kinds and "Patient" in kinds
    composition = bundle["entry"][0]["resource"]
    assert composition["status"] == "final"
    assert composition["section"][0]["entry"][0]["identifier"]["value"] == f"medications/{MED_MINE}"
    provenance = next(
        e["resource"] for e in bundle["entry"] if e["resource"]["resourceType"] == "Provenance"
    )
    assert provenance["entity"][0]["what"]["identifier"]["value"] == f"medications/{MED_MINE}"
    assert "Stable on current plan." in json.dumps(composition)
    assert [name for name, _ in db.rpc_calls].count("record_care_handoff_export") == 1


@pytest.mark.asyncio
async def test_printable_export_carries_no_bundle_and_is_still_audited() -> None:
    db = make_db()
    db.rpc_handlers["read_care_handoff_summary"] = lambda _p: approved_payload()
    db.rpc_handlers["record_care_handoff_export"] = lambda _p: approved_payload()
    result = await service(db).export(UUID(CLINICIAN), UUID(PATIENT), SUMMARY, 2, "print")
    assert result.bundle is None
    assert db.rpc_calls[-1][1]["p_format"] == "print"


def test_a_draft_cannot_be_turned_into_a_bundle() -> None:
    draft = HandoffDetail.model_validate(detail_payload())
    with pytest.raises(ValueError):
        build_handoff_bundle(draft, patient={"first_name": "L", "last_name": "S"})
