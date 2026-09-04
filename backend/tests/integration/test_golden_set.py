"""Golden-set evaluation tests — load fixture documents, run through extraction, compare against expected output.

These tests verify that the ingestion pipeline's AI extraction + FHIR validation
produces results structurally matching hand-curated expected outputs. Because LLM
output is non-deterministic, assertions check *structure* and *key fields* rather
than exact string equality.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.agents.ingestion.graph import extract_content, validate_fhir
from app.tools.fhir_builder import validate_extracted_data

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
PATIENT_ID = UUID("00000000-0000-0000-0000-000000000123")
DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000999")


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def _load_expected(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


# ── Smoke: Fixtures actually exist ──────────────────────


class TestFixturesExist:
    """Verify all synthetic test documents and golden-set files exist."""

    @pytest.mark.parametrize(
        "fixture_name",
        [
            "discharge_summary.txt",
            "lab_report.txt",
            "prescription.txt",
            "diagnostic_report.txt",
            "discharge_summary_expected.json",
            "lab_report_expected.json",
            "prescription_expected.json",
            "diagnostic_report_expected.json",
        ],
    )
    def test_fixture_exists(self, fixture_name: str) -> None:
        path = FIXTURES / fixture_name
        assert path.exists(), f"Missing fixture: {path}"
        assert path.stat().st_size > 0, f"Empty fixture: {path}"


# ── Golden-set structure tests ──────────────────────────


class TestGoldenSetStructure:
    """Verify all expected JSON files have the required top-level keys."""

    @pytest.mark.parametrize(
        "expected_name",
        [
            "discharge_summary_expected.json",
            "lab_report_expected.json",
            "prescription_expected.json",
            "diagnostic_report_expected.json",
        ],
    )
    def test_expected_has_required_keys(self, expected_name: str) -> None:
        expected = _load_expected(expected_name)
        for key in ("medications", "conditions", "allergies", "follow_up_instructions"):
            assert key in expected, f"Missing key '{key}' in {expected_name}"
            assert isinstance(expected[key], list), f"'{key}' should be a list in {expected_name}"


# ── Golden-set content validation ───────────────────────


class TestDischargeGoldenSet:
    """Discharge summary should extract 5 meds, 4 conditions, 2 allergies, 6 follow-ups."""

    def test_expected_medication_count(self) -> None:
        expected = _load_expected("discharge_summary_expected.json")
        assert len(expected["medications"]) == 5

    def test_expected_condition_count(self) -> None:
        expected = _load_expected("discharge_summary_expected.json")
        assert len(expected["conditions"]) == 4

    def test_expected_allergy_count(self) -> None:
        expected = _load_expected("discharge_summary_expected.json")
        assert len(expected["allergies"]) == 2

    def test_expected_followup_count(self) -> None:
        expected = _load_expected("discharge_summary_expected.json")
        assert len(expected["follow_up_instructions"]) == 6

    def test_all_meds_have_names(self) -> None:
        expected = _load_expected("discharge_summary_expected.json")
        for med in expected["medications"]:
            assert med.get("name"), f"Medication missing name: {med}"

    def test_fhir_validation_on_expected_data(self) -> None:
        """Run expected data through FHIR validation — should produce zero errors."""
        expected = _load_expected("discharge_summary_expected.json")
        validated, errors = validate_extracted_data(expected, PATIENT_ID, DOCUMENT_ID)
        assert errors == [], f"FHIR validation errors: {errors}"
        assert len(validated["medications"]) == 5
        assert len(validated["conditions"]) == 4
        assert len(validated["allergies"]) == 2


class TestPrescriptionGoldenSet:
    """Prescription should extract 4 meds with different routes."""

    def test_expected_medication_count(self) -> None:
        expected = _load_expected("prescription_expected.json")
        assert len(expected["medications"]) == 4

    def test_subcutaneous_route_present(self) -> None:
        expected = _load_expected("prescription_expected.json")
        routes = {med.get("route") for med in expected["medications"]}
        assert "subcutaneous" in routes, f"Expected subcutaneous route, got: {routes}"

    def test_fhir_validation_on_expected_data(self) -> None:
        expected = _load_expected("prescription_expected.json")
        validated, errors = validate_extracted_data(expected, PATIENT_ID, DOCUMENT_ID)
        assert errors == [], f"FHIR validation errors: {errors}"
        assert len(validated["medications"]) == 4


class TestLabReportGoldenSet:
    """Lab report should extract conditions from abnormal results, no meds."""

    def test_no_medications(self) -> None:
        expected = _load_expected("lab_report_expected.json")
        assert len(expected["medications"]) == 0

    def test_conditions_from_abnormal_values(self) -> None:
        expected = _load_expected("lab_report_expected.json")
        assert len(expected["conditions"]) >= 3

    def test_fhir_validation_on_expected_data(self) -> None:
        expected = _load_expected("lab_report_expected.json")
        validated, errors = validate_extracted_data(expected, PATIENT_ID, DOCUMENT_ID)
        assert errors == [], f"FHIR validation errors: {errors}"


class TestDiagnosticGoldenSet:
    """Diagnostic report should extract meds from recommendations + conditions from findings."""

    def test_medications_from_recommendations(self) -> None:
        expected = _load_expected("diagnostic_report_expected.json")
        assert len(expected["medications"]) >= 2

    def test_conditions_from_findings(self) -> None:
        expected = _load_expected("diagnostic_report_expected.json")
        assert len(expected["conditions"]) >= 3

    def test_fhir_validation_on_expected_data(self) -> None:
        expected = _load_expected("diagnostic_report_expected.json")
        validated, errors = validate_extracted_data(expected, PATIENT_ID, DOCUMENT_ID)
        assert errors == [], f"FHIR validation errors: {errors}"


# ── Integration: extract_content with fixture text ──────


class TestExtractContentWithFixture:
    """Test extract_content node with real fixture text and mocked LLM returning golden-set output."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("fixture_txt", "fixture_json"),
        [
            ("discharge_summary.txt", "discharge_summary_expected.json"),
            ("lab_report.txt", "lab_report_expected.json"),
            ("prescription.txt", "prescription_expected.json"),
            ("diagnostic_report.txt", "diagnostic_report_expected.json"),
        ],
    )
    async def test_extract_with_golden_response(
        self, fixture_txt: str, fixture_json: str
    ) -> None:
        """Simulate LLM returning the golden-set JSON given fixture text."""
        raw_content = _load_fixture(fixture_txt)
        expected = _load_expected(fixture_json)

        with patch("app.agents.ingestion.graph.get_router") as mock_get_router:
            mock_router = MagicMock()
            mock_router.generate_text = AsyncMock(return_value=json.dumps(expected))
            mock_get_router.return_value = mock_router

            state = {
                "document_id": str(DOCUMENT_ID),
                "raw_content": raw_content,
            }
            result = await extract_content(state)

        assert result["error"] is None
        assert result["raw_content"] is None, "raw_content should be cleared after extraction"

        extracted = result["extracted_data"]
        assert len(extracted.get("medications", [])) == len(expected["medications"])
        assert len(extracted.get("conditions", [])) == len(expected["conditions"])


# ── Integration: full extract → validate pipeline ───────


class TestExtractThenValidate:
    """Test extract_content → validate_fhir with fixture data."""

    @pytest.mark.asyncio
    async def test_discharge_extract_then_validate(self) -> None:
        expected = _load_expected("discharge_summary_expected.json")

        with patch("app.agents.ingestion.graph.get_router") as mock_get_router:
            mock_router = MagicMock()
            mock_router.generate_text = AsyncMock(return_value=json.dumps(expected))
            mock_get_router.return_value = mock_router

            state = {
                "document_id": str(DOCUMENT_ID),
                "patient_id": str(PATIENT_ID),
                "raw_content": _load_fixture("discharge_summary.txt"),
            }
            state = await extract_content(state)

        with patch(
            "app.tools.fhir_builder.validate_extracted_data",
            wraps=validate_extracted_data,
        ):
            state = await validate_fhir(state)

        assert state["error"] is None
        assert state["validation_errors"] is None or state["validation_errors"] == []
        assert len(state["validated_data"]["medications"]) == 5
        assert len(state["validated_data"]["conditions"]) == 4
        assert len(state["validated_data"]["allergies"]) == 2
