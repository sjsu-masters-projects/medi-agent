"""Tests for evidence-grounded Form FDA 3500 draft orchestration.

The service runs against ``FakeDB`` (tests/unit/services/medwatch_fake_db.py), an in-memory
client whose RPCs follow migrations 048 and 064. Synthetic data only; nothing contacts FDA.
"""

import copy
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
from app.models.adr import (
    MEDWATCH_APPROVAL_ATTESTATIONS,
    MedWatchDraftApprovalRequest,
    MedWatchDraftCreateRequest,
    MedWatchDraftDiscardRequest,
    MedWatchDraftRead,
    MedWatchDraftUpdateRequest,
    MedWatchSubmissionAmendRequest,
    MedWatchSubmissionRecordRequest,
)
from app.models.medwatch_form_3500 import MedWatchFormDataV2
from app.services import medwatch_service as medwatch_module
from app.services.medwatch_3500.identifier import DEFAULT_CODE_PATTERN, identifier_violations
from app.services.medwatch_3500.pdf import Form3500RenderError
from app.services.medwatch_3500.template import TemplateMismatchError
from app.services.medwatch_service import (
    Form3500Sources,
    MedWatchService,
    build_form_3500,
    export_filename,
    patient_identity,
)
from tests.unit.services.medwatch_3500_fixtures import full_payload
from tests.unit.services.medwatch_fake_db import (
    APPROVED_AT,
    OTHER_CLINICIAN_ID,
    FakeDB,
    api_error,
    seeded,
)
from tests.unit.services.medwatch_fake_db import (
    CLINICIAN_ID as FAKE_CLINICIAN,
)
from tests.unit.services.medwatch_fake_db import PATIENT_ID as FAKE_PATIENT

ASSESSMENT = "44444444-4444-4444-8444-444444444444"
SYMPTOM = "22222222-2222-4222-8222-222222222222"
MEDICATION = "33333333-3333-4333-8333-333333333333"
CLINICIAN = UUID(FAKE_CLINICIAN)


def _assessment(**overrides: Any) -> dict[str, Any]:
    row = {
        "id": ASSESSMENT,
        "patient_id": FAKE_PATIENT,
        "symptom_report_id": SYMPTOM,
        "suspect_medication_id": MEDICATION,
        "suspect_medication_name": "Lisinopril",
        "naranjo_score": 6,
        "causality": "Probable",
        "status": "draft",
        "naranjo_answers": {"improved_on_dechallenge": "yes"},
        "evidence": [
            {
                "question": "improved_on_dechallenge",
                "answer": "yes",
                "evidence": "Cough eased after the dose was held.",
            }
        ],
    }
    row.update(overrides)
    return row


def _sources_db(**tables: list[dict[str, Any]]) -> FakeDB:
    return seeded(
        adr_assessments=[_assessment()],
        symptom_reports=[
            {
                "id": SYMPTOM,
                "patient_id": FAKE_PATIENT,
                "symptom": "Dry cough",
                "severity": 4,
                "onset": "2026-10-02",
                "notes": None,
                "created_at": "2026-10-03T16:00:00+00:00",
            }
        ],
        medications=[
            {
                "id": MEDICATION,
                "patient_id": FAKE_PATIENT,
                "name": "Lisinopril",
                "dosage": "10 mg",
                "frequency": "daily",
                "route": "oral",
                "start_date": "2026-09-01",
                "is_active": True,
            },
            {
                "id": "66666666-6666-4666-8666-666666666667",
                "patient_id": FAKE_PATIENT,
                "name": "Metformin",
                "is_active": True,
            },
        ],
        conditions=[
            {"patient_id": FAKE_PATIENT, "name": "Hypertension", "status": "active"},
            {"patient_id": FAKE_PATIENT, "name": "Old fracture", "status": "resolved"},
        ],
        allergies=[{"patient_id": FAKE_PATIENT, "allergen": "Penicillin", "reaction": "hives"}],
        **tables,
    )


def _service(db: FakeDB) -> MedWatchService:
    return MedWatchService(db)  # type: ignore[arg-type]


def _ready_payload(**section_overrides: Any) -> dict[str, Any]:
    """A full v2 payload that passes the approval gate for the seeded patient."""
    payload = full_payload(1)
    payload["section_a"]["identifier"] = "XX-ABCD"
    payload["section_b"]["report_types"] = ["adverse_event"]
    payload["section_b"]["outcomes"] = ["hospitalization"]
    payload["section_b"]["death_date"] = None
    payload["section_b"]["narrative"] = "Synthetic dizziness after a dose increase."
    payload["section_b"]["tests"] = []
    payload["section_b"]["tests_comments"] = ""
    payload["section_b"]["other_history"] = ""
    payload["section_f"]["others"] = []
    payload["legacy"] = {}
    for key, value in section_overrides.items():
        section, field = key.split("__")
        payload[section][field] = value
    return payload


def _draft_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "id": str(uuid4()),
        "adr_assessment_id": ASSESSMENT,
        "patient_id": FAKE_PATIENT,
        "form_data": _ready_payload(),
        "source_evidence": [],
        "clinician_edited_fields": [],
        "de_identified": False,
        "status": "draft",
        "patient_reference": "XX-ABCD",
        "created_by": FAKE_CLINICIAN,
        "approved_by": None,
        "approved_at": None,
        "approval_note": None,
        "submitted_at": None,
        "discarded_at": None,
        "discarded_by": None,
        "discard_reason": None,
        "revision": 1,
        "export_version": "fda-3500-2025-09",
        "care_team_id": "team-1",
        "created_at": "2026-10-13T16:00:00+00:00",
        "updated_at": "2026-10-13T16:00:00+00:00",
    }
    row.update(overrides)
    return row


def _approved(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "status": "reviewed",
        "approved_by": FAKE_CLINICIAN,
        "approved_at": APPROVED_AT,
        "approval_note": "Reviewed",
        "revision": 3,
    }
    values.update(overrides)
    return _draft_row(**values)


def _legacy_form() -> dict[str, Any]:
    return {
        "patient": {"patient_identifier": "Lucía Ramírez", "date_of_birth": "1961-07-14"},
        "event": {"description": "Dizziness", "onset_date_or_time": "2026-10-01"},
        "suspect_product": {"name": "Lisinopril", "dose": "10 mg"},
        "concomitant_products": {"products": "Albuterol"},
        "tests_and_history": {"relevant_tests": "", "other_relevant_history": ""},
        "reporter": {"name": "Elena Park", "email": "elena.park@example.test"},
        "clinical_review": {
            "naranjo_score": 6,
            "causality": "Probable",
            "reportability_rationale": "Clinically significant new event.",
        },
    }


def _approval(**overrides: Any) -> MedWatchDraftApprovalRequest:
    payload: dict[str, Any] = {
        "approval_note": "Reviewed source evidence.",
        "expected_revision": 1,
        "attested": True,
        "attestation_version": "medwatch-3500-approval-v1",
    }
    payload.update(overrides)
    return MedWatchDraftApprovalRequest.model_validate(payload)


