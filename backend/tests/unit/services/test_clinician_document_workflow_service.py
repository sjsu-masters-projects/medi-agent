"""Focused unit tests for clinician document workflows."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import NotFoundError, ValidationError
from app.db.repositories import CareTeamRepository
from app.models.enums import DocumentReviewStatus
from app.services.clinician_document_workflow_service import (
    ClinicianDocumentWorkflowService,
)


def _response(*, data=None):
    return SimpleNamespace(data=data)


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def care_team_repo():
    return MagicMock(spec=CareTeamRepository)


@pytest.fixture
def execute():
    return AsyncMock()


@pytest.fixture
def service(mock_db, care_team_repo, execute):
    return ClinicianDocumentWorkflowService(
        db=mock_db,
        care_team_repo=care_team_repo,
        execute=execute,
    )


@pytest.mark.asyncio
async def test_fetch_patient_documents_hydrates_reviewer_metadata(service, execute):
    patient_id = uuid4()
    reviewer_id = uuid4()
    execute.side_effect = [
        _response(
            data=[
                {
                    "id": str(uuid4()),
                    "file_name": "lab.pdf",
                    "document_type": "lab_report",
                    "parse_status": "completed",
                    "ai_summary": "Summary",
                    "created_at": "2026-04-21T10:00:00Z",
                    "uploaded_by_role": "patient",
                    "clinician_annotation": "Review soon",
                    "review_status": "approved",
                    "reviewed_by": str(reviewer_id),
                    "reviewed_at": "2026-04-21T11:00:00Z",
                    "review_note": "Looks valid",
                }
            ]
        ),
        _response(
            data=[
                {
                    "id": str(reviewer_id),
                    "first_name": "Mina",
                    "last_name": "Shah",
                }
            ]
        ),
    ]

    documents = await service.fetch_patient_documents(patient_id)

    assert documents[0]["review_note"] == "Looks valid"
    assert documents[0]["reviewer"]["first_name"] == "Mina"
    assert execute.await_count == 2


@pytest.mark.asyncio
async def test_approve_document_review_updates_pending_patient_upload(
    service, care_team_repo, execute, mock_db
):
    clinician_id = uuid4()
    patient_id = uuid4()
    document_id = uuid4()
    chain = MagicMock()
    for method in ("select", "eq", "single", "update"):
        getattr(chain, method).return_value = chain
    mock_db.table.return_value = chain
    care_team_repo.find_active_assignment = AsyncMock(return_value=[{"id": str(uuid4())}])
    execute.side_effect = [
        _response(
            data={
                "id": str(document_id),
                "patient_id": str(patient_id),
                "uploaded_by_role": "patient",
                "review_status": "pending",
                "reviewed_by": None,
                "reviewed_at": None,
                "review_note": None,
            }
        ),
        _response(
            data=[
                {
                    "id": str(document_id),
                    "review_status": "approved",
                    "reviewed_by": str(clinician_id),
                    "reviewed_at": "2026-04-23T10:00:00Z",
                    "review_note": None,
                }
            ]
        ),
    ]

    result = await service.approve_document_review(clinician_id, patient_id, document_id)

    assert result["review_status"] == DocumentReviewStatus.APPROVED.value
    chain.update.assert_called_once()


@pytest.mark.asyncio
async def test_reject_document_review_rejects_already_reviewed_document(
    service, care_team_repo, execute
):
    care_team_repo.find_active_assignment = AsyncMock(return_value=[{"id": str(uuid4())}])
    execute.return_value = _response(
        data={
            "id": str(uuid4()),
            "patient_id": str(uuid4()),
            "uploaded_by_role": "patient",
            "review_status": "approved",
        }
    )

    with pytest.raises(ValidationError, match="already been completed"):
        await service.reject_document_review(uuid4(), uuid4(), uuid4(), "Bad upload")


@pytest.mark.asyncio
async def test_save_document_annotation_rejects_document_outside_patient_scope(
    service, care_team_repo, execute
):
    care_team_repo.find_active_assignment = AsyncMock(return_value=[{"id": str(uuid4())}])
    execute.return_value = _response(data=[])

    with pytest.raises(NotFoundError, match="Document"):
        await service.save_document_annotation(uuid4(), uuid4(), uuid4(), "Needs follow-up")
