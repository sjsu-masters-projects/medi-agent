"""Golden-set evaluation tests — load fixture documents, run through extraction, compare against expected output.

These tests exercise current extraction parsing and FHIR validation with mocked
generation over synthetic fixtures. They verify the complete golden structure,
not live model accuracy, PDF/OCR, item-level grounding or candidate persistence.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.services.ingestion_service import IngestionService
from app.tools.fhir_builder import validate_extracted_data

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
PATIENT_ID = UUID("00000000-0000-0000-0000-000000000123")
DOCUMENT_ID = UUID("00000000-0000-0000-0000-000000000999")


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def _load_expected(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


def _model_payload(expected: dict[str, Any], source: str) -> dict[str, Any]:
    """Adapt legacy gold keys to the current schema without changing clinical values.

    Verbatim source chunks meet the parser's evidence shape; these tests do not
    assert that every chunk grounds each item. Item anchoring has separate tests.
    """
    evidence = [
        {"page": 1, "excerpt": source[start : start + 1800], "confidence": 1.0}
        for start in range(0, len(source), 1800)
    ]
    payload = {
        key: [{**item, "evidence": evidence} for item in expected.get(key, [])]
        for key in ("medications", "conditions")
    }
    payload["allergies"] = [
        {**item, "allergen": item.get("allergen") or item["substance"], "evidence": evidence}
        for item in expected.get("allergies", [])
    ]
    payload["appointments"] = [
        {**item, "scheduled_for": item.get("timing"), "evidence": evidence}
        for item in expected.get("follow_up_instructions", [])
    ]
    return payload


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


# ── Current extraction parsing with fixture text ──────


class TestExtractContentWithFixture:
    """Exercise the ingestion service's model/parsing boundary for every golden document."""

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
    async def test_extract_with_golden_response(self, fixture_txt: str, fixture_json: str) -> None:
        """Simulate LLM returning the golden-set JSON given fixture text."""
        raw_content = _load_fixture(fixture_txt)
        expected = _load_expected(fixture_json)

        db = MagicMock()
        with patch("app.services.ingestion_service.get_router") as mock_get_router:
            mock_router = MagicMock()
            mock_router.generate_text_with_telemetry = AsyncMock(
                return_value=(
                    json.dumps(_model_payload(expected, raw_content)),
                    MagicMock(model="synthetic-extractor"),
                )
            )
            mock_get_router.return_value = mock_router

            result, model, invalid_items = await IngestionService(db)._extract_structured(
                raw_content
            )

        assert invalid_items == 0
        assert model == "synthetic-extractor"
        for key in ("medications", "conditions", "allergies"):
            assert len(getattr(result, key)) == len(expected[key])
        assert len(result.appointments) == len(expected["follow_up_instructions"])
        call = mock_router.generate_text_with_telemetry.await_args
        assert raw_content in call.kwargs["prompt"]
        assert call.kwargs["max_tokens"] == 8192
        db.table.assert_not_called()


# ── Integration: full extract → validate pipeline ───────


class TestExtractThenValidate:
    """Exercise current extraction followed by the FHIR validation owner."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "fixture_name", ["discharge_summary", "lab_report", "prescription", "diagnostic_report"]
    )
    async def test_extract_then_validate(self, fixture_name: str) -> None:
        expected = _load_expected(f"{fixture_name}_expected.json")
        source = _load_fixture(f"{fixture_name}.txt")

        with patch("app.services.ingestion_service.get_router") as mock_get_router:
            mock_router = MagicMock()
            mock_router.generate_text_with_telemetry = AsyncMock(
                return_value=(
                    json.dumps(_model_payload(expected, source)),
                    MagicMock(model="synthetic-extractor"),
                )
            )
            mock_get_router.return_value = mock_router

            result, _, invalid_items = await IngestionService(MagicMock())._extract_structured(
                source
            )

        assert invalid_items == 0
        fhir_input = result.model_dump()
        # The parser represents printed timing as scheduled_for; the FHIR utility
        # accepts timing. Keep this explicit fixture projection between the owners.
        fhir_input["appointments"] = [
            {**item.model_dump(), "timing": item.scheduled_for} for item in result.appointments
        ]
        validated, errors = validate_extracted_data(fhir_input, PATIENT_ID, DOCUMENT_ID)
        assert errors == []
        for key in ("medications", "conditions", "allergies"):
            assert len(validated[key]) == len(expected[key])
        assert len(validated["appointments"]) == len(expected["follow_up_instructions"])
        for actual, gold in zip(
            validated["appointments"], expected["follow_up_instructions"], strict=True
        ):
            assert actual["description"] == gold["description"]
            assert actual["timing"] == gold.get("timing")
            assert actual["provider"] == gold.get("provider")