# Create (R17.1, R18, R22.1 wiring).


@pytest.mark.asyncio
async def test_create_draft_builds_form_3500_with_provenance_from_stored_records() -> None:
    db = _sources_db()
    item = await _service(db).create_draft(
        CLINICIAN,
        UUID(ASSESSMENT),
        MedWatchDraftCreateRequest(
            decision="prepare_draft", reportability_rationale="Reporting for signal review."
        ),
    )

    [(name, payload)] = db.rpc_calls
    assert name == "create_medwatch_draft"
    form = MedWatchFormDataV2.model_validate(payload["p_form_data"])
    assert form.form_version == "fda-3500-2025-09"
    assert DEFAULT_CODE_PATTERN.fullmatch(form.section_a.identifier)
    assert form.section_a.identifier.startswith("LR-")
    assert payload["p_draft_id"] == item["id"]
    assert form.section_b.other_history == (
        "Conditions: Hypertension. Allergies: Penicillin (hives)."
    )
    assert [other.name for other in form.section_f.others] == ["Metformin"]
    assert (form.section_g.first_name, form.section_g.last_name) == ("Elena", "Park")
    sources: dict[str, set[str]] = {}
    for entry in payload["p_source_evidence"]:
        sources.setdefault(entry["field_paths"][0], set()).add(entry["source_type"])
    assert sources["section_b.other_history"] == {
        "patient_condition_record",
        "patient_allergy_record",
    }
    assert sources["section_d.product_1.abated"] == {"ai_extracted_adr_evidence"}
    assert not any(
        entry["source_type"] == "patient_confirmed_adr_evidence"
        for entry in payload["p_source_evidence"]
    )
    read = MedWatchDraftRead.model_validate(item)
    assert read.patient_reference == form.section_a.identifier
    assert {issue.code for issue in read.missing_for_approval} >= {
        "event_date_unconfirmed",
        "health_professional_missing",
        "occupation_missing",
        "non_serious_attestation_required",
    }
    assert read.attestation.text == MEDWATCH_APPROVAL_ATTESTATIONS[read.attestation.version]
    assert read.current_submission is None and not read.pdf_available
    for table in ("conditions", "allergies", "symptom_reports", "clinicians"):
        assert table in db.queries


@pytest.mark.asyncio
async def test_create_allows_a_new_draft_only_after_discard() -> None:
    db = _sources_db(medwatch_drafts=[_draft_row()])
    request = MedWatchDraftCreateRequest(decision="prepare_draft", reportability_rationale="R")
    with pytest.raises(ValidationError) as error:
        await _service(db).create_draft(CLINICIAN, UUID(ASSESSMENT), request)
    assert error.value.code == "MEDWATCH_DRAFT_EXISTS"
    db.tables["medwatch_drafts"][0]["discarded_at"] = "2026-10-13T16:30:00+00:00"
    await _service(db).create_draft(CLINICIAN, UUID(ASSESSMENT), request)
    assert [name for name, _ in db.rpc_calls] == ["create_medwatch_draft"]


@pytest.mark.asyncio
async def test_missing_and_unassigned_records_are_404_and_403() -> None:
    db = _sources_db(medwatch_drafts=[_draft_row(id="d0000000-0000-4000-8000-000000000000")])
    service = _service(db)
    request = MedWatchDraftCreateRequest(decision="prepare_draft", reportability_rationale="R")
    with pytest.raises(NotFoundError):
        await service.create_draft(CLINICIAN, uuid4(), request)
    with pytest.raises(NotFoundError):
        await service.get_preview(CLINICIAN, uuid4())
    with pytest.raises(AuthorizationError):
        await service.get_preview(
            UUID(OTHER_CLINICIAN_ID), UUID("d0000000-0000-4000-8000-000000000000")
        )
    with pytest.raises(AuthorizationError):
        await service.create_draft(UUID(OTHER_CLINICIAN_ID), UUID(ASSESSMENT), request)
    assert db.rpc_calls == []


# Save and load (Property 9, R16.5, R17.3, R22.5).


@pytest.mark.parametrize("index", range(6))
@pytest.mark.asyncio
async def test_property_9_save_then_load_returns_equal_form_data(index: int) -> None:
    """Feature: adr-loop-gap-fixes, Property 9: Save then load returns equal data."""
    payload = full_payload(index)
    payload["section_a"]["identifier"] = "XX-ABCD"
    stored = _draft_row(form_data={**_ready_payload(), "legacy": payload["legacy"]})
    db = seeded(medwatch_drafts=[stored])
    service = _service(db)
    form = MedWatchFormDataV2.model_validate(payload)
    saved = await service.update_draft(
        CLINICIAN,
        UUID(stored["id"]),
        MedWatchDraftUpdateRequest(form_data=form, expected_revision=1),
    )
    loaded = (await service.list_drafts(CLINICIAN))["items"][0]
    assert saved["form_data"] == form.model_dump(mode="json")
    assert loaded["form_data"] == form.model_dump(mode="json")
    assert loaded["revision"] == 2 and loaded["export_version"] == "fda-3500-2025-09"


@pytest.mark.asyncio
async def test_a_048_draft_is_upgraded_on_read_and_saved_as_form_3500() -> None:
    legacy = _draft_row(form_data=_legacy_form(), export_version="fda-3500-legacy-048")
    db = seeded(medwatch_drafts=[legacy])
    service = _service(db)
    [item] = (await service.list_drafts(CLINICIAN))["items"]
    assert item["upgraded_from_legacy"] is True
    form = MedWatchFormDataV2.model_validate(item["form_data"])
    assert form.section_a.identifier != "Lucía Ramírez"
    assert DEFAULT_CODE_PATTERN.fullmatch(form.section_a.identifier)
    assert db.tables["medwatch_drafts"][0]["form_data"] == _legacy_form()

    saved = await service.update_draft(
        CLINICIAN,
        UUID(legacy["id"]),
        MedWatchDraftUpdateRequest(form_data=form, expected_revision=1),
    )
    assert saved["upgraded_from_legacy"] is False
    assert db.tables["medwatch_drafts"][0]["form_data"]["form_version"] == "fda-3500-2025-09"
    assert db.rpc_calls[0][1]["p_changed_fields"] == []


@pytest.mark.asyncio
async def test_save_rejects_an_identifying_identifier_and_review_changes() -> None:
    stored = _draft_row()
    db = seeded(medwatch_drafts=[stored])
    service = _service(db)
    for identifier in ("Lucía R", "ramirez-01", "14-Jul-1961", "lucia.ramirez"):
        payload = _ready_payload(section_a__identifier=identifier)
        with pytest.raises(ValidationError) as error:
            await service.update_draft(
                CLINICIAN,
                UUID(stored["id"]),
                MedWatchDraftUpdateRequest(
                    form_data=MedWatchFormDataV2.model_validate(payload), expected_revision=1
                ),
            )
        assert error.value.code == "MEDWATCH_IDENTIFIER_IDENTIFIES", identifier
        assert error.value.details == {"path": "section_a.identifier"}
    payload = _ready_payload()
    payload["mediagent_review"]["naranjo_score"] = 9
    with pytest.raises(ValidationError) as error:
        await service.update_draft(
            CLINICIAN,
            UUID(stored["id"]),
            MedWatchDraftUpdateRequest(
                form_data=MedWatchFormDataV2.model_validate(payload), expected_revision=1
            ),
        )
    assert error.value.code == "MEDWATCH_REVIEW_FIELDS_LOCKED"
    assert db.rpc_calls == []


