"""Read-only, assignment-scoped care-plan revision context."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.core.exceptions import AuthorizationError
from app.services.care_plan_service import CarePlanService

PATIENT_ID = UUID("00000000-0000-0000-0000-000000000201")
CLINICIAN_ID = UUID("00000000-0000-0000-0000-000000000202")


def test_review_context_returns_active_and_proposed_versions() -> None:
    db = MagicMock()
    service = CarePlanService(db)
    service._require_assignment = MagicMock()  # type: ignore[method-assign]
    service._plans = MagicMock(  # type: ignore[method-assign]
        return_value=[
            {"id": "draft", "status": "draft", "version_number": 2},
            {"id": "approved", "status": "approved", "version_number": 1},
        ]
    )
    service._hydrate_plan = MagicMock(side_effect=lambda plan: {**plan, "items": []})  # type: ignore[method-assign]
    db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "preferred_language": "en-US"
    }

    result = service.get_review_context_for_clinician(CLINICIAN_ID, PATIENT_ID)

    assert result["latest"]["version_number"] == 2
    assert result["active"]["version_number"] == 1
    assert result["patient_locale"] == "en-US"
    service._require_assignment.assert_called_once_with(CLINICIAN_ID, PATIENT_ID)


def test_review_context_denies_unassigned_clinician_before_reading_plans() -> None:
    db = MagicMock()
    service = CarePlanService(db)
    service._require_assignment = MagicMock(  # type: ignore[method-assign]
        side_effect=AuthorizationError("You are not assigned to this patient")
    )

    with pytest.raises(AuthorizationError):
        service.get_review_context_for_clinician(CLINICIAN_ID, PATIENT_ID)

    db.table.assert_not_called()


def test_hydrated_item_retains_every_supporting_document() -> None:
    db = MagicMock()
    responses = {
        "care_plan_items": [{"id": "item-1", "source_fact_id": "fact-1"}],
        "evidence_citations": [
            {
                "fact_id": "fact-1",
                "provenance_id": "source-1",
                "excerpt": "first",
                "location": {"page": 1},
            },
            {
                "fact_id": "fact-1",
                "provenance_id": "source-2",
                "excerpt": "second",
                "location": {"page": 2},
            },
        ],
        "source_provenances": [
            {"id": "source-1", "document_id": "document-1", "document_location": {}},
            {"id": "source-2", "document_id": "document-2", "document_location": {}},
        ],
        "documents": [
            {"id": "document-1", "file_name": "first.pdf"},
            {"id": "document-2", "file_name": "second.pdf"},
        ],
    }

    def table(name: str) -> MagicMock:
        query = MagicMock()
        query.select.return_value = query
        query.eq.return_value = query
        query.in_.return_value = query
        query.order.return_value = query
        query.execute.return_value.data = responses[name]
        return query

    db.table.side_effect = table
    plan = CarePlanService(db)._hydrate_plan({"id": str(PATIENT_ID)})

    assert [source["file_name"] for source in plan["items"][0]["sources"]] == [
        "first.pdf",
        "second.pdf",
    ]
    assert plan["items"][0]["source"]["excerpt"] == "first"
