"""Unit tests for medication normalization helpers."""

from unittest.mock import AsyncMock, patch

import pytest

from app.tools.medication_normalizer import (
    normalize_frequency,
    normalize_medication,
    parse_dosage,
)


def test_parse_dosage_simple():
    parsed = parse_dosage("500mg")

    assert parsed["value"] == 500.0
    assert parsed["unit"] == "mg"


def test_parse_dosage_decimal():
    parsed = parse_dosage("2.5mg")

    assert parsed["value"] == 2.5
    assert parsed["unit"] == "mg"


def test_parse_dosage_compound():
    parsed = parse_dosage("10mg/5ml")

    assert parsed["value"] == 10.0
    assert parsed["unit"] == "mg"


def test_parse_dosage_invalid():
    parsed = parse_dosage("take with food")

    assert parsed["value"] is None
    assert parsed["unit"] is None


def test_normalize_frequency():
    assert normalize_frequency("twice daily") == "twice_daily"
    assert normalize_frequency("BID") == "twice_daily"
    assert normalize_frequency("unknown") == "unknown"


@pytest.mark.asyncio
async def test_normalize_medication_success():
    with patch(
        "app.tools.medication_normalizer.normalize_drug_name",
        new=AsyncMock(return_value={"normalized_name": "metformin", "rxcui": "860975"}),
    ):
        normalized = await normalize_medication(
            {
                "name": "Metformin",
                "dosage": "500mg",
                "frequency": "twice daily",
                "instructions": "Take with meals",
            }
        )

    assert normalized["generic_name"] == "metformin"
    assert normalized["rxcui"] == "860975"
    assert normalized["parsed_dosage"]["value"] == 500.0
    assert normalized["normalized_frequency"] == "twice_daily"


@pytest.mark.asyncio
async def test_normalize_medication_rxnorm_failure():
    with patch(
        "app.tools.medication_normalizer.normalize_drug_name",
        new=AsyncMock(side_effect=RuntimeError("rxnorm down")),
    ):
        normalized = await normalize_medication(
            {"name": "Aspirin", "dosage": "81mg", "frequency": "daily"}
        )

    assert normalized["generic_name"] == "Aspirin"
    assert normalized["rxcui"] is None