@pytest.mark.parametrize(
    ("row", "code"),
    [
        (
            {
                "discarded_at": "2026-10-13T00:00:00Z",
                "discarded_by": FAKE_CLINICIAN,
                "discard_reason": "x",
            },
            "MEDWATCH_DRAFT_DISCARDED",
        ),
        (
            {
                "status": "submitted",
                "submitted_at": "2026-10-13T00:00:00Z",
                "approved_at": APPROVED_AT,
            },
            "MEDWATCH_DRAFT_SUBMITTED",
        ),
        (
            {"status": "reviewed", "approved_at": APPROVED_AT, "approved_by": FAKE_CLINICIAN},
            "MEDWATCH_DRAFT_NOT_EDITABLE",
        ),
    ],
)
@pytest.mark.asyncio
async def test_save_rejects_approved_submitted_and_discarded_drafts(row, code) -> None:
    stored = _draft_row(**row)
    db = seeded(medwatch_drafts=[stored])
    with pytest.raises(ValidationError) as error:
        await _service(db).update_draft(
            CLINICIAN,
            UUID(stored["id"]),
            MedWatchDraftUpdateRequest(
                form_data=MedWatchFormDataV2.model_validate(_ready_payload()), expected_revision=1
            ),
        )
    assert error.value.code == code
    assert db.rpc_calls == []


@pytest.mark.asyncio
async def test_save_keeps_legacy_text_read_only_and_audits_changed_leaves() -> None:
    stored = _draft_row(form_data={**_ready_payload(), "legacy": {"event.outcome": "Kept"}})
    db = seeded(medwatch_drafts=[stored])
    payload = _ready_payload(section_b__narrative="Synthetic edited narrative.")
    payload["legacy"] = {"event.outcome": "Rewritten by the client"}
    await _service(db).update_draft(
        CLINICIAN,
        UUID(stored["id"]),
        MedWatchDraftUpdateRequest(
            form_data=MedWatchFormDataV2.model_validate(payload), expected_revision=1
        ),
    )
    [(_name, params)] = db.rpc_calls
    assert params["p_changed_fields"] == ["section_b.narrative"]
    assert params["p_form_data"]["legacy"] == {"event.outcome": "Kept"}


# Approval (Property 12 service part, R17.5, R19).


@pytest.mark.asyncio
async def test_property_12_approval_enforces_the_list_the_draft_shows() -> None:
    """Feature: adr-loop-gap-fixes, Property 12: The approval gate is total and shared."""
    incomplete = _ready_payload(
        section_b__outcomes=[], section_b__event_date_confirmed=False, section_g__occupation=None
    )
    stored = _draft_row(form_data=incomplete)
    db = seeded(medwatch_drafts=[stored])
    service = _service(db)
    [item] = (await service.list_drafts(CLINICIAN))["items"]
    preview = await service.get_preview(CLINICIAN, UUID(stored["id"]))
    with pytest.raises(ValidationError) as error:
        await service.approve_draft(CLINICIAN, UUID(stored["id"]), _approval())
    assert error.value.code == "MEDWATCH_APPROVAL_INCOMPLETE"
    assert error.value.details == {"missing_for_approval": item["missing_for_approval"]}
    assert [issue.model_dump() for issue in preview.missing_for_approval] == item[
        "missing_for_approval"
    ]
    assert {issue["code"] for issue in item["missing_for_approval"]} == {
        "non_serious_attestation_required",
        "event_date_unconfirmed",
        "occupation_missing",
    }
    with pytest.raises(ValidationError) as error:
        await service.approve_draft(
            CLINICIAN, UUID(stored["id"]), _approval(non_serious_attested=True)
        )
    assert {issue["code"] for issue in error.value.details["missing_for_approval"]} == {
        "event_date_unconfirmed",
        "occupation_missing",
    }
    assert db.rpc_calls == []


@pytest.mark.asyncio
async def test_approval_needs_the_current_revision_and_acknowledged_warnings() -> None:
    payload = _ready_payload(section_b__narrative="Lucía felt dizzy at Synthetic Valley Health.")
    stored = _draft_row(form_data=payload)
    db = seeded(medwatch_drafts=[stored])
    service = _service(db)
    with pytest.raises(ConflictError) as conflict:
        await service.approve_draft(CLINICIAN, UUID(stored["id"]), _approval(expected_revision=2))
    assert conflict.value.code == "MEDWATCH_REVISION_CONFLICT"
    with pytest.raises(ValidationError) as error:
        await service.approve_draft(CLINICIAN, UUID(stored["id"]), _approval())
    assert error.value.code == "MEDWATCH_WARNINGS_NOT_ACKNOWLEDGED"
    warnings = error.value.details["name_warnings"]
    assert warnings == [
        {"path": "section_b.narrative", "kind": "patient_name"},
        {"path": "section_b.narrative", "kind": "clinic_name"},
    ]
    assert db.rpc_calls == []

    approved = await service.approve_draft(
        CLINICIAN, UUID(stored["id"]), _approval(acknowledged_warnings=warnings)
    )
    [(name, params)] = db.rpc_calls
    assert name == "approve_medwatch_draft"
    assert params["p_approval"] == {
        "attestation_version": "medwatch-3500-approval-v1",
        "non_serious_attested": False,
        "acknowledged_warnings": warnings,
    }
    assert approved["status"] == "reviewed" and approved["missing_for_approval"] == []
    assert approved["pdf_available"] is True


@pytest.mark.asyncio
async def test_a_048_draft_cannot_be_approved_until_saved_as_form_3500() -> None:
    stored = _draft_row(form_data=_legacy_form())
    db = seeded(medwatch_drafts=[stored])
    with pytest.raises(ValidationError) as error:
        await _service(db).approve_draft(
            CLINICIAN, UUID(stored["id"]), _approval(non_serious_attested=True)
        )
    assert error.value.code == "MEDWATCH_APPROVAL_INCOMPLETE"
    assert db.rpc_calls == []


# Lists and preview (R20, R22.5, R23.8).


