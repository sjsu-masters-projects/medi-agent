"""Clinician reads and writes of care-team-owned records stay with the owning team.

Documents, the facts extracted from them, FHIR imports and their review/audit/reconciliation
paths belong to ONE care team; a "Not sure" document is visible to every active team until it
is claimed. Every test here fails if the ownership check on its path is removed. Synthetic data.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.config import settings
from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.models.clinical_fact import (
    ClinicalFactCreate,
    ClinicalFactReviewState,
    SourceArtifactType,
    SourceProvenanceCreate,
)
from app.models.reconciliation import ReconciliationDecisionRequest
from app.services.clinic_link_scope import ClinicLinkScope
from app.services.clinical_fact_service import ClinicalFactService
from app.services.clinical_reconciliation_service import ClinicalReconciliationService
from app.services.clinician_document_workflow_service import ClinicianDocumentWorkflowService
from app.services.clinician_record_gate import ClinicianFactService, ClinicianRecordGate
from app.services.document_service import DocumentService
from app.services.external_record_review_service import ExternalRecordReviewService
from app.services.fhir_audit_export_service import FhirAuditExportService
from app.services.fhir_import_review_service import FhirImportReviewService
from app.services.fhir_import_service import FhirImportService
from app.services.smart_launch_service import SmartLaunchService
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
    standard_links,
)

TWO = "55555555-5555-4555-8555-555555555555"
TWO_A = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1"
TWO_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2"

DOC_MINE, DOC_THEIRS, DOC_OPEN, DOC_TWO_B = (
    f"dddddddd-dddd-4ddd-8ddd-ddddddddddd{n}" for n in "1234"
)
F_MINE, F_THEIRS, F_OPEN, F_MIXED, F_IMP_MINE, F_IMP_THEIRS, F_IMP_LEGACY = (
    f"ffffffff-ffff-4fff-8fff-fffffffffff{n}" for n in "1234567"
)
IMP_MINE, IMP_THEIRS, IMP_LEGACY = (f"eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee{n}" for n in "123")
RES_MINE, RES_THEIRS, RES_LEGACY = (f"99999999-9999-4999-8999-99999999999{n}" for n in "123")


async def passthrough(query: Any) -> Any:
    return query.execute()


def _doc(doc_id: str, team: str | None, state: str = "routed") -> dict[str, Any]:
    return {
        "id": doc_id,
        "patient_id": PATIENT,
        "uploaded_by": PATIENT,
        "uploaded_by_role": "patient",
        "file_name": f"{doc_id[-1]}.pdf",
        "document_type": "lab_report",
        "parse_status": "completed",
        "review_status": "pending",
        "reviewed_by": None,
        "created_at": f"2026-10-0{doc_id[-1]}T10:00:00Z",
        "routing_state": state,
        "care_team_id": team,
    }


def _fact(fact_id: str, fact_type: str = "medication", **extra: Any) -> dict[str, Any]:
    return {
        "id": fact_id,
        "patient_id": PATIENT,
        "fact_type": fact_type,
        "subject_type": fact_type,
        "value": {"name": "Metformin"},
        "review_state": "pending_review",
        "reconciliation_state": "not_started",
        "created_at": "2026-10-01T10:00:00Z",
        **extra,
    }


def _links() -> list[dict[str, Any]]:
    return standard_links() + [
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


def _world() -> FakeDB:
    """Cardiology (CLINICIAN/TEAM), orthopaedics (OTHER/OTHER_TEAM), TWO with two links."""
    citations = [
        (F_MINE, "p-mine"),
        (F_THEIRS, "p-theirs"),
        (F_OPEN, "p-open"),
        (F_MIXED, "p-mine"),
        (F_MIXED, "p-theirs"),
        (F_IMP_MINE, "p-imp-mine"),
        (F_IMP_THEIRS, "p-imp-theirs"),
        (F_IMP_LEGACY, "p-imp-legacy"),
    ]
    return FakeDB(
        {
            "care_teams": _links(),
            "documents": [
                _doc(DOC_MINE, TEAM),
                _doc(DOC_THEIRS, OTHER_TEAM),
                _doc(DOC_OPEN, None, "unrouted"),
                _doc(DOC_TWO_B, TWO_B),
            ],
            "clinical_facts": [
                _fact(F_MINE),
                _fact(F_THEIRS),
                _fact(F_OPEN),
                _fact(F_MIXED),
                _fact(F_IMP_MINE),
                _fact(F_IMP_THEIRS),
                _fact(F_IMP_LEGACY),
            ],
            "source_provenances": [
                {"id": "p-mine", "document_id": DOC_MINE, "care_team_id": None},
                {"id": "p-theirs", "document_id": DOC_THEIRS, "care_team_id": None},
                {"id": "p-open", "document_id": DOC_OPEN, "care_team_id": None},
                {
                    "id": "p-imp-mine",
                    "document_id": None,
                    "care_team_id": TEAM,
                    "source_reference": f"fhir_import_resources/{RES_MINE}",
                },
                {
                    "id": "p-imp-theirs",
                    "document_id": None,
                    "care_team_id": OTHER_TEAM,
                    "source_reference": f"fhir_import_resources/{RES_THEIRS}",
                },
                # Written before provenance carried a team: the import row is the owner.
                {
                    "id": "p-imp-legacy",
                    "document_id": None,
                    "care_team_id": None,
                    "source_reference": f"fhir_import_resources/{RES_LEGACY}",
                },
            ],
            "evidence_citations": [
                {"id": str(uuid4()), "fact_id": fact, "provenance_id": provenance}
                for fact, provenance in citations
            ],
            "fhir_imports": [
                {
                    "id": IMP_MINE,
                    "patient_id": PATIENT,
                    "clinician_id": CLINICIAN,
                    "care_team_id": TEAM,
                },
                {
                    "id": IMP_THEIRS,
                    "patient_id": PATIENT,
                    "clinician_id": OTHER,
                    "care_team_id": OTHER_TEAM,
                },
                {
                    "id": IMP_LEGACY,
                    "patient_id": PATIENT,
                    "clinician_id": OTHER,
                    "care_team_id": None,
                },
            ],
            "fhir_import_resources": [
                {
                    "id": RES_MINE,
                    "import_id": IMP_MINE,
                    "issuer": "https://sandbox.example/fhir",
                    "resource_type": "MedicationRequest",
                    "external_resource_id": "m1",
                    "raw_resource": {"id": "m1"},
                },
                {
                    "id": RES_THEIRS,
                    "import_id": IMP_THEIRS,
                    "issuer": "https://sandbox.example/fhir",
                    "resource_type": "MedicationRequest",
                    "external_resource_id": "m2",
                    "raw_resource": {"id": "m2"},
                },
                {
                    "id": RES_LEGACY,
                    "import_id": IMP_LEGACY,
                    "issuer": "https://sandbox.example/fhir",
                    "resource_type": "MedicationRequest",
                    "external_resource_id": "m3",
                    "raw_resource": {"id": "m3"},
                },
            ],
            "clinical_fact_audit_events": [
                {
                    "id": str(uuid4()),
                    "fact_id": F_THEIRS,
                    "actor_id": OTHER,
                    "event_type": "created",
                    "created_at": "2026-10-01T10:00:00Z",
                },
                {
                    "id": str(uuid4()),
                    "fact_id": F_MINE,
                    "actor_id": CLINICIAN,
                    "event_type": "created",
                    "created_at": "2026-10-01T10:00:00Z",
                },
            ],
        }
    )


def _ids(rows: list[dict[str, Any]]) -> set[str]:
    return {str(row["id"]) for row in rows}


# ── The shared gate ────────────────────────────────────────────────────────────────────


def test_gate_document_hides_another_teams_routed_document() -> None:
    gate = ClinicianRecordGate(_world())
    assert gate.document(CLINICIAN, PATIENT, DOC_MINE)["id"] == DOC_MINE
    with pytest.raises(NotFoundError):
        gate.document(CLINICIAN, PATIENT, DOC_THEIRS)
    with pytest.raises(NotFoundError):
        gate.document(OTHER, PATIENT, DOC_MINE)


def test_gate_document_shows_an_unrouted_document_to_every_active_team() -> None:
    gate = ClinicianRecordGate(_world())
    for clinician in (CLINICIAN, OTHER, TWO):
        assert gate.document(clinician, PATIENT, DOC_OPEN)["routing_state"] == "unrouted"


def test_gate_document_refuses_a_clinician_with_no_link() -> None:
    with pytest.raises(AuthorizationError):
        ClinicianRecordGate(_world()).document(THIRD, PATIENT, DOC_OPEN)


def test_gate_document_lets_a_two_link_clinician_see_both_teams_documents() -> None:
    gate = ClinicianRecordGate(_world())
    assert gate.document(TWO, PATIENT, DOC_TWO_B)["id"] == DOC_TWO_B
    with pytest.raises(NotFoundError):
        gate.document(TWO, PATIENT, DOC_MINE)


def test_gate_document_asks_for_owner_columns_even_with_a_narrow_select() -> None:
    db = _world()
    ClinicianRecordGate(db).document(CLINICIAN, PATIENT, DOC_MINE, columns="id")
    assert ("documents", "select", [("eq", "id", DOC_MINE), ("eq", "patient_id", PATIENT)]) in [
        (table, kind, filters) for table, kind, filters in db.queries
    ]


def test_gate_fact_follows_every_source_behind_the_fact() -> None:
    gate = ClinicianRecordGate(_world())
    for visible in (F_MINE, F_OPEN, F_IMP_MINE, F_IMP_LEGACY):
        gate.fact(CLINICIAN, PATIENT, visible)
    for hidden in (F_THEIRS, F_IMP_THEIRS, F_MIXED):
        with pytest.raises(NotFoundError):
            gate.fact(CLINICIAN, PATIENT, hidden)


def test_gate_fact_refuses_no_link_and_unknown_facts() -> None:
    gate = ClinicianRecordGate(_world())
    with pytest.raises(AuthorizationError):
        gate.fact(THIRD, PATIENT, F_OPEN)
    with pytest.raises(NotFoundError):
        gate.fact(CLINICIAN, PATIENT, str(uuid4()))


def test_gate_import_follows_its_team_or_its_importing_clinician() -> None:
    gate = ClinicianRecordGate(_world())
    assert gate.fhir_import(CLINICIAN, PATIENT, IMP_MINE)["id"] == IMP_MINE
    with pytest.raises(NotFoundError):
        gate.fhir_import(CLINICIAN, PATIENT, IMP_THEIRS)
    with pytest.raises(NotFoundError):
        gate.fhir_import(CLINICIAN, PATIENT, IMP_LEGACY)  # no team, and OTHER imported it
    assert gate.fhir_import(OTHER, PATIENT, IMP_LEGACY)["id"] == IMP_LEGACY
    with pytest.raises(AuthorizationError):
        gate.fhir_import(THIRD, PATIENT, IMP_MINE)


def test_clinician_fact_service_gates_every_read_and_write() -> None:
    db = _world()
    service = ClinicianFactService(db)
    assert (
        service.lineage(
            clinician_id=UUID(CLINICIAN), patient_id=UUID(PATIENT), fact_id=UUID(F_MINE)
        )["fact"]["id"]
        == F_MINE
    )
    calls: list[Any] = [
        lambda: service.get_fact(
            clinician_id=UUID(CLINICIAN), patient_id=UUID(PATIENT), fact_id=UUID(F_THEIRS)
        ),
        lambda: service.lineage(
            clinician_id=UUID(CLINICIAN), patient_id=UUID(PATIENT), fact_id=UUID(F_THEIRS)
        ),
        lambda: service.reject(
            clinician_id=UUID(CLINICIAN),
            patient_id=UUID(PATIENT),
            fact_id=UUID(F_THEIRS),
            note="no",
        ),
        lambda: service.correct(
            clinician_id=UUID(CLINICIAN),
            patient_id=UUID(PATIENT),
            fact_id=UUID(F_THEIRS),
            value={"name": "x"},
            note="no",
        ),
    ]
    for call in calls:
        with pytest.raises(NotFoundError):
            call()
    theirs = next(row for row in db.tables["clinical_facts"] if row["id"] == F_THEIRS)
    assert theirs["review_state"] == "pending_review" and theirs["value"] == {"name": "Metformin"}
    assert not [
        row
        for row in db.tables.get("clinical_fact_audit_events", [])
        if row["event_type"] in ("rejected", "corrected")
    ]


# ── Clinician document workflow (list, queue, review, annotate, facts) ─────────────────


def _workflow(db: FakeDB) -> ClinicianDocumentWorkflowService:
    return ClinicianDocumentWorkflowService(
        db=db,
        care_team_repo=MagicMock(),
        execute=passthrough,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_patient_document_list_hides_other_teams_and_shows_unrouted() -> None:
    service = _workflow(_world())
    mine = await service.fetch_patient_documents(UUID(PATIENT), clinician_id=UUID(CLINICIAN))
    assert _ids(mine) == {DOC_MINE, DOC_OPEN}
    theirs = await service.fetch_patient_documents(UUID(PATIENT), clinician_id=UUID(OTHER))
    assert _ids(theirs) == {DOC_THEIRS, DOC_OPEN}


@pytest.mark.asyncio
async def test_patient_document_list_for_a_two_link_clinician_has_both_teams() -> None:
    documents = await _workflow(_world()).fetch_patient_documents(
        UUID(PATIENT), clinician_id=UUID(TWO)
    )
    assert _ids(documents) == {DOC_TWO_B, DOC_OPEN}  # no TWO_A documents exist in this world


@pytest.mark.asyncio
async def test_patient_document_list_refuses_a_clinician_with_no_link() -> None:
    with pytest.raises(AuthorizationError):
        await _workflow(_world()).fetch_patient_documents(UUID(PATIENT), clinician_id=UUID(THIRD))


def _queue_world() -> FakeDB:
    db = _world()
    db.tables["patients"] = [{"id": PATIENT, "first_name": "Sam", "last_name": "Rowe"}]
    return db


@pytest.mark.asyncio
async def test_review_queue_lists_own_routed_and_unrouted_documents_only() -> None:
    service = _workflow(_queue_world())
    queue = await service.list_document_review_queue(UUID(CLINICIAN))
    assert _ids(queue) == {DOC_MINE, DOC_OPEN}
    by_id = {row["id"]: row for row in queue}
    assert by_id[DOC_OPEN]["needs_claim"] is True
    assert by_id[DOC_OPEN]["claimable_care_team_ids"] == [TEAM]
    assert by_id[DOC_MINE]["needs_claim"] is False
    assert _ids(await service.list_document_review_queue(UUID(OTHER))) == {DOC_THEIRS, DOC_OPEN}
    assert await service.list_document_review_queue(UUID(THIRD)) == []


@pytest.mark.asyncio
async def test_a_two_link_clinician_reviews_the_documents_of_both_teams() -> None:
    queue = await _workflow(_queue_world()).list_document_review_queue(UUID(TWO))
    assert _ids(queue) == {DOC_TWO_B, DOC_OPEN}
    assert next(row for row in queue if row["id"] == DOC_OPEN)["claimable_care_team_ids"] == sorted(
        [TWO_A, TWO_B]
    )


def _status(db: FakeDB, doc_id: str) -> Any:
    return next(row for row in db.tables["documents"] if row["id"] == doc_id)["review_status"]


@pytest.mark.asyncio
async def test_approve_and_reject_refuse_another_teams_document() -> None:
    db = _world()
    service = _workflow(db)
    with pytest.raises(NotFoundError):
        await service.approve_document_review(UUID(CLINICIAN), UUID(PATIENT), UUID(DOC_THEIRS))
    with pytest.raises(NotFoundError):
        await service.reject_document_review(UUID(CLINICIAN), UUID(PATIENT), UUID(DOC_THEIRS), "no")
    assert _status(db, DOC_THEIRS) == "pending"


@pytest.mark.asyncio
async def test_an_unrouted_document_cannot_be_approved_or_rejected_until_claimed() -> None:
    db = _world()
    service = _workflow(db)
    for action in (
        service.approve_document_review(UUID(CLINICIAN), UUID(PATIENT), UUID(DOC_OPEN)),
        service.reject_document_review(UUID(OTHER), UUID(PATIENT), UUID(DOC_OPEN), "no"),
    ):
        with pytest.raises(ValidationError) as caught:
            await action
        assert caught.value.code == "DOCUMENT_CLAIM_REQUIRED"
    assert _status(db, DOC_OPEN) == "pending"
    # Once a team has claimed it (the database does this atomically) its clinician may review.
    document = next(row for row in db.tables["documents"] if row["id"] == DOC_OPEN)
    document.update(routing_state="routed", care_team_id=TEAM)
    result = await service.approve_document_review(UUID(CLINICIAN), UUID(PATIENT), UUID(DOC_OPEN))
    assert result["review_status"] == "approved"
    with pytest.raises(NotFoundError):  # and now it is not the other team's
        await service.approve_document_review(UUID(OTHER), UUID(PATIENT), UUID(DOC_OPEN))


@pytest.mark.asyncio
async def test_the_owning_teams_clinician_can_approve_a_routed_document() -> None:
    db = _world()
    result = await _workflow(db).approve_document_review(
        UUID(CLINICIAN), UUID(PATIENT), UUID(DOC_MINE)
    )
    assert result["review_status"] == "approved" and _status(db, DOC_MINE) == "approved"


@pytest.mark.asyncio
async def test_review_by_a_clinician_with_no_link_is_refused() -> None:
    with pytest.raises(AuthorizationError):
        await _workflow(_world()).approve_document_review(
            UUID(THIRD), UUID(PATIENT), UUID(DOC_OPEN)
        )


@pytest.mark.asyncio
async def test_annotating_another_teams_document_is_refused_and_writes_nothing() -> None:
    db = _world()
    service = _workflow(db)
    with pytest.raises(NotFoundError):
        await service.save_document_annotation(
            UUID(CLINICIAN), UUID(PATIENT), UUID(DOC_THEIRS), "note"
        )
    assert "clinician_annotation" not in next(
        row for row in db.tables["documents"] if row["id"] == DOC_THEIRS
    )
    saved = await service.save_document_annotation(
        UUID(CLINICIAN), UUID(PATIENT), UUID(DOC_OPEN), "note"
    )
    assert saved["status"] == "saved"


@pytest.mark.asyncio
async def test_document_facts_refuse_another_teams_document() -> None:
    service = _workflow(_world())
    with pytest.raises(NotFoundError):
        await service.document_facts(UUID(CLINICIAN), UUID(PATIENT), UUID(DOC_THEIRS))


@pytest.mark.asyncio
async def test_document_facts_leave_out_a_fact_that_also_cites_another_teams_document() -> None:
    facts = await _workflow(_world()).document_facts(UUID(CLINICIAN), UUID(PATIENT), UUID(DOC_MINE))
    assert {fact["id"] for fact in facts} == {F_MINE}  # F_MIXED also cites DOC_THEIRS


# ── Document source / retry endpoints (DocumentService) ────────────────────────────────


def test_clinician_document_authorization_follows_ownership() -> None:
    service = DocumentService(_world())  # type: ignore[arg-type]
    service.authorize_clinician_document(UUID(CLINICIAN), UUID(PATIENT), UUID(DOC_MINE))
    service.authorize_clinician_document(UUID(CLINICIAN), UUID(PATIENT), UUID(DOC_OPEN))
    with pytest.raises(NotFoundError):
        service.authorize_clinician_document(UUID(CLINICIAN), UUID(PATIENT), UUID(DOC_THEIRS))
    with pytest.raises(AuthorizationError):
        service.authorize_clinician_document(UUID(THIRD), UUID(PATIENT), UUID(DOC_OPEN))


@pytest.mark.asyncio
async def test_clinician_source_preview_is_refused_for_another_teams_document() -> None:
    service = DocumentService(_world())  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        await service.get_clinician_document(UUID(CLINICIAN), UUID(PATIENT), UUID(DOC_THEIRS))
    document = await service.get_clinician_document(UUID(OTHER), UUID(PATIENT), UUID(DOC_THEIRS))
    assert document["id"] == DOC_THEIRS


@pytest.mark.asyncio
async def test_create_document_stores_the_owner_and_routing_state() -> None:
    db = FakeDB({"care_teams": standard_links()})
    service = DocumentService(db)  # type: ignore[arg-type]
    base: dict[str, Any] = {
        "patient_id": UUID(PATIENT),
        "uploaded_by": UUID(PATIENT),
        "uploaded_by_role": "patient",
        "file_name": "a.pdf",
        "file_path": f"{PATIENT}/a.pdf",
        "file_size_bytes": 10,
        "mime_type": "application/pdf",
        "document_type": "lab_report",
        "sign_file_url": False,
    }
    routed = await service.create_document(**base, care_team_id=TEAM, routing_state="routed")
    assert (routed["care_team_id"], routed["routing_state"]) == (TEAM, "routed")
    open_doc = await service.create_document(**base, care_team_id=None, routing_state="unrouted")
    assert (open_doc["care_team_id"], open_doc["routing_state"]) == (None, "unrouted")
    with pytest.raises(ValidationError):
        await service.create_document(**base, care_team_id=TEAM, routing_state="unrouted")


# ── FHIR / SMART review reads ──────────────────────────────────────────────────────────


def test_fact_review_list_only_shows_facts_from_sources_the_clinician_may_see() -> None:
    service = FhirImportReviewService(_world())  # type: ignore[arg-type]
    page = service.list_facts(
        clinician_id=UUID(CLINICIAN),
        patient_id=UUID(PATIENT),
        review_state=ClinicalFactReviewState.PENDING_REVIEW,
        fact_type=None,
        offset=0,
        limit=50,
    )
    assert {fact["id"] for fact in page["facts"]} == {F_MINE, F_OPEN, F_IMP_MINE}
    assert page["total_count"] == 3
    assert page["state_counts"] == {"pending_review": 3}
    # F_IMP_LEGACY's provenance has no team but its import row belongs to another clinician.
    assert F_IMP_LEGACY not in {fact["id"] for fact in page["facts"]}


def test_fact_review_list_for_the_other_team_is_the_mirror_image() -> None:
    service = FhirImportReviewService(_world())  # type: ignore[arg-type]
    page = service.list_facts(
        clinician_id=UUID(OTHER),
        patient_id=UUID(PATIENT),
        review_state=ClinicalFactReviewState.PENDING_REVIEW,
        fact_type=None,
        offset=0,
        limit=50,
    )
    assert {fact["id"] for fact in page["facts"]} == {F_THEIRS, F_OPEN, F_IMP_THEIRS, F_IMP_LEGACY}


def test_fact_review_list_refuses_a_clinician_with_no_link() -> None:
    with pytest.raises(AuthorizationError):
        FhirImportReviewService(_world()).list_facts(  # type: ignore[arg-type]
            clinician_id=UUID(THIRD),
            patient_id=UUID(PATIENT),
            review_state=ClinicalFactReviewState.PENDING_REVIEW,
            fact_type=None,
            offset=0,
            limit=5,
        )


def test_fact_source_is_refused_for_another_teams_fact_and_import() -> None:
    service = FhirImportReviewService(_world())  # type: ignore[arg-type]
    source = service.get_source(
        clinician_id=UUID(CLINICIAN), fact_id=UUID(F_IMP_MINE), patient_id=UUID(PATIENT)
    )
    assert source is not None and source["raw_resource"] == {"id": "m1"}
    for hidden in (F_IMP_THEIRS, F_THEIRS, F_MIXED):
        with pytest.raises(NotFoundError):
            service.get_source(
                clinician_id=UUID(CLINICIAN), fact_id=UUID(hidden), patient_id=UUID(PATIENT)
            )


def test_a_legacy_fact_is_refused_when_its_import_belongs_to_another_clinician() -> None:
    service = FhirImportReviewService(_world())  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        service.get_source(
            clinician_id=UUID(CLINICIAN), fact_id=UUID(F_IMP_LEGACY), patient_id=UUID(PATIENT)
        )
    assert service.get_source(
        clinician_id=UUID(OTHER), fact_id=UUID(F_IMP_LEGACY), patient_id=UUID(PATIENT)
    )


# ── FHIR audit export ──────────────────────────────────────────────────────────────────


def test_fhir_audit_export_is_refused_for_another_teams_fact_and_returns_no_events() -> None:
    service = FhirAuditExportService(_world())  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        service.export_for_fact(
            clinician_id=UUID(CLINICIAN), fact_id=UUID(F_THEIRS), patient_id=UUID(PATIENT)
        )
    exported = service.export_for_fact(
        clinician_id=UUID(CLINICIAN), fact_id=UUID(F_MINE), patient_id=UUID(PATIENT)
    )
    assert [event["subtype"][0]["code"] for event in exported["audit_events"]] == ["created"]
    with pytest.raises(AuthorizationError):
        service.export_for_fact(
            clinician_id=UUID(THIRD), fact_id=UUID(F_OPEN), patient_id=UUID(PATIENT)
        )


# ── Reconciliation ─────────────────────────────────────────────────────────────────────


def _decision(**fields: Any) -> ReconciliationDecisionRequest:
    return ReconciliationDecisionRequest.model_validate(
        {"decision": "keep_existing", "idempotency_key": str(uuid4()), **fields}
    )


def test_reconciliation_preview_and_decision_refuse_another_teams_fact() -> None:
    db = _world()
    service = ClinicalReconciliationService(db)  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        service.preview(
            clinician_id=UUID(CLINICIAN), fact_id=UUID(F_THEIRS), patient_id=UUID(PATIENT)
        )
    with pytest.raises(NotFoundError):
        service.decide(
            fact_id=UUID(F_IMP_THEIRS),
            patient_id=UUID(PATIENT),
            actor_id=UUID(CLINICIAN),
            request=_decision(),
        )
    with pytest.raises(AuthorizationError):
        service.decide(
            fact_id=UUID(F_OPEN),
            patient_id=UUID(PATIENT),
            actor_id=UUID(THIRD),
            request=_decision(),
        )
    assert db.rpc_calls == []


def test_reconciliation_decision_by_the_owning_clinician_reaches_the_database() -> None:
    db = _world()
    db.rpc_handlers["apply_clinical_fact_reconciliation"] = lambda params: {
        "fact_id": params["p_fact_id"],
        "decision": params["p_decision"],
    }
    result = ClinicalReconciliationService(db).decide(  # type: ignore[arg-type]
        fact_id=UUID(F_MINE),
        patient_id=UUID(PATIENT),
        actor_id=UUID(CLINICIAN),
        request=_decision(),
    )
    assert result["decision"] == "keep_existing"
    assert db.rpc_calls[0][1]["p_actor_id"] == CLINICIAN


CONDITIONS = [
    {
        "id": "c0000000-0000-4000-8000-000000000001",
        "patient_id": PATIENT,
        "name": "Hypertension",
        "is_sensitive": False,
        "recorded_by_care_team_id": TEAM,
    },
    {
        "id": "c0000000-0000-4000-8000-000000000002",
        "patient_id": PATIENT,
        "name": "Hypertension",
        "is_sensitive": True,
        "recorded_by_care_team_id": TEAM,
    },
    {
        "id": "c0000000-0000-4000-8000-000000000003",
        "patient_id": PATIENT,
        "name": "Hypertension",
        "is_sensitive": True,
        "recorded_by_care_team_id": OTHER_TEAM,
    },
]


def _condition_world() -> FakeDB:
    db = _world()
    db.tables["conditions"] = [dict(row) for row in CONDITIONS]
    fact = next(row for row in db.tables["clinical_facts"] if row["id"] == F_MINE)
    fact.update(fact_type="condition", subject_type="condition", value={"name": "Hypertension"})
    return db


def test_reconciliation_preview_never_matches_a_sensitive_condition_another_team_recorded() -> None:
    preview = ClinicalReconciliationService(_condition_world()).preview(  # type: ignore[arg-type]
        clinician_id=UUID(CLINICIAN), fact_id=UUID(F_MINE), patient_id=UUID(PATIENT)
    )
    assert {match["target_id"] for match in preview["matches"]} == {
        CONDITIONS[0]["id"],
        CONDITIONS[1]["id"],
    }
    assert CONDITIONS[2]["id"] not in str(preview)


def test_reconciliation_cannot_target_another_teams_sensitive_condition() -> None:
    db = _condition_world()
    with pytest.raises(NotFoundError):
        ClinicalReconciliationService(db).decide(  # type: ignore[arg-type]
            fact_id=UUID(F_MINE),
            patient_id=UUID(PATIENT),
            actor_id=UUID(CLINICIAN),
            request=_decision(
                decision="update", target_id=CONDITIONS[2]["id"], selected_fields=["name"]
            ),
        )
    assert db.rpc_calls == []


# ── SMART launch, import list, withdrawal, ownership of new imports ────────────────────


def test_import_list_shows_only_imports_the_clinician_may_see() -> None:
    service = SmartLaunchService(_world())  # type: ignore[arg-type]
    mine = service.list_imports(clinician_id=UUID(CLINICIAN), patient_id=UUID(PATIENT))
    assert _ids(mine) == {IMP_MINE}
    other = service.list_imports(clinician_id=UUID(OTHER), patient_id=UUID(PATIENT))
    assert _ids(other) == {IMP_THEIRS, IMP_LEGACY}
    with pytest.raises(AuthorizationError):
        service.list_imports(clinician_id=UUID(THIRD), patient_id=UUID(PATIENT))


def test_withdrawing_another_teams_import_is_refused_before_the_rpc() -> None:
    db = _world()
    service = SmartLaunchService(db)  # type: ignore[arg-type]
    with pytest.raises(NotFoundError):
        service.remove_import(
            clinician_id=UUID(CLINICIAN), patient_id=UUID(PATIENT), import_id=UUID(IMP_THEIRS)
        )
    assert db.rpc_calls == []
    db.rpc_handlers["withdraw_unapplied_fhir_import"] = lambda _p: {"can_delete": True}
    service.remove_import(
        clinician_id=UUID(CLINICIAN), patient_id=UUID(PATIENT), import_id=UUID(IMP_MINE)
    )
    assert db.rpc_calls[0][0] == "withdraw_unapplied_fhir_import"


def test_a_new_import_is_owned_by_the_importing_clinicians_link() -> None:
    db = _world()
    service = SmartLaunchService(db)  # type: ignore[arg-type]
    team = service._import_care_team(UUID(CLINICIAN), UUID(PATIENT))
    assert str(team) == TEAM
    created = service._create_import(
        session={
            "id": str(uuid4()),
            "clinician_id": CLINICIAN,
            "patient_id": PATIENT,
            "issuer": "https://sandbox.example/fhir",
        },
        context={"patient": "p1", "encounter": None},
        care_team_id=team,
    )
    assert created["care_team_id"] == TEAM


def test_an_import_by_a_clinician_with_two_links_needs_a_chosen_team() -> None:
    service = SmartLaunchService(_world())  # type: ignore[arg-type]
    with pytest.raises(ValidationError) as caught:
        service._import_care_team(UUID(TWO), UUID(PATIENT))
    assert caught.value.code == "CARE_TEAM_REQUIRED"
    with pytest.raises(AuthorizationError):
        service._import_care_team(UUID(THIRD), UUID(PATIENT))


def test_launch_is_refused_before_any_oauth_step_when_the_owner_is_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "smart_client_id", "sandbox-client")
    service = SmartLaunchService(_world())  # type: ignore[arg-type]
    service._discover = MagicMock()  # type: ignore[method-assign]
    with pytest.raises(ValidationError) as caught:
        service.start_launch(
            clinician_id=UUID(TWO), patient_id=UUID(PATIENT), issuer="https://x.example/fhir"
        )
    assert caught.value.code == "CARE_TEAM_REQUIRED"
    service._discover.assert_not_called()


def test_imported_candidates_carry_the_importing_team_on_their_provenance() -> None:
    service = FhirImportService(_world())  # type: ignore[arg-type]
    candidates = service._map_candidates(
        patient_id=UUID(PATIENT),
        issuer="https://sandbox.example/fhir",
        stored_resource={"id": RES_MINE, "external_resource_id": "m1", "version_id": "1"},
        resource={
            "resourceType": "AllergyIntolerance",
            "id": "a1",
            "code": {"text": "Penicillin"},
            "patient": {"reference": "Patient/p"},
        },
        care_team_id=UUID(TEAM),
    )
    assert candidates and all(str(c.provenance.care_team_id) == TEAM for c in candidates)


def test_the_fact_registry_persists_the_provenance_team() -> None:
    db = FakeDB({"care_teams": standard_links()})
    ClinicalFactService(db).create_candidate(  # type: ignore[arg-type]
        ClinicalFactCreate(
            patient_id=UUID(PATIENT),
            fact_type="medication",
            subject_type="MedicationRequest",
            value={"name": "Metformin"},
            provenance=SourceProvenanceCreate(
                artifact_type=SourceArtifactType.FHIR_RESOURCE,
                source_system="https://s.example",
                source_reference="fhir_import_resources/x",
                care_team_id=UUID(TEAM),
            ),
        ),
        actor_id=UUID(CLINICIAN),
    )
    assert db.tables["source_provenances"][0]["care_team_id"] == TEAM


# ── External record review workload ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_external_review_workload_counts_only_what_the_clinicians_teams_may_see() -> None:
    db = _world()
    service = ExternalRecordReviewService(db)  # type: ignore[arg-type]
    service.memberships.link_scope = AsyncMock(  # type: ignore[method-assign]
        return_value=ClinicLinkScope({PATIENT: (None, None)})
    )
    mine = await service.list_reviews(UUID(CLINICIAN))
    other = await service.list_reviews(UUID(OTHER))
    # Seven pending facts: mine=F_MINE,F_IMP_MINE,F_IMP_LEGACY(shared); open=F_OPEN; theirs...
    assert mine.items[0].pending_count == 4  # F_MINE, F_OPEN, F_IMP_MINE, F_IMP_LEGACY
    assert other.items[0].pending_count == 4  # F_THEIRS, F_OPEN, F_IMP_THEIRS, F_IMP_LEGACY


@pytest.mark.asyncio
async def test_external_review_workload_is_zero_for_a_team_with_nothing_visible() -> None:
    db = FakeDB(
        {
            "care_teams": standard_links(),
            "clinical_facts": [_fact(F_THEIRS)],
            "evidence_citations": [{"id": "c1", "fact_id": F_THEIRS, "provenance_id": "p-theirs"}],
            "source_provenances": [{"id": "p-theirs", "document_id": DOC_THEIRS}],
            "documents": [_doc(DOC_THEIRS, OTHER_TEAM)],
        }
    )
    service = ExternalRecordReviewService(db)  # type: ignore[arg-type]
    service.memberships.link_scope = AsyncMock(  # type: ignore[method-assign]
        return_value=ClinicLinkScope({PATIENT: (None, None)})
    )
    result = await service.list_reviews(UUID(CLINICIAN))
    assert result.items == []


# ── Drafting follows the document ──────────────────────────────────────────────────────


def test_ingestion_requests_drafting_for_the_document_not_the_patient() -> None:
    from datetime import UTC, datetime

    from app.services.ingestion_service import DocumentDraftingRequest

    db = FakeDB()
    db.rpc_handlers["request_care_plan_generation_for_document"] = lambda _p: {
        "request_id": None,
        "status": "document_unrouted",
    }
    when = datetime(2026, 10, 1, tzinfo=UTC)
    outcome = DocumentDraftingRequest(db).request(UUID(DOC_OPEN), when)  # type: ignore[arg-type]
    assert outcome["status"] == "document_unrouted"
    assert db.rpc_calls == [
        (
            "request_care_plan_generation_for_document",
            {"p_document_id": DOC_OPEN, "p_source_watermark": when.isoformat()},
        )
    ]
