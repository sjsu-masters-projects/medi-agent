"""Keep imported evidence and overlapping proposals out of accidental publication."""

from copy import deepcopy
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.core.exceptions import ValidationError
from app.services.care_plan_reconciliation import overlaps, publication_key
from app.services.care_plan_service import CarePlanService


def query(data):
    result = MagicMock()
    for method in ("select", "eq", "in_", "order", "limit", "insert"):
        getattr(result, method).return_value = result
    result.execute.return_value.data = data
    return result


def activity(item_id="one", **changes):
    return {
        "id": item_id,
        "category": "movement",
        "instructions": "Walk 20 minutes",
        "frequency": "daily",
        "schedule": {},
        "reviewed_locale": "en-US",
        **changes,
    }


def test_strength_and_form_suffixes_require_review_without_changing_source_names():
    items = [
        activity("one", category="medication", medication={"name": "Metformin"}),
        activity("two", category="medication", medication={"name": "Metformin 500 mg tablet"}),
        activity("three", category="medication", medication={"name": "Metformin ER 500 mg tablet"}),
    ]
    original = deepcopy(items)
    assert overlaps(items, []) == {"one": ["two"], "two": ["one"]}
    assert items == original
    items[1]["is_removed"] = True
    assert overlaps(items, []) == {}


def test_generation_requires_live_document_or_clinician_entry_provenance():
    facts = [{"id": str(index)} for index in range(7)]
    sources = [
        {"artifact_type": "document", "document_id": "doc"},
        {"artifact_type": "clinician_entry"},
        {"artifact_type": "fhir_resource"},
        {"artifact_type": "external_record"},
        {"artifact_type": "document", "document_id": "doc", "withdrawn_at": "2026-10-01"},
        {"artifact_type": "document", "document_id": None},
    ]
    citations = [
        {"fact_id": str(index), "source_provenances": source}
        for index, source in enumerate(sources)
    ]
    db = MagicMock()
    chains = {"clinical_facts": query(facts), "evidence_citations": query(citations)}
    db.table.side_effect = chains.__getitem__
    assert CarePlanService(db)._plan_facts(UUID(int=1)) == facts[:2]
    chains["clinical_facts"].eq.assert_called_with("patient_id", str(UUID(int=1)))
    # No source/fact mutation and no publication during evidence selection.
    chains["clinical_facts"].update.assert_not_called()
    db.rpc.assert_not_called()


def test_exact_source_overlap_preserves_translated_carried_wording_and_all_rows():
    items = [
        activity(source_fact_id="fact-1"),
        activity("two", source_fact_id="fact-2", instructions="Caminar 20 minutos"),
    ]
    facts = [
        {
            "id": fact_id,
            "fact_type": "obligation",
            "value": {"description": "Caminar 20 minutos", "frequency": "daily"},
        }
        for fact_id in ("fact-1", "fact-2")
    ]
    original = deepcopy(items)
    assert overlaps(items, facts) == {"one": ["two"], "two": ["one"]}
    assert items == original
    items[1]["is_removed"] = True
    assert overlaps(items, facts) == {}


def test_different_cadence_requires_review_but_event_context_is_distinct():
    items = [
        activity(),
        activity("two", frequency="three times weekly"),
        activity("three", schedule={"event": "after dinner"}),
    ]
    original = deepcopy(items)
    assert overlaps(items, []) == {"one": ["two"], "two": ["one"]}
    assert items == original


def test_same_medication_name_groups_even_incompatible_doses_for_review():
    items = [
        activity(
            "one", category="medication", medication={"name": "Metformin", "dosage": "500 mg"}
        ),
        activity(
            "two", category="medication", medication={"name": " metformin ", "dosage": "1000 mg"}
        ),
    ]
    assert overlaps(items, []) == {"one": ["two"], "two": ["one"]}
    assert publication_key(activity(instructions="")) is None


def test_approval_denies_identical_activity_without_writing_projection():
    db = MagicMock()
    service = CarePlanService(db)
    service._require_assignment = MagicMock()
    service._draft = MagicMock()
    service._patient_locale = MagicMock(return_value="en-US")
    service._active_medications = MagicMock(return_value=[])
    service.generation_for_clinician = MagicMock(return_value={"status": "completed"})
    service._items = MagicMock(return_value=[activity(), activity("two")])
    with pytest.raises(ValidationError, match="overlapping"):
        service.approve(UUID(int=1), UUID(int=2), UUID(int=3), "Reviewed")
    db.rpc.assert_not_called()
    service._items.return_value[1]["is_removed"] = True
    service.approve(UUID(int=1), UUID(int=2), UUID(int=3), "Reviewed")
    db.rpc.assert_called_once()


def test_revision_links_carried_medication_to_approved_projection():
    db = MagicMock()
    existing = query([])
    created_plan, inserted = MagicMock(), MagicMock()
    created_plan.insert.return_value.execute.return_value.data = [{"id": str(UUID(int=3))}]
    db.table.side_effect = (
        lambda name: existing
        if name == "care_plan_versions" and not existing.select.called
        else created_plan
        if name == "care_plan_versions"
        else inserted
    )
    service = CarePlanService(db)
    service._plans = MagicMock(
        return_value=[{"id": str(UUID(int=2)), "status": "approved", "version_number": 1}]
    )
    service._items = MagicMock(
        return_value=[
            activity(
                category="medication",
                medication={"name": "Metformin", "decision": "create"},
                projection_type="medication",
                projection_id=str(UUID(int=4)),
            )
        ]
    )
    service._open_draft(UUID(int=1), "2026-10-01T00:00:00Z")
    medication = inserted.insert.call_args.args[0]["medication"]
    assert medication["decision"] == "update"
    assert medication["target_id"] == str(UUID(int=4))
    assert service._items.return_value[0]["medication"]["decision"] == "create"


def test_unsupported_route_cannot_be_confirmed_past_publication_boundary():
    assert "supported medication route" in CarePlanService._blocker(
        category="medication",
        title="Medication",
        instructions="Source wording",
        frequency="daily",
        medication={
            "name": "Metformin",
            "dosage": "500 mg",
            "frequency": "daily",
            "route": "by mouth",
        },
        confidence=1,
        removed=False,
        confirmed=True,
    )