@pytest.mark.asyncio
async def test_list_states_separate_active_submitted_and_discarded() -> None:
    active, approved = _draft_row(), _approved()
    submitted = _approved(status="submitted", submitted_at="2026-10-13T00:00:00Z")
    discarded = _draft_row(
        discarded_at="2026-10-13T00:00:00Z", discarded_by=FAKE_CLINICIAN, discard_reason="Mistake"
    )
    submission = {
        "id": str(uuid4()),
        "medwatch_draft_id": submitted["id"],
        "recorded_by": FAKE_CLINICIAN,
        "submitted_on": "2026-10-12",
        "method": "medwatch_online",
        "created_at": "2026-10-13T00:00:00Z",
    }
    db = seeded(
        medwatch_drafts=[active, approved, submitted, discarded],
        medwatch_external_submissions=[submission],
    )
    service = _service(db)

    async def ids(state: str) -> set[str]:
        return {item["id"] for item in (await service.list_drafts(CLINICIAN, state))["items"]}  # type: ignore[arg-type]

    assert await ids("active") == {active["id"], approved["id"]}
    assert await ids("submitted") == {submitted["id"]}
    assert await ids("discarded") == {discarded["id"]}
    [item] = (await service.list_drafts(CLINICIAN, "submitted"))["items"]
    read = MedWatchDraftRead.model_validate(item)
    assert read.current_submission is not None
    assert read.current_submission.recorded_by_name == "Elena Park"
    assert read.missing_for_approval == [] and read.pdf_available
    assert (await service.list_drafts(UUID(OTHER_CLINICIAN_ID)))["items"] == []


@pytest.mark.asyncio
async def test_preview_lays_out_form_3500_with_provenance_and_missing_items() -> None:
    payload = _ready_payload(section_g__occupation=None)
    stored = _draft_row(
        form_data=payload,
        source_evidence=[
            {
                "field_paths": ["section_d.product_1.abated"],
                "source_type": "ai_extracted_adr_evidence",
                "attribution": "AI-extracted from the patient's report",
            },
            {
                "field_paths": ["section_a.identifier"],
                "source_type": "default_patient_code",
                "attribution": "Default code",
            },
        ],
        clinician_edited_fields=["section_b.narrative", "section_f.others"],
    )
    db = seeded(medwatch_drafts=[stored])
    preview = await _service(db).get_preview(CLINICIAN, UUID(stored["id"]))

    assert [s.section for s in preview.sections] == ["A", "B", "C", "D", "E", "F", "G"]
    assert {
        s.section for s in preview.sections if s.completion == "not_completed_by_mediagent"
    } == {
        "C",
        "E",
    }
    assert all(not s.items for s in preview.sections if s.section in {"C", "E"})
    items = {item.path: item for section in preview.sections for item in section.items}
    assert items["section_a.identifier"].item == "A1"
    assert items["section_a.identifier"].provenance[0].kind == "record"
    assert items["section_d.product_1.abated"].provenance[0].kind == "ai_extracted"
    assert items["section_b.narrative"].provenance[-1].kind == "clinician_edited"
    assert items["section_f.others[0].name"].provenance[-1].kind == "clinician_edited"
    assert items["section_f.others[0].name"].value is None
    assert items["section_b.outcomes"].label == "Outcome"
    assert items["section_b.outcomes"].value == "Hospitalization (Initial or prolonged)"
    assert items["section_b.event_date"].value == "01-Oct-2026"
    assert items["section_g.occupation"].missing_for_approval == ["occupation_missing"]
    assert "section_b.tests[1].test" not in items and "section_b.tests[0].test" in items
    assert preview.mediagent_review.naranjo_score == 6
    assert not any(path.startswith("mediagent_review") for path in items)
    assert preview.template.revision == "09/2025" and preview.template.expires == "2027-09-30"
    assert preview.template.may_be_superseded is False
    assert preview.not_submitted_to_fda is True


# Export (R15.4, R16.6, R21).


@pytest.mark.asyncio
async def test_pdf_export_is_audited_before_the_bytes_are_returned(caplog) -> None:
    stored = _approved()
    db = seeded(medwatch_drafts=[stored])
    caplog.set_level(logging.DEBUG)
    exported = await _service(db).export_pdf(CLINICIAN, UUID(stored["id"]))
    assert exported["content"].startswith(b"%PDF")
    assert exported["media_type"] == "application/pdf"
    assert exported["filename"] == f"fda-3500-{stored['id'][:8]}-not-submitted.pdf"
    [(name, params)] = db.rpc_calls
    assert name == "record_medwatch_draft_export"
    assert params["p_format"] == "pdf" and params["p_template_revision"] == "09/2025"
    assert re.fullmatch(r"[0-9a-f]{64}", params["p_template_sha256"])
    assert "Synthetic dizziness" not in caplog.text


def _pdf_pages(content: bytes) -> list[bytes]:
    from io import BytesIO

    from pypdf import PdfReader

    reader = PdfReader(BytesIO(content))
    assert reader.decrypt("")
    pages = []
    for page in reader.pages:
        streams = page["/Contents"]
        streams = streams if isinstance(streams, list) else [streams]
        pages.append(b"".join(stream.get_object().get_data() for stream in streams))
    return pages


@pytest.mark.asyncio
async def test_preview_pdf_is_watermarked_on_every_page_and_records_no_export() -> None:
    """The preview is audited as a view, never as an export, and changes no draft state."""
    for stored in (_draft_row(), _approved()):
        db = seeded(medwatch_drafts=[stored])
        before = copy.deepcopy(db.tables["medwatch_drafts"])
        preview = await _service(db).preview_pdf(CLINICIAN, UUID(stored["id"]))
        assert preview["content"].startswith(b"%PDF-1.7")
        pages = _pdf_pages(preview["content"])
        assert pages and all(b"MAWatermarkFont" in page for page in pages)
        assert all(b"DRAFT \x96 not for submission" in page for page in pages)
        assert [name for name, _ in db.rpc_calls] == ["record_medwatch_draft_preview_viewed"]
        assert db.rpc_calls[0][1] == {"p_draft_id": stored["id"], "p_actor_id": str(CLINICIAN)}
        events = [e["event_type"] for e in db.tables["medwatch_draft_audit_events"]]
        assert events == ["preview_viewed"]
        assert db.tables["medwatch_drafts"] == before


@pytest.mark.asyncio
async def test_approved_export_stays_unwatermarked_and_audited() -> None:
    stored = _approved()
    db = seeded(medwatch_drafts=[stored])
    exported = await _service(db).export_pdf(CLINICIAN, UUID(stored["id"]))
    assert all(b"MAWatermarkFont" not in page for page in _pdf_pages(exported["content"]))
    assert [name for name, _ in db.rpc_calls] == ["record_medwatch_draft_export"]
    assert [e["event_type"] for e in db.tables["medwatch_draft_audit_events"]] == ["exported"]


@pytest.mark.asyncio
async def test_single_draft_read_and_preview_hide_unassigned_drafts_as_404() -> None:
    stored = _draft_row()
    service = _service(seeded(medwatch_drafts=[stored]))
    item = await service.get_draft(CLINICIAN, UUID(stored["id"]))
    assert item["id"] == stored["id"]
    messages = set()
    for call in (service.get_draft, service.preview_pdf):
        for clinician, draft_id in (
            (UUID(OTHER_CLINICIAN_ID), UUID(stored["id"])),
            (CLINICIAN, uuid4()),
        ):
            with pytest.raises(NotFoundError) as error:
                await call(clinician, draft_id)
            messages.add(error.value.message.split("'")[0])
    assert messages == {"MedWatch draft "}


