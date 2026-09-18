"""The first two tools: one public lookup, one patient-scoped read.

The patient-scoped one carries the properties that matter — the patient comes from the
session and nowhere else, and the query is filtered by that patient rather than by
anything the model said.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.adk.tools import PATIENT_ID_STATE_KEY
from app.adk.tools import patient_context as patient_context_module
from app.adk.tools.drug_reference import lookup_rxnorm_ingredient
from app.adk.tools.patient_context import get_patient_context

PATIENT_ID = str(uuid4())


def _context(patient_id: object | None = PATIENT_ID) -> SimpleNamespace:
    state = {} if patient_id is None else {PATIENT_ID_STATE_KEY: patient_id}
    return SimpleNamespace(state=state)


# ---------------------------------------------------------------------------
# lookup_rxnorm_ingredient — public terminology, no patient scope
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_brand_name_resolves_to_its_ingredient() -> None:
    resolved = {
        "original_name": "Coumadin",
        "normalized_name": "warfarin",
        "rxcui": "11289",
        "brand_names": ["Coumadin", "Jantoven"],
    }

    with patch(
        "app.adk.tools.drug_reference.normalize_drug_name",
        AsyncMock(return_value=resolved),
    ):
        result = await lookup_rxnorm_ingredient("Coumadin")

    assert result["ingredient"] == "warfarin"
    assert result["rxcui"] == "11289"


@pytest.mark.asyncio
async def test_an_unresolved_drug_returns_a_readable_error_not_an_exception() -> None:
    """A raised error ends the turn; a result lets the model ask what was meant."""
    with patch(
        "app.adk.tools.drug_reference.normalize_drug_name",
        AsyncMock(return_value={"error": "Drug not found in RxNorm"}),
    ):
        result = await lookup_rxnorm_ingredient("nonexistent")

    assert "error" in result


@pytest.mark.asyncio
async def test_an_empty_drug_name_does_not_reach_the_service() -> None:
    service = AsyncMock()

    with patch("app.adk.tools.drug_reference.normalize_drug_name", service):
        result = await lookup_rxnorm_ingredient("   ")

    assert "error" in result
    service.assert_not_awaited()


# ---------------------------------------------------------------------------
# get_patient_context — the first tool to touch patient rows
# ---------------------------------------------------------------------------


def test_the_patient_is_not_part_of_the_tool_surface() -> None:
    """The model supplies nothing. `tool_context` is injected and stripped from the schema."""
    assert list(inspect.signature(get_patient_context).parameters) == ["tool_context"]


@pytest.mark.asyncio
async def test_the_query_is_filtered_by_the_session_patient() -> None:
    """The identifier passed to the read is the boundary — RLS is not behind this."""
    service = MagicMock()
    service.get_context = AsyncMock(return_value={})

    with patch.object(patient_context_module, "_service", return_value=service):
        await get_patient_context(_context())

    service.get_context.assert_awaited_once_with(PATIENT_ID)


@pytest.mark.asyncio
async def test_a_missing_patient_reads_nothing_at_all() -> None:
    """No patient in scope must mean no query, not a query with no filter."""
    service = MagicMock()
    service.get_context = AsyncMock(return_value={})

    with patch.object(patient_context_module, "_service", return_value=service):
        result = await get_patient_context(_context(patient_id=None))

    service.get_context.assert_not_awaited()
    assert "error" in result


@pytest.mark.asyncio
async def test_a_malformed_patient_reads_nothing_at_all() -> None:
    service = MagicMock()
    service.get_context = AsyncMock(return_value={})

    with patch.object(patient_context_module, "_service", return_value=service):
        result = await get_patient_context(_context(patient_id="' OR 1=1 --"))

    service.get_context.assert_not_awaited()
    assert "error" in result


@pytest.mark.asyncio
async def test_the_refusal_does_not_name_the_patient() -> None:
    service = MagicMock()
    service.get_context = AsyncMock(return_value={})

    with patch.object(patient_context_module, "_service", return_value=service):
        result = await get_patient_context(_context(patient_id="maria-gomez-42"))

    assert "maria-gomez-42" not in str(result)


@pytest.mark.asyncio
async def test_the_clinical_context_is_returned() -> None:
    service = MagicMock()
    service.get_context = AsyncMock(
        return_value={
            "medications": [{"name": "Metformin"}],
            "conditions": [{"name": "Type 2 diabetes"}],
            "recent_symptoms": [{"symptom": "fatigue"}],
            "care_teams": [{"clinician_name": "Dr Reyes"}],
        }
    )

    with patch.object(patient_context_module, "_service", return_value=service):
        result = await get_patient_context(_context())

    assert result["medications"] == [{"name": "Metformin"}]
    assert result["care_teams"] == [{"clinician_name": "Dr Reyes"}]


@pytest.mark.asyncio
async def test_the_attached_document_blob_is_not_returned() -> None:
    """`get_context` carries a document for the chat route; a context read is not that."""
    service = MagicMock()
    service.get_context = AsyncMock(
        return_value={"medications": [], "document": {"summary": "discharge summary text"}}
    )

    with patch.object(patient_context_module, "_service", return_value=service):
        result = await get_patient_context(_context())

    assert "document" not in result
    assert "discharge summary text" not in str(result)
