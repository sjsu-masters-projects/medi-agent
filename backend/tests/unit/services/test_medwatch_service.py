"""Tests for evidence-grounded MedWatch draft orchestration."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.models.adr import (
    MedWatchDraftApprovalRequest,
    MedWatchDraftCreateRequest,
    MedWatchDraftUpdateRequest,
    MedWatchFormData,
)
from app.services.medwatch_service import MedWatchService


def _response(data=None):
    return SimpleNamespace(data=data)


@pytest.fixture
def service() -> MedWatchService:
    db = MagicMock()
    chain = MagicMock()
    for method in ("select", "eq", "in_", "limit", "order", "single"):
        getattr(chain, method).return_value = chain
    db.table.return_value = chain
    return MedWatchService(db)


def _form(*, patient_identifier: str = "Maya Patel") -> MedWatchFormData:
    return MedWatchFormData.model_validate(
        {
            "patient": {
                "patient_identifier": patient_identifier,
                "date_of_birth": "1988-04-03",
                "sex": "female",
            },
            "event": {
                "description": "Dizziness",
                "onset_date_or_time": "2026-10-01",
                "outcome": "",
                "seriousness": "",
            },
            "suspect_product": {
                "name": "Fluticasone/salmeterol",
                "dose": "1 puff",
                "frequency": "twice daily",
                "route": "inhaled",
                "therapy_start_date": "2026-09-28",
                "therapy_end_date": "",
            },
            "concomitant_products": {"products": "Albuterol"},
            "tests_and_history": {
                "relevant_tests": "",
                "other_relevant_history": "",
            },
            "reporter": {
                "name": "Elena Park",
                "email": "elena@example.com",
                "specialty": "Internal medicine",
                "clinic_name": "MediAgent Clinic",
            },
            "clinical_review": {
                "naranjo_score": 6,
                "causality": "Probable",
                "reportability_rationale": "Clinically significant new event.",
            },
        }
    )


@pytest.mark.asyncio
async def test_create_draft_uses_patient_facts_and_keeps_unknown_fields_empty(service) -> None:
    clinician_id = uuid4()
    patient_id = uuid4()
    assessment_id = uuid4()
    symptom_id = uuid4()
    medication_id = uuid4()
    document_id = uuid4()
    draft_id = uuid4()
    service.care_team_repo.find_active_assignment = AsyncMock(return_value=[{"id": "team"}])
    service._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _response(
                {
                    "id": str(assessment_id),
                    "patient_id": str(patient_id),
                    "symptom_report_id": str(symptom_id),
                    "suspect_medication_id": str(medication_id),
                    "suspect_medication_name": "Fluticasone/salmeterol",
                    "naranjo_score": 6,
                    "causality": "Probable",
                    "status": "draft",
                    "evidence": [
                        {
                            "question": "dose_response",
                            "answer": "yes",
                            "evidence": "Symptoms improved after the prior dose was reduced.",
                        }
                    ],
                }
            ),
            _response([]),
            _response(
                {
                    "id": str(patient_id),
                    "first_name": "Maya",
                    "last_name": "Patel",
                    "date_of_birth": "1988-04-03",
                    "gender": "female",
                }
            ),
            _response(
                {
                    "id": str(symptom_id),
                    "symptom": "dizziness",
                    "severity": 2,
                    "onset": "a few hours after starting",
                    "notes": None,
                }
            ),
            _response(
                {
                    "id": str(medication_id),
                    "name": "Fluticasone/salmeterol",
                    "dosage": "1 puff",
                    "frequency": "twice daily",
                    "route": "inhaled",
                    "start_date": "2026-09-28",
                    "end_date": None,
                    "instructions": "Use twice daily",
                    "source_document_id": str(document_id),
                }
            ),
            _response(
                {
                    "id": str(clinician_id),
                    "first_name": "Elena",
                    "last_name": "Park",
                    "email": "elena@example.com",
                    "specialty": "Internal medicine",
                    "clinic_name": "MediAgent Clinic",
                }
            ),
            _response(
                [
                    {"id": str(medication_id), "name": "Fluticasone/salmeterol"},
                    {"id": str(uuid4()), "name": "Albuterol"},
                ]
            ),
            _response([{"id": str(draft_id), "status": "draft"}]),
        ]
    )

    result = await service.create_draft(
        clinician_id,
        assessment_id,
        MedWatchDraftCreateRequest(
            decision="prepare_draft",
            reportability_rationale="Clinically significant new event.",
        ),
    )

    assert result["id"] == str(draft_id)
    rpc_name, payload = service.db.rpc.call_args.args
    assert rpc_name == "create_medwatch_draft"
    assert payload["p_form_data"]["event"]["outcome"] == ""
    assert payload["p_form_data"]["tests_and_history"]["relevant_tests"] == ""
    assert payload["p_form_data"]["concomitant_products"]["products"] == "Albuterol"
    assert any(
        item["source_type"] == "document_grounded_medication"
        and item["citation"] == f"documents/{document_id}"
        for item in payload["p_source_evidence"]
    )
    assert any(
        item["source_type"] == "patient_confirmed_adr_evidence"
        for item in payload["p_source_evidence"]
    )


@pytest.mark.asyncio
async def test_update_draft_audits_only_changed_leaf_fields(service) -> None:
    clinician_id = uuid4()
    patient_id = uuid4()
    draft_id = uuid4()
    current = _form()
    updated = current.model_copy(deep=True)
    updated.event.outcome = "Recovering"
    service.care_team_repo.find_active_assignment = AsyncMock(return_value=[{"id": "team"}])
    service._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            _response(
                {
                    "id": str(draft_id),
                    "patient_id": str(patient_id),
                    "status": "draft",
                    "revision": 1,
                    "form_data": current.model_dump(mode="json"),
                }
            ),
            _response([{"id": str(draft_id), "revision": 2, "status": "draft"}]),
        ]
    )

    await service.update_draft(
        clinician_id,
        draft_id,
        MedWatchDraftUpdateRequest(form_data=updated, expected_revision=1),
    )

    rpc_name, payload = service.db.rpc.call_args.args
    assert rpc_name == "update_medwatch_draft"
    assert payload["p_changed_fields"] == ["event.outcome"]


@pytest.mark.asyncio
async def test_approval_rejects_incomplete_draft_before_rpc(service) -> None:
    clinician_id = uuid4()
    patient_id = uuid4()
    draft_id = uuid4()
    service.care_team_repo.find_active_assignment = AsyncMock(return_value=[{"id": "team"}])
    service._execute = AsyncMock(  # type: ignore[method-assign]
        return_value=_response(
            {
                "id": str(draft_id),
                "patient_id": str(patient_id),
                "status": "draft",
                "revision": 1,
                "form_data": _form(patient_identifier="").model_dump(mode="json"),
            }
        )
    )

    with pytest.raises(ValidationError, match="patient identifier"):
        await service.approve_draft(
            clinician_id,
            draft_id,
            MedWatchDraftApprovalRequest(
                approval_note="Reviewed source evidence.",
                expected_revision=1,
                attested=True,
            ),
        )

    service.db.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_export_marks_artifact_as_not_submitted_to_fda(service) -> None:
    clinician_id = uuid4()
    patient_id = uuid4()
    draft_id = uuid4()
    assessment_id = uuid4()
    approved = {
        "id": str(draft_id),
        "patient_id": str(patient_id),
        "adr_assessment_id": str(assessment_id),
        "status": "reviewed",
        "approved_by": str(clinician_id),
        "approved_at": "2026-10-09T11:00:00Z",
        "approval_note": "Reviewed source evidence.",
        "revision": 2,
        "export_version": "medwatch-3500a-draft-v1",
        "form_data": _form().model_dump(mode="json"),
        "source_evidence": [],
        "clinician_edited_fields": [],
    }
    service.care_team_repo.find_active_assignment = AsyncMock(return_value=[{"id": "team"}])
    service._execute = AsyncMock(  # type: ignore[method-assign]
        side_effect=[_response(approved), _response([approved])]
    )

    result = await service.export_draft(clinician_id, draft_id)

    assert result["content"]["not_submitted_to_fda"] is True
    assert "submitted" not in result["content"]["approval"]
    service.db.rpc.assert_called_once_with(
        "record_medwatch_draft_export",
        {"p_draft_id": str(draft_id), "p_actor_id": str(clinician_id)},
    )


def test_approval_requires_explicit_attestation() -> None:
    with pytest.raises(ValueError, match="attestation"):
        MedWatchDraftApprovalRequest(
            approval_note="Reviewed source evidence.",
            expected_revision=1,
            attested=False,
        )