@pytest.mark.asyncio
async def test_list_states_draft_and_approved_split_the_active_tab() -> None:
    active, approved = _draft_row(), _approved()
    service = _service(seeded(medwatch_drafts=[active, approved]))
    drafts = (await service.list_drafts(CLINICIAN, "draft"))["items"]
    approved_items = (await service.list_drafts(CLINICIAN, "approved"))["items"]
    assert [i["id"] for i in drafts] == [active["id"]]
    assert [i["id"] for i in approved_items] == [approved["id"]]


@pytest.mark.asyncio
async def test_pdf_export_returns_no_bytes_when_the_audit_fails() -> None:
    stored = _approved()
    db = seeded(medwatch_drafts=[stored])
    db.errors["record_medwatch_draft_export"] = api_error("XX000")
    with pytest.raises(ExternalServiceError) as error:
        await _service(db).export_pdf(CLINICIAN, UUID(stored["id"]))
    assert "SECRET" not in error.value.message and "Synthetic database" not in error.value.message


@pytest.mark.asyncio
async def test_template_mismatch_and_render_failure_record_no_export(monkeypatch) -> None:
    stored = _approved()
    db = seeded(medwatch_drafts=[stored])

    def mismatch(**_kwargs: Any) -> Any:
        raise TemplateMismatchError("synthetic mismatch")

    monkeypatch.setattr(medwatch_module, "load_template", mismatch)
    with pytest.raises(TemplateMismatchError) as error:
        await _service(db).export_pdf(CLINICIAN, UUID(stored["id"]))
    assert error.value.code == "FORM_3500_TEMPLATE_MISMATCH"
    monkeypatch.undo()

    def broken(_form: Any, draft_id: UUID) -> bytes:
        raise Form3500RenderError(draft_id)

    monkeypatch.setattr(medwatch_module, "render_form_3500", broken)
    with pytest.raises(Form3500RenderError) as render_error:
        await _service(db).export_pdf(CLINICIAN, UUID(stored["id"]))
    assert render_error.value.code == "FORM_3500_RENDER_FAILED"
    assert db.rpc_calls == []


@pytest.mark.parametrize(
    ("row", "code"),
    [
        (_draft_row(), "MEDWATCH_NOT_APPROVED"),
        (
            _approved(
                discarded_at="2026-10-13T00:00:00Z", discarded_by=FAKE_CLINICIAN, discard_reason="x"
            ),
            "MEDWATCH_DRAFT_DISCARDED",
        ),
        (_approved(form_data=_legacy_form()), "MEDWATCH_LEGACY_DRAFT_INCOMPLETE"),
    ],
)
@pytest.mark.asyncio
async def test_pdf_export_refusals(row, code) -> None:
    db = seeded(medwatch_drafts=[row])
    with pytest.raises(ValidationError) as error:
        await _service(db).export_pdf(CLINICIAN, UUID(row["id"]))
    assert error.value.code == code
    assert db.rpc_calls == []


@pytest.mark.asyncio
async def test_json_export_is_labelled_form_3500_and_records_its_format() -> None:
    legacy = _approved(form_data=_legacy_form(), export_version="fda-3500-legacy-048")
    db = seeded(medwatch_drafts=[legacy])
    exported = await _service(db).export_draft(CLINICIAN, UUID(legacy["id"]))
    content = exported["content"]
    assert content["artifact_type"] == "fda_3500_draft"
    assert content["form_version"] == "fda-3500-2025-09"
    assert content["not_submitted_to_fda"] is True
    assert content["form_data"]["form_version"] == "fda-3500-2025-09"
    assert "3500a" not in str(content).casefold()
    assert exported["filename"] == export_filename(UUID(legacy["id"]), "json")
    assert db.rpc_calls[0][1]["p_format"] == "json"


# Discard and submission records (R22, R23).


@pytest.mark.asyncio
async def test_discard_maps_conflicts_and_refuses_submitted_drafts() -> None:
    stored = _approved()
    db = seeded(medwatch_drafts=[stored])
    service = _service(db)
    with pytest.raises(ConflictError) as conflict:
        await service.discard_draft(
            CLINICIAN,
            UUID(stored["id"]),
            MedWatchDraftDiscardRequest(reason="Wrong", expected_revision=1),
        )
    assert conflict.value.code == "MEDWATCH_REVISION_CONFLICT"
    item = await service.discard_draft(
        CLINICIAN,
        UUID(stored["id"]),
        MedWatchDraftDiscardRequest(reason=" Wrong ", expected_revision=3),
    )
    assert item["discard_reason"] == "Wrong" and item["discarded_at"]
    assert item["pdf_available"] is False
    submitted = _approved(status="submitted", submitted_at="2026-10-13T00:00:00Z")
    db = seeded(medwatch_drafts=[submitted])
    with pytest.raises(ValidationError) as error:
        await _service(db).discard_draft(
            CLINICIAN,
            UUID(submitted["id"]),
            MedWatchDraftDiscardRequest(reason="x", expected_revision=3),
        )
    assert error.value.code == "MEDWATCH_DRAFT_SUBMITTED"
    assert db.rpc_calls == []


@pytest.mark.asyncio
async def test_submission_is_recorded_after_approval_and_amended_with_history() -> None:
    stored = _approved()
    db = seeded(medwatch_drafts=[stored])
    service = _service(db)
    with pytest.raises(ValidationError) as early:
        await service.record_submission(
            CLINICIAN,
            UUID(stored["id"]),
            MedWatchSubmissionRecordRequest(
                submitted_on=date(2026, 10, 11), method="fax", attested=True, expected_revision=3
            ),
        )
    assert early.value.code == "MEDWATCH_SUBMISSION_INVALID"
    item = await service.record_submission(
        CLINICIAN,
        UUID(stored["id"]),
        MedWatchSubmissionRecordRequest(
            submitted_on=date(2026, 10, 12),
            method="medwatch_online",
            fda_reference=" SYN-1 ",
            attested=True,
            expected_revision=3,
        ),
    )
    original = item["current_submission"]
    assert item["status"] == "submitted" and original.fda_reference == "SYN-1"
    amend = MedWatchSubmissionAmendRequest(
        amends_id=UUID(original.id),
        submitted_on=date(2026, 10, 12),
        method="other",
        method_detail="Synthetic courier",
        reason="Wrong method",
    )
    amended = await service.amend_submission(CLINICIAN, UUID(stored["id"]), amend)
    history = [entry.id for entry in amended["submission_history"]]
    assert history[-1] == original.id and history[0] == amended["current_submission"].id
    assert amended["current_submission"].amends_id == original.id
    with pytest.raises(ConflictError) as conflict:
        await service.amend_submission(CLINICIAN, UUID(stored["id"]), amend)
    assert conflict.value.code == "MEDWATCH_SUBMISSION_CONFLICT"


