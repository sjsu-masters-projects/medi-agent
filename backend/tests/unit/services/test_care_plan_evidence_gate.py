"""Patient-upload acceptance is independent of successful parsing."""

from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.core.exceptions import ValidationError
from app.services.care_plan_evidence_gate import eligible_fact_ids
from app.services.care_plan_service import CarePlanService


def query(data):
    chain = MagicMock()
    for method in ("select", "eq", "in_"):
        getattr(chain, method).return_value = chain
    chain.execute.return_value.data = data
    return chain


@pytest.mark.parametrize(
    "role,status,expected",
    [
        ("patient", "pending", set()),
        ("patient", "rejected", set()),
        ("patient", None, set()),
        ("patient", "approved", {"fact"}),
        ("clinician", None, {"fact"}),
        ("unknown", "approved", set()),
    ],
)
def test_document_review_gate(role, status, expected):
    db = MagicMock()
    chains = {
        "evidence_citations": query(
            [
                {
                    "fact_id": "fact",
                    "source_provenances": {"artifact_type": "document", "document_id": "doc"},
                }
            ]
        ),
        "documents": query([{"id": "doc", "uploaded_by_role": role, "review_status": status}]),
    }
    db.table.side_effect = chains.__getitem__
    assert eligible_fact_ids(db, UUID(int=1), ["fact"]) == expected
    chains["documents"].eq.assert_called_once_with("patient_id", str(UUID(int=1)))


@pytest.mark.parametrize(
    "withdrawn,documents",
    [
        (None, []),
        ("2026-10-09", [{"id": "doc", "uploaded_by_role": "patient", "review_status": "approved"}]),
    ],
)
def test_missing_or_withdrawn_document_cannot_be_rescued_by_another_citation(withdrawn, documents):
    db = MagicMock()
    chains = {
        "evidence_citations": query(
            [
                {"fact_id": "fact", "source_provenances": {"artifact_type": "clinician_entry"}},
                {
                    "fact_id": "fact",
                    "source_provenances": {
                        "artifact_type": "document",
                        "document_id": "doc",
                        "withdrawn_at": withdrawn,
                    },
                },
            ]
        ),
        "documents": query(documents),
    }
    db.table.side_effect = chains.__getitem__
    assert eligible_fact_ids(db, UUID(int=1), ["fact"]) == set()


def test_no_citation_and_empty_fact_list_fail_closed():
    db = MagicMock()
    db.table.return_value = query([])
    assert eligible_fact_ids(db, UUID(int=1), ["fact"]) == set()
    db.reset_mock()
    assert eligible_fact_ids(db, UUID(int=1), []) == set()
    db.table.assert_not_called()


@pytest.mark.parametrize("status", ["pending", "rejected", None])
def test_stale_draft_preflight_blocks_publication_before_rpc(status):
    db = MagicMock()
    chains = {
        "evidence_citations": query(
            [
                {
                    "fact_id": "fact",
                    "source_provenances": {"artifact_type": "document", "document_id": "doc"},
                }
            ]
        ),
        "documents": query([{"id": "doc", "uploaded_by_role": "patient", "review_status": status}]),
    }
    db.table.side_effect = chains.__getitem__
    service = CarePlanService(db)
    service._require_assignment = MagicMock()
    service._draft = MagicMock()
    service.generation_for_clinician = MagicMock(return_value={"status": "completed"})
    service._patient_locale = MagicMock(return_value="en-US")
    service._active_medications = MagicMock(return_value=[])
    service._items = MagicMock(
        return_value=[
            {"source_fact_id": "fact", "category": "movement", "reviewed_locale": "en-US"}
        ]
    )
    with pytest.raises(ValidationError, match="source documents before preview or publication"):
        service.approve(UUID(int=1), UUID(int=2), UUID(int=3), "Synthetic review")
    db.rpc.assert_not_called()
