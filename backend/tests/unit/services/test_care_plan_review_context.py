"""Read-only, assignment-scoped care-plan revision context."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.core.exceptions import AuthorizationError, ValidationError
from app.models.care_plan import CarePlanDraftUpdate
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
    service._active_medications = MagicMock(return_value=[])  # type: ignore[method-assign]
    db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = {
        "preferred_language": "en-US"
    }

    result = service.get_review_context_for_clinician(CLINICIAN_ID, PATIENT_ID)

    assert result["latest"]["version_number"] == 2
    assert result["active"]["version_number"] == 1
    assert result["patient_locale"] == "en-US"
    assert result["active_medications"] == []
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
            {
                "fact_id": "fact-1",
                "provenance_id": "source-1",
                "excerpt": "first",
                "location": {"page": 1},
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


def test_medication_decision_requires_explicit_match_or_new_name() -> None:
    active = [{"id": "med-1", "name": "Metformin", "dosage": "500 mg"}]
    validate = CarePlanService._validate_medication_decision

    with pytest.raises(ValidationError, match="already exists"):
        validate({"decision": "create", "name": "metformin"}, active)
    with pytest.raises(ValidationError, match="Choose an active matching"):
        validate({"decision": "update", "target_id": "someone-else", "name": "Metformin"}, active)
    with pytest.raises(ValidationError, match="Choose an active matching"):
        validate({"decision": "update", "target_id": "med-1", "name": "Different"}, active)
    validate({"decision": "update", "target_id": "med-1", "name": "metformin"}, active)
    validate({"decision": "create", "name": "Loratadine"}, active)


def test_approval_denies_unreviewed_patient_language_before_rpc() -> None:
    db = MagicMock()
    service = CarePlanService(db)
    service._require_assignment = MagicMock()  # type: ignore[method-assign]
    service._draft = MagicMock(return_value={"id": str(PATIENT_ID)})  # type: ignore[method-assign]
    service._patient_locale = MagicMock(return_value="en-US")  # type: ignore[method-assign]
    service._active_medications = MagicMock(return_value=[])  # type: ignore[method-assign]
    service._items = MagicMock(  # type: ignore[method-assign]
        return_value=[{"category": "movement", "is_removed": False, "reviewed_locale": None}]
    )

    with pytest.raises(ValidationError, match="patient's language"):
        service.approve(CLINICIAN_ID, PATIENT_ID, PATIENT_ID, "reviewed")

    db.rpc.assert_not_called()


def test_approval_denies_unmatched_medication_before_rpc() -> None:
    db = MagicMock()
    service = CarePlanService(db)
    service._require_assignment = MagicMock()  # type: ignore[method-assign]
    service._draft = MagicMock(return_value={"id": str(PATIENT_ID)})  # type: ignore[method-assign]
    service._patient_locale = MagicMock(return_value="en-US")  # type: ignore[method-assign]
    service._active_medications = MagicMock(  # type: ignore[method-assign]
        return_value=[{"id": "med-1", "name": "Metformin"}]
    )
    service._items = MagicMock(  # type: ignore[method-assign]
        return_value=[
            {
                "category": "medication",
                "is_removed": False,
                "reviewed_locale": "en-US",
                "medication": {"decision": "create", "name": "Metformin"},
            }
        ]
    )

    with pytest.raises(ValidationError, match="already exists"):
        service.approve(CLINICIAN_ID, PATIENT_ID, PATIENT_ID, "reviewed")

    db.rpc.assert_not_called()


def test_approval_calls_transaction_for_reviewed_matching_medication() -> None:
    db = MagicMock()
    service = CarePlanService(db)
    service._require_assignment = MagicMock()  # type: ignore[method-assign]
    service._draft = MagicMock(return_value={"id": str(PATIENT_ID)})  # type: ignore[method-assign]
    service._patient_locale = MagicMock(return_value="en-US")  # type: ignore[method-assign]
    service._active_medications = MagicMock(  # type: ignore[method-assign]
        return_value=[{"id": "med-1", "name": "Metformin"}]
    )
    service._items = MagicMock(  # type: ignore[method-assign]
        return_value=[
            {
                "category": "medication",
                "is_removed": False,
                "reviewed_locale": "en-US",
                "frequency": "daily",
                "medication": {
                    "decision": "update",
                    "target_id": "med-1",
                    "name": "Metformin",
                    "frequency": "daily",
                },
            }
        ]
    )
    db.rpc.return_value.execute.return_value.data = {"status": "approved"}

    result = service.approve(CLINICIAN_ID, PATIENT_ID, PATIENT_ID, "Reviewed source")

    assert result["status"] == "approved"
    db.rpc.assert_called_once_with(
        "approve_care_plan_version",
        {
            "p_plan_version_id": str(PATIENT_ID),
            "p_reviewer_id": str(CLINICIAN_ID),
            "p_note": "Reviewed source",
        },
    )

    db.rpc.reset_mock()
    service._items.return_value[0]["frequency"] = "twice daily"
    with pytest.raises(ValidationError, match="frequency must match"):
        service.approve(CLINICIAN_ID, PATIENT_ID, PATIENT_ID, "Reviewed source")
    db.rpc.assert_not_called()


def test_draft_save_persists_explicit_locale_review() -> None:
    db = MagicMock()
    service = CarePlanService(db)
    service._require_assignment = MagicMock()  # type: ignore[method-assign]
    service._draft = MagicMock(return_value={"id": str(PATIENT_ID)})  # type: ignore[method-assign]
    service._items = MagicMock(  # type: ignore[method-assign]
        return_value=[{"id": str(PATIENT_ID), "category": "movement", "confidence_score": 0.95}]
    )
    service._patient_locale = MagicMock(return_value="en-US")  # type: ignore[method-assign]
    service._active_medications = MagicMock(return_value=[])  # type: ignore[method-assign]
    service._audit = MagicMock()  # type: ignore[method-assign]
    service._plan = MagicMock(return_value={"id": str(PATIENT_ID)})  # type: ignore[method-assign]
    service._hydrate_plan = MagicMock(return_value={})  # type: ignore[method-assign]
    update = CarePlanDraftUpdate.model_validate(
        {
            "items": [
                {
                    "id": str(PATIENT_ID),
                    "title": "Walk",
                    "instructions": "Walk 20 minutes",
                    "frequency": "daily",
                    "language_verified": True,
                    "verified_locale": "en-US",
                }
            ]
        }
    )

    service.update_draft(CLINICIAN_ID, PATIENT_ID, PATIENT_ID, update)

    db.table.return_value.update.assert_called_once()
    assert db.table.return_value.update.call_args.args[0]["reviewed_locale"] == "en-US"

    db.table.return_value.update.reset_mock()
    stale = update.model_copy(deep=True)
    stale.items[0].verified_locale = "es-MX"
    with pytest.raises(ValidationError, match="language changed"):
        service.update_draft(CLINICIAN_ID, PATIENT_ID, PATIENT_ID, stale)
    db.table.return_value.update.assert_not_called()