@pytest.mark.asyncio
async def test_submission_needs_an_approved_draft() -> None:
    stored = _draft_row()
    db = seeded(medwatch_drafts=[stored])
    request = MedWatchSubmissionRecordRequest(
        submitted_on=date(2026, 10, 12), method="fax", attested=True, expected_revision=1
    )
    with pytest.raises(ValidationError) as error:
        await _service(db).record_submission(CLINICIAN, UUID(stored["id"]), request)
    assert error.value.code == "MEDWATCH_NOT_APPROVED"
    with pytest.raises(ValidationError) as amend_error:
        await _service(db).amend_submission(
            CLINICIAN,
            UUID(stored["id"]),
            MedWatchSubmissionAmendRequest(
                amends_id=uuid4(), submitted_on=date(2026, 10, 12), method="fax", reason="x"
            ),
        )
    assert amend_error.value.code == "MEDWATCH_NOT_SUBMITTED"


@pytest.mark.parametrize(
    ("sqlstate", "expected", "code"),
    [
        ("P0002", NotFoundError, "NOT_FOUND"),
        ("42501", AuthorizationError, "AUTHORIZATION_ERROR"),
        ("40001", ConflictError, "MEDWATCH_REVISION_CONFLICT"),
        ("23514", ValidationError, "MEDWATCH_INVALID_STATE"),
        ("22023", ValidationError, "MEDWATCH_INVALID_REQUEST"),
        ("XX000", ExternalServiceError, "EXTERNAL_SERVICE_ERROR"),
    ],
)
@pytest.mark.asyncio
async def test_rpc_errors_map_by_sqlstate_without_database_detail(sqlstate, expected, code) -> None:
    stored = _draft_row()
    db = seeded(medwatch_drafts=[stored])
    db.errors["discard_medwatch_draft"] = api_error(sqlstate)
    with pytest.raises(expected) as error:
        await _service(db).discard_draft(
            CLINICIAN,
            UUID(stored["id"]),
            MedWatchDraftDiscardRequest(reason="x", expected_revision=1),
        )
    assert error.value.code == code
    assert "SECRET" not in error.value.message and "Synthetic database" not in error.value.message


def test_no_medwatch_code_path_can_reach_fda_or_the_network() -> None:
    """R22.3: the codebase has no path that transmits a report."""
    root = Path(medwatch_module.__file__).parent
    sources = [Path(medwatch_module.__file__), *sorted((root / "medwatch_3500").glob("*.py"))]
    for source in sources:
        text = source.read_text()
        for marker in ("httpx", "requests", "urllib", "aiohttp", "socket", "fda.gov"):
            assert marker not in text, (source.name, marker)


def test_approval_requires_explicit_attestation() -> None:
    with pytest.raises(ValueError, match="attestation"):
        MedWatchDraftApprovalRequest(
            approval_note="Reviewed source evidence.",
            expected_revision=1,
            attested=False,
            attestation_version="medwatch-3500-approval-v1",
        )


# Form 3500 prefill with provenance (R17.1, R17.6, R18.1 to R18.6, K-P8). Synthetic records.
PATIENT_ID = UUID("11111111-1111-4111-8111-111111111111")
SYMPTOM_ID = UUID("22222222-2222-4222-8222-222222222222")
MEDICATION_ID = UUID("33333333-3333-4333-8333-333333333333")
ASSESSMENT_ID = UUID("44444444-4444-4444-8444-444444444444")
CLINICIAN_ID = UUID("55555555-5555-4555-8555-555555555555")
DOCUMENT_ID = UUID("66666666-6666-4666-8666-666666666666")
REQUEST_ID = UUID("77777777-7777-4777-8777-777777777777")
DRAFT_ID = UUID("88888888-8888-4888-8888-888888888888")
PREFILL_TODAY = date(2026, 10, 13)


def _sources(**overrides: Any) -> Form3500Sources:
    values: dict[str, Any] = {
        "draft_id": DRAFT_ID,
        "assessment": {
            "id": str(ASSESSMENT_ID),
            "suspect_medication_name": "Lisinopril",
            "naranjo_score": 6,
            "causality": "Probable",
            "naranjo_answers": {
                "improved_on_dechallenge": "yes",
                "reappeared_on_rechallenge": "yes",
                "dose_response": "no",
            },
            "evidence": [
                {
                    "question": "improved_on_dechallenge",
                    "answer": "yes",
                    "evidence": "Cough eased after the dose was held.",
                },
                {
                    "question": "reappeared_on_rechallenge",
                    "answer": "yes",
                    "evidence": "It came back when I restarted it.",
                    "source": "patient_follow_up",
                    "information_request_id": str(REQUEST_ID),
                },
                {
                    "question": "dose_response",
                    "answer": "no",
                    "evidence": "Chart note reviewed.",
                    "source": "clinician_review",
                },
            ],
        },
        "patient": {
            "id": str(PATIENT_ID),
            "first_name": "Lucía",
            "last_name": "Ramírez",
            "email": "lucia.ramirez@example.test",
            "date_of_birth": "1961-07-14",
            "gender": "female",
        },
        "symptom": {
            "id": str(SYMPTOM_ID),
            "symptom": "Dry cough",
            "severity": 4,
            "onset": "2026-10-02",
            "notes": "Worse at night",
            "created_at": "2026-10-03T16:00:00+00:00",
        },
        "medication": {
            "id": str(MEDICATION_ID),
            "name": "Lisinopril",
            "dosage": "10 mg",
            "frequency": "daily",
            "route": "oral",
            "start_date": "2026-09-01",
            "end_date": None,
            "is_active": True,
            "instructions": "Take one tablet daily",
            "source_document_id": str(DOCUMENT_ID),
        },
        "clinician": {
            "id": str(CLINICIAN_ID),
            "first_name": "Elena",
            "last_name": "Park",
            "email": "elena.park@example.test",
            "specialty": "Internal medicine",
            "clinic_name": "Synthetic Valley Clinic",
        },
        "medications": [
            {"id": str(MEDICATION_ID), "name": "Lisinopril"},
            {"id": "m-2", "name": "Metformin", "start_date": "2024-01-10"},
            {"id": "m-3", "generic_name": "atorvastatin", "end_date": "2026-12-31"},
        ],
        "conditions": [
            {"name": "Hypertension", "status": "active"},
            {"name": "Old fracture", "status": "resolved"},
        ],
        "allergies": [{"allergen": "Penicillin", "reaction": "hives"}, {"allergen": "Latex"}],
        "rationale": "New cough on an ACE inhibitor; reporting for signal review.",
        "today": PREFILL_TODAY,
    }
    values.update(overrides)
    return Form3500Sources(**values)


