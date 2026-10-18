"""A patient sees only their own document's results, as printed, with review status."""

from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from app.core.exceptions import NotFoundError
from app.services.document_service import DocumentService

DOCUMENT = UUID("11111111-1111-1111-1111-111111111111")
PATIENT = UUID("22222222-2222-2222-2222-222222222222")


def _fact(index: int, fact_type: str, state: str, **value: str) -> dict:
    return {
        "id": f"fact-{index}",
        "fact_type": fact_type,
        "review_state": state,
        "external_source_key": f"document/{DOCUMENT}/{fact_type}/{index}",
        "value": value,
    }


def _service(facts: list[dict]) -> DocumentService:
    service = DocumentService(MagicMock())
    service._get_document_row = MagicMock(return_value={"id": str(DOCUMENT)})  # type: ignore[method-assign]
    service._fact_pages = MagicMock(return_value={"fact-3": 1})  # type: ignore[method-assign]
    patcher = patch("app.services.document_service.ClinicalFactService")
    registry = patcher.start()
    registry.return_value.list_facts_for_document.return_value = facts
    return service


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


def test_results_are_printed_values_in_document_order_with_review_status() -> None:
    service = _service(
        [
            _fact(5, "vital_sign", "approved", name="Pulse", value="72", unit="bpm"),
            _fact(
                3,
                "lab_result",
                "pending_review",
                test_name="Hemoglobin A1c",
                value="7.8",
                unit="%",
                reference_range="4.0 - 5.6",
                flag="H",
                flag_meaning="high",
                range_status="above",
                panel="Glycemic control",
                consistency="reviewer note",
            ),
            _fact(1, "medication", "approved", name="Metformin", dosage="500 mg"),
            _fact(4, "lab_result", "rejected", test_name="Sodium", value="139"),
        ]
    )
    rows = service.list_document_results(DOCUMENT, PATIENT)
    assert [row["name"] for row in rows] == ["Hemoglobin A1c", "Pulse"]
    a1c = rows[0]
    assert a1c == {
        "kind": "lab_result",
        "name": "Hemoglobin A1c",
        "value": "7.8",
        "unit": "%",
        "reference_range": "4.0 - 5.6",
        "flag": "H",
        "flag_meaning": "high",
        "range_status": "above",
        "panel": "Glycemic control",
        "observed_at": None,
        "page": 1,
        "reviewed": False,
    }
    assert rows[1]["reviewed"] is True and rows[1]["reference_range"] is None


def test_another_patients_document_is_not_found() -> None:
    service = DocumentService(MagicMock())
    service._get_document_row = MagicMock(  # type: ignore[method-assign]
        side_effect=NotFoundError("Document", str(DOCUMENT))
    )
    with pytest.raises(NotFoundError):
        service.list_document_results(DOCUMENT, PATIENT)