def _by_path(evidence: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for entry in evidence:
        assert len(entry["field_paths"]) == 1, entry
        grouped.setdefault(entry["field_paths"][0], []).append(entry)
    return grouped


def _filled_paths(value: Any, prefix: str = "") -> list[str]:
    if isinstance(value, dict):
        paths: list[str] = []
        for key, item in value.items():
            paths.extend(_filled_paths(item, f"{prefix}.{key}" if prefix else key))
        return paths
    if isinstance(value, list) and value and isinstance(value[0], dict):
        paths = []
        for index, item in enumerate(value):
            paths.extend(_filled_paths(item, f"{prefix}[{index}]"))
        return paths
    if value in (None, "", [], False) or prefix == "form_version":
        return []
    return [prefix]


def test_prefill_maps_each_item_from_its_stored_source() -> None:
    form, evidence = build_form_3500(_sources())
    a, b, product = form.section_a, form.section_b, form.section_d.product_1
    assert DEFAULT_CODE_PATTERN.fullmatch(a.identifier) and a.identifier.startswith("LR-")
    assert (a.date_of_birth, a.sex) == ("1961-07-14", "F")
    assert b.report_types == ["adverse_event"]
    assert (b.event_date, b.event_date_confirmed) == ("2026-10-02", False)
    assert b.narrative == "Dry cough (patient-reported severity 4/10). Worse at night"
    assert b.other_history == "Conditions: Hypertension. Allergies: Penicillin (hives); Latex."
    assert (product.name, product.dose, product.dose_unit) == (
        "Lisinopril",
        "10",
        "MILLIGRAM(S) - MG",
    )
    assert (product.frequency, product.route) == ("Daily", "Oral")
    assert (product.therapy_start, product.therapy_stop, product.ongoing) == (
        "2026-09-01",
        None,
        "yes",
    )
    assert (product.abated, product.reappeared) == ("yes", "yes")
    assert [(row.name, row.start, row.end) for row in form.section_f.others] == [
        ("Metformin", "2024-01-10", None),
        ("atorvastatin", None, None),
    ]
    g = form.section_g
    assert (g.first_name, g.last_name, g.email) == ("Elena", "Park", "elena.park@example.test")
    review = form.mediagent_review
    assert (review.naranjo_score, review.causality) == (6, "Probable")
    assert review.reportability_rationale.startswith("New cough")
    assert form.legacy == {}


def test_every_filled_path_has_source_evidence() -> None:
    form, evidence = build_form_3500(_sources())
    grouped = _by_path(evidence)
    dumped = form.model_dump(mode="json")
    dumped.pop("legacy")
    for path in _filled_paths(dumped):
        if path == "section_b.event_date_confirmed":
            continue
        assert path in grouped, path
    assert grouped["section_d.product_1.name"][0]["source_type"] == "document_grounded_medication"
    assert grouped["section_d.product_1.name"][0]["citation"] == f"documents/{DOCUMENT_ID}"
    assert grouped["section_a.sex"][0]["citation"] == f"patients/{PATIENT_ID}"
    assert grouped["section_g.email"][0]["source_type"] == "authenticated_clinician"
    assert grouped["section_f.others[0].start"][0]["citation"] == "medications/m-2"
    assert {e["source_type"] for e in grouped["section_b.other_history"]} == {
        "patient_condition_record",
        "patient_allergy_record",
    }


def test_items_without_a_stored_source_stay_blank() -> None:
    form, _evidence = build_form_3500(_sources())
    a, b, g = form.section_a, form.section_b, form.section_g
    assert (a.race, a.hispanic_latino, a.weight_value, a.weight_unit, a.age_value) == (
        [],
        False,
        "",
        None,
        "",
    )
    assert (b.outcomes, b.death_date, b.report_date, b.tests, b.tests_comments) == (
        [],
        None,
        None,
        [],
        "",
    )
    product = form.section_d.product_1
    assert (product.ndc_or_unique_id, product.lot, product.manufacturer_compounder) == ("", "", "")
    assert (product.diagnosis_for_use, product.product_types, product.expiration_date) == (
        "",
        [],
        None,
    )
    assert form.section_d.product_2 is None
    assert (g.phone, g.address, g.city, g.country) == ("", "", "", "")
    assert (g.health_professional, g.occupation, g.also_reported_to) == (None, None, [])


@pytest.mark.parametrize("gender", ["other", "prefer_not_to_say", None, "FEMALE "])
def test_sex_is_only_prefilled_for_female_or_male(gender) -> None:
    patient = {**_sources().patient, "gender": gender}
    form, evidence = build_form_3500(_sources(patient=patient))
    assert form.section_a.sex is None
    assert "section_a.sex" not in _by_path(evidence)


def test_b3_falls_back_to_the_report_date_as_a_best_estimate() -> None:
    symptom = {**_sources().symptom, "onset": "a few hours after the new dose"}
    form, evidence = build_form_3500(_sources(symptom=symptom))
    assert (form.section_b.event_date, form.section_b.event_date_confirmed) == ("2026-10-03", False)
    entry = _by_path(evidence)["section_b.event_date"][0]
    assert entry["attribution"] == "Best estimate, confirm: date the symptom was reported"
    assert entry["citation"] == f"symptom_reports/{SYMPTOM_ID}"
    onset_entry = _by_path(build_form_3500(_sources())[1])["section_b.event_date"][0]
    assert onset_entry["attribution"] == "Best estimate, confirm: patient-reported onset"


def test_b3_uses_the_los_angeles_date_of_created_at() -> None:
    symptom = {**_sources().symptom, "onset": None, "created_at": "2026-10-03T05:30:00Z"}
    form, _evidence = build_form_3500(_sources(symptom=symptom))
    assert form.section_b.event_date == "2026-10-02"


def test_assessment_evidence_keeps_its_own_source() -> None:
    _form, evidence = build_form_3500(_sources())
    entries = _by_path(evidence)["mediagent_review.causality"]
    by_excerpt = {entry["excerpt"]: entry for entry in entries}
    ai = by_excerpt["Cough eased after the dose was held."]
    patient = by_excerpt["It came back when I restarted it."]
    other = by_excerpt["Chart note reviewed."]
    assert ai["source_type"] == "ai_extracted_adr_evidence"
    assert patient["source_type"] == "patient_confirmed_adr_evidence"
    assert patient["source_id"] == str(REQUEST_ID)
    assert other["source_type"] == "adr_assessment_evidence"
    confirmed = [e for e in evidence if e["source_type"] == "patient_confirmed_adr_evidence"]
    assert all(e["excerpt"] == "It came back when I restarted it." for e in confirmed)


def test_dechallenge_items_are_labelled_by_their_evidence_source() -> None:
    _form, evidence = build_form_3500(_sources())
    grouped = _by_path(evidence)
    assert grouped["section_d.product_1.abated"][0]["source_type"] == "ai_extracted_adr_evidence"
    assert grouped["section_d.product_1.reappeared"][0]["source_type"] == (
        "patient_confirmed_adr_evidence"
    )


@pytest.mark.parametrize("answer", ["do_not_know", None, "maybe"])
def test_unknown_naranjo_answers_leave_d7_and_d8_blank(answer) -> None:
    assessment = {
        **_sources().assessment,
        "naranjo_answers": {"improved_on_dechallenge": answer, "reappeared_on_rechallenge": answer},
    }
    form, evidence = build_form_3500(_sources(assessment=assessment))
    assert (form.section_d.product_1.abated, form.section_d.product_1.reappeared) == (None, None)
    assert "section_d.product_1.abated" not in _by_path(evidence)


def test_no_answers_map_no_to_no() -> None:
    assessment = {
        **_sources().assessment,
        "naranjo_answers": {"improved_on_dechallenge": "no", "reappeared_on_rechallenge": "no"},
        "evidence": [],
    }
    form, evidence = build_form_3500(_sources(assessment=assessment))
    assert (form.section_d.product_1.abated, form.section_d.product_1.reappeared) == ("no", "no")
    entry = _by_path(evidence)["section_d.product_1.abated"][0]
    assert entry["source_type"] == "deterministic_adr_assessment"


def test_b6_is_never_prefilled_from_observation_facts() -> None:
    facts = [
        {
            "fact_type": "observation",
            "code": "2160-0",
            "value": "1.4 mg/dL",
            "effective": "2026-10-01",
        },
        {
            "fact_type": "observation",
            "code": "8480-6",
            "value": "142 mmHg",
            "effective": "2026-10-01",
        },
    ]
    form, evidence = build_form_3500(_sources(clinical_facts=facts))
    assert form.section_b.tests == []
    assert not any(path.startswith("section_b.tests") for path in _by_path(evidence))


def test_reporter_identity_appears_only_in_section_g() -> None:
    form, _evidence = build_form_3500(_sources())
    outside_g = str(
        form.model_dump(mode="json", include={"section_a", "section_b", "section_d", "section_f"})
    ).casefold()
    for value in ("elena", "park", "synthetic valley clinic", "internal medicine"):
        assert value not in outside_g
    assert "lucía" not in outside_g and "ramírez" not in outside_g
    identity = patient_identity(_sources().patient)
    assert identifier_violations(form.section_a.identifier, identity) == []


def test_unsplittable_text_and_overflow_go_to_legacy() -> None:
    medication = {
        **_sources().medication,
        "dosage": "1 puff",
        "route": "inhaled",
        "frequency": "twice daily",
    }
    many = [{"id": f"m-{n}", "name": f"Synthetic {n}"} for n in range(12)]
    form, evidence = build_form_3500(_sources(medication=medication, medications=many))
    product = form.section_d.product_1
    assert (product.dose, product.dose_unit) == ("", None)
    assert (product.route, product.route_other) == ("Respiratory (inhalation)", "")
    assert (product.frequency, product.frequency_other) == ("Other", "twice daily")
    assert len(form.section_f.others) == 10
    assert form.legacy == {
        "medication.dosage": "1 puff",
        "medications.additional": "Synthetic 10; Synthetic 11",
    }
    assert "legacy.medication.dosage" in _by_path(evidence)


def test_future_and_reversed_medication_dates_are_not_used() -> None:
    medication = {
        **_sources().medication,
        "start_date": "2026-09-01",
        "end_date": "2026-08-01",
        "is_active": False,
    }
    form, _evidence = build_form_3500(_sources(medication=medication))
    product = form.section_d.product_1
    assert (product.therapy_start, product.therapy_stop, product.ongoing) == (
        "2026-09-01",
        None,
        None,
    )


@pytest.mark.asyncio
async def test_list_drafts_tags_the_links_clinic_and_filters_by_clinic() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from app.db.repositories.care_teams import CareTeamRepository
    from app.models.enums import ClinicianRole, ClinicMembershipStatus
    from app.services.medwatch_3500 import dates  # noqa: F401

    stored = _draft_row(form_data=_ready_payload())
    service = _service(seeded(medwatch_drafts=[stored]))
    links = [
        {
            "patient_id": stored["patient_id"],
            "clinic_id": CLINIC_A,
            "clinics": {"display_name": "Synthetic Valley Health"},
        }
    ]
    member = SimpleNamespace(
        clinic_id=UUID(CLINIC_A), role=ClinicianRole.PROVIDER, status=ClinicMembershipStatus.ACTIVE
    )
    with (
        patch.object(CareTeamRepository, "list_active_links", AsyncMock(return_value=links)),
        patch(
            "app.services.clinic_membership_service.ClinicMembershipService.active_memberships",
            new=AsyncMock(return_value=[member]),
        ),
    ):
        everything = await service.list_drafts(CLINICIAN)
        own = await service.list_drafts(CLINICIAN, clinic_id=UUID(CLINIC_A))
        other = await service.list_drafts(CLINICIAN, clinic_id=UUID(CLINIC_B))
    assert everything["items"][0]["clinic_name"] == "Synthetic Valley Health"
    assert len(own["items"]) == 1
    assert other == {"items": [], "total": 0}


CLINIC_A = "00000000-0000-0000-0000-00000000000a"
CLINIC_B = "00000000-0000-0000-0000-00000000000b"


def test_clinician_entered_answers_are_attributed_to_the_clinician() -> None:
    """PV-001-D: a clinician answer is never labelled patient-confirmed or AI-extracted."""
    assessment = {
        **_sources().assessment,
        "evidence": [
            {
                "question": "alternative_causes",
                "answer": "no",
                "evidence": "No other medicine or condition explains it.",
                "source": "clinician_entry",
                "recorded_by": "00000000-0000-4000-8000-0000000000c1",
            }
        ],
    }
    _form, evidence = build_form_3500(_sources(assessment=assessment))
    clinician = [e for e in evidence if e["source_type"] == "clinician_entered_adr_evidence"]
    assert len(clinician) == 1
    assert clinician[0]["attribution"] == "Clinician-entered Naranjo answer: alternative_causes"
    assert clinician[0]["excerpt"] == "No other medicine or condition explains it."
    assert clinician[0]["source_id"] is None


def test_patient_dechallenge_answer_fills_d7_with_patient_attribution() -> None:
    """PV-001-D: improved_on_dechallenge is now patient-answerable, so D7 can be patient-confirmed."""
    assessment = {
        **_sources().assessment,
        "naranjo_answers": {"improved_on_dechallenge": "yes"},
        "evidence": [
            {
                "question": "improved_on_dechallenge",
                "answer": "yes",
                "evidence": "It eased when my clinician paused it.",
                "source": "patient_follow_up",
                "information_request_id": str(REQUEST_ID),
            }
        ],
    }
    form, evidence = build_form_3500(_sources(assessment=assessment))
    assert form.section_d.product_1.abated == "yes"
    entry = _by_path(evidence)["section_d.product_1.abated"][0]
    assert entry["source_type"] == "patient_confirmed_adr_evidence"
    assert entry["excerpt"] == "It eased when my clinician paused it."
