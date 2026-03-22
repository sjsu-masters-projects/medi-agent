"""Tests for RxNorm service."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.rxnorm_service import (
    get_drug_properties,
    get_related_drugs,
    get_rxcui,
    normalize_drug_name,
)


@pytest.mark.asyncio
async def test_get_rxcui_success():
    """Test successful RxCUI lookup."""
    mock_response = {"idGroup": {"rxnormId": ["5640", "198013"]}}

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await get_rxcui("ibuprofen")

        assert "error" not in result
        assert result["drug_name"] == "ibuprofen"
        assert result["rxcui"] == "5640"
        assert isinstance(result["all_rxcuis"], list)
        assert len(result["all_rxcuis"]) == 2


@pytest.mark.asyncio
async def test_get_rxcui_not_found():
    """Test RxCUI lookup with invalid drug."""
    mock_response = {"idGroup": {"rxnormId": []}}

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await get_rxcui("nonexistentdrugxyz123")

        assert "error" in result
        assert result["drug_name"] == "nonexistentdrugxyz123"
        assert result["rxcui"] is None


@pytest.mark.asyncio
async def test_get_rxcui_timeout():
    """Test RxCUI lookup timeout."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = httpx.TimeoutException("Request timed out")

        result = await get_rxcui("ibuprofen")

        assert "error" in result
        assert result["error"] == "Request timed out"


@pytest.mark.asyncio
async def test_get_drug_properties_success():
    """Test successful drug properties lookup."""
    mock_response = {
        "properties": {
            "name": "Ibuprofen",
            "synonym": "Ibuprofen",
            "tty": "IN",
            "language": "ENG",
            "suppress": "N",
            "umlscui": "C0020740",
        }
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await get_drug_properties("5640")

        assert "error" not in result
        assert result["rxcui"] == "5640"
        assert result["name"] == "Ibuprofen"
        assert result["tty"] == "IN"


@pytest.mark.asyncio
async def test_get_drug_properties_invalid():
    """Test drug properties with invalid RxCUI."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = AsyncMock(status_code=404)

        def raise_for_status():
            raise httpx.HTTPStatusError("Not found", request=AsyncMock(), response=mock_response)

        mock_response.raise_for_status = raise_for_status
        mock_get.return_value = mock_response

        result = await get_drug_properties("99999999")

        assert "error" in result
        assert result["rxcui"] == "99999999"


@pytest.mark.asyncio
async def test_get_related_drugs_success():
    """Test successful related drugs lookup."""
    mock_response = {
        "allRelatedGroup": {
            "conceptGroup": [
                {
                    "tty": "IN",
                    "conceptProperties": [{"rxcui": "5640", "name": "Ibuprofen"}],
                },
                {
                    "tty": "BN",
                    "conceptProperties": [
                        {"rxcui": "203368", "name": "Advil"},
                        {"rxcui": "203369", "name": "Motrin"},
                    ],
                },
                {
                    "tty": "SCD",
                    "conceptProperties": [
                        {"rxcui": "310965", "name": "Ibuprofen 200 MG Oral Tablet"}
                    ],
                },
                {
                    "tty": "SBD",
                    "conceptProperties": [{"rxcui": "310964", "name": "Advil 200 MG Oral Tablet"}],
                },
            ]
        }
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await get_related_drugs("5640")

        assert "error" not in result
        assert result["rxcui"] == "5640"
        assert "ingredients" in result
        assert "brand_names" in result
        assert "clinical_drugs" in result
        assert "branded_drugs" in result
        assert isinstance(result["brand_names"], list)
        assert len(result["brand_names"]) == 2


@pytest.mark.asyncio
async def test_normalize_drug_name_brand_to_generic():
    """Test normalizing brand name to generic."""
    # Mock get_rxcui
    mock_rxcui_response = {"idGroup": {"rxnormId": ["203368"]}}

    # Mock get_drug_properties
    mock_props_response = {
        "properties": {
            "name": "Advil",
            "tty": "BN",
            "synonym": "Advil",
            "language": "ENG",
            "suppress": "N",
            "umlscui": "C0593507",
        }
    }

    # Mock get_related_drugs
    mock_related_response = {
        "allRelatedGroup": {
            "conceptGroup": [
                {
                    "tty": "IN",
                    "conceptProperties": [{"rxcui": "5640", "name": "Ibuprofen"}],
                },
                {
                    "tty": "BN",
                    "conceptProperties": [{"rxcui": "203368", "name": "Advil"}],
                },
            ]
        }
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = [
            AsyncMock(
                status_code=200, json=lambda: mock_rxcui_response, raise_for_status=lambda: None
            ),
            AsyncMock(
                status_code=200, json=lambda: mock_props_response, raise_for_status=lambda: None
            ),
            AsyncMock(
                status_code=200, json=lambda: mock_related_response, raise_for_status=lambda: None
            ),
        ]

        result = await normalize_drug_name("Advil")

        assert "error" not in result
        assert result["original_name"] == "Advil"
        assert result["normalized_name"] == "Ibuprofen"
        assert result["rxcui"] == "203368"
        assert result["term_type"] == "BN"
        assert "brand_names" in result


@pytest.mark.asyncio
async def test_normalize_drug_name_generic():
    """Test normalizing generic name."""
    # Mock get_rxcui
    mock_rxcui_response = {"idGroup": {"rxnormId": ["5640"]}}

    # Mock get_drug_properties
    mock_props_response = {
        "properties": {
            "name": "Ibuprofen",
            "tty": "IN",
            "synonym": "Ibuprofen",
            "language": "ENG",
            "suppress": "N",
            "umlscui": "C0020740",
        }
    }

    # Mock get_related_drugs
    mock_related_response = {
        "allRelatedGroup": {
            "conceptGroup": [
                {
                    "tty": "IN",
                    "conceptProperties": [{"rxcui": "5640", "name": "Ibuprofen"}],
                }
            ]
        }
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = [
            AsyncMock(
                status_code=200, json=lambda: mock_rxcui_response, raise_for_status=lambda: None
            ),
            AsyncMock(
                status_code=200, json=lambda: mock_props_response, raise_for_status=lambda: None
            ),
            AsyncMock(
                status_code=200, json=lambda: mock_related_response, raise_for_status=lambda: None
            ),
        ]

        result = await normalize_drug_name("ibuprofen")

        assert "error" not in result
        assert result["original_name"] == "ibuprofen"
        assert result["normalized_name"] == "Ibuprofen"
        assert result["rxcui"] == "5640"


@pytest.mark.asyncio
async def test_normalize_drug_name_not_found():
    """Test normalizing invalid drug name."""
    mock_response = {"idGroup": {"rxnormId": []}}

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await normalize_drug_name("nonexistentdrugxyz123")

        assert "error" in result
        assert result["original_name"] == "nonexistentdrugxyz123"
        assert result["normalized_name"] is None


@pytest.mark.asyncio
async def test_response_formats():
    """Test that all functions return correct formats."""
    # Mock get_rxcui
    mock_rxcui_response = {"idGroup": {"rxnormId": ["2670"]}}

    # Mock get_drug_properties
    mock_props_response = {
        "properties": {
            "name": "Aspirin",
            "tty": "IN",
            "synonym": "Aspirin",
            "language": "ENG",
            "suppress": "N",
            "umlscui": "C0004057",
        }
    }

    # Mock get_related_drugs
    mock_related_response = {
        "allRelatedGroup": {
            "conceptGroup": [
                {
                    "tty": "IN",
                    "conceptProperties": [{"rxcui": "2670", "name": "Aspirin"}],
                }
            ]
        }
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = [
            AsyncMock(
                status_code=200, json=lambda: mock_rxcui_response, raise_for_status=lambda: None
            ),
            AsyncMock(
                status_code=200, json=lambda: mock_props_response, raise_for_status=lambda: None
            ),
            AsyncMock(
                status_code=200, json=lambda: mock_related_response, raise_for_status=lambda: None
            ),
        ]

        # Test get_rxcui format
        rxcui_result = await get_rxcui("aspirin")
        assert "drug_name" in rxcui_result
        assert "rxcui" in rxcui_result
        assert "all_rxcuis" in rxcui_result

        # Test get_drug_properties format
        props_result = await get_drug_properties(rxcui_result["rxcui"])
        assert "rxcui" in props_result
        assert "name" in props_result

        # Test get_related_drugs format
        related_result = await get_related_drugs(rxcui_result["rxcui"])
        assert "rxcui" in related_result
        assert "ingredients" in related_result
        assert "brand_names" in related_result


@pytest.mark.asyncio
async def test_get_rxcui_http_error():
    """Test get_rxcui with HTTP error."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = AsyncMock(status_code=500)

        def raise_for_status():
            raise httpx.HTTPStatusError("Server error", request=AsyncMock(), response=mock_response)

        mock_response.raise_for_status = raise_for_status
        mock_get.return_value = mock_response

        result = await get_rxcui("ibuprofen")

        assert "error" in result
        assert "API error: 500" in result["error"]


@pytest.mark.asyncio
async def test_get_rxcui_unexpected_error():
    """Test get_rxcui handles unexpected errors."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = ValueError("Unexpected error")

        result = await get_rxcui("ibuprofen")

        assert "error" in result
        assert result["error"] == "Unexpected error occurred"


@pytest.mark.asyncio
async def test_get_drug_properties_empty_properties():
    """Test get_drug_properties with empty properties."""
    mock_response = {"properties": {}}  # Empty properties

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await get_drug_properties("5640")

        assert "error" in result
        assert result["error"] == "Properties not found"


@pytest.mark.asyncio
async def test_get_drug_properties_missing_properties():
    """Test get_drug_properties with missing properties field."""
    mock_response = {}  # No 'properties' field

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await get_drug_properties("5640")

        assert "error" in result
        assert result["error"] == "Properties not found"


@pytest.mark.asyncio
async def test_get_drug_properties_timeout():
    """Test get_drug_properties timeout."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = httpx.TimeoutException("Request timed out")

        result = await get_drug_properties("5640")

        assert "error" in result
        assert result["error"] == "Request timed out"


@pytest.mark.asyncio
async def test_get_drug_properties_http_error_500():
    """Test get_drug_properties with 500 error."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = AsyncMock(status_code=500)

        def raise_for_status():
            raise httpx.HTTPStatusError("Server error", request=AsyncMock(), response=mock_response)

        mock_response.raise_for_status = raise_for_status
        mock_get.return_value = mock_response

        result = await get_drug_properties("5640")

        assert "error" in result
        assert "API error: 500" in result["error"]


@pytest.mark.asyncio
async def test_get_drug_properties_unexpected_error():
    """Test get_drug_properties handles unexpected errors."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = ValueError("Unexpected error")

        result = await get_drug_properties("5640")

        assert "error" in result
        assert result["error"] == "Unexpected error occurred"


@pytest.mark.asyncio
async def test_get_related_drugs_empty_concept_group():
    """Test get_related_drugs with empty conceptGroup."""
    mock_response = {"allRelatedGroup": {"conceptGroup": []}}

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await get_related_drugs("5640")

        assert "error" in result
        assert result["error"] == "No related drugs found"
        assert result["ingredients"] == []
        assert result["brand_names"] == []


@pytest.mark.asyncio
async def test_get_related_drugs_missing_concept_group():
    """Test get_related_drugs with missing conceptGroup."""
    mock_response = {"allRelatedGroup": {}}  # No conceptGroup

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await get_related_drugs("5640")

        assert "error" in result
        assert result["error"] == "No related drugs found"


@pytest.mark.asyncio
async def test_get_related_drugs_limit_to_5():
    """Test get_related_drugs limits each category to 5 items."""
    # Create 10 brand names
    brand_concepts = [{"rxcui": f"BN{i}", "name": f"Brand{i}"} for i in range(10)]

    mock_response = {
        "allRelatedGroup": {
            "conceptGroup": [
                {"tty": "BN", "conceptProperties": brand_concepts},
            ]
        }
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await get_related_drugs("5640")

        # Should limit to 5
        assert len(result["brand_names"]) == 5


@pytest.mark.asyncio
async def test_get_related_drugs_timeout():
    """Test get_related_drugs timeout."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = httpx.TimeoutException("Request timed out")

        result = await get_related_drugs("5640")

        assert "error" in result
        assert result["error"] == "Request timed out"


@pytest.mark.asyncio
async def test_get_related_drugs_http_error():
    """Test get_related_drugs with HTTP error."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = AsyncMock(status_code=503)

        def raise_for_status():
            raise httpx.HTTPStatusError(
                "Service unavailable", request=AsyncMock(), response=mock_response
            )

        mock_response.raise_for_status = raise_for_status
        mock_get.return_value = mock_response

        result = await get_related_drugs("5640")

        assert "error" in result
        assert "API error: 503" in result["error"]


@pytest.mark.asyncio
async def test_get_related_drugs_unexpected_error():
    """Test get_related_drugs handles unexpected errors."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = ValueError("Unexpected error")

        result = await get_related_drugs("5640")

        assert "error" in result
        assert result["error"] == "Unexpected error occurred"


@pytest.mark.asyncio
async def test_normalize_drug_name_rxcui_error():
    """Test normalize_drug_name when get_rxcui fails."""
    mock_response = {"idGroup": {"rxnormId": []}}

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await normalize_drug_name("nonexistent")

        assert "error" in result
        assert result["original_name"] == "nonexistent"
        assert result["normalized_name"] is None


@pytest.mark.asyncio
async def test_normalize_drug_name_properties_error():
    """Test normalize_drug_name when get_drug_properties fails."""
    # Mock successful get_rxcui
    mock_rxcui_response = {"idGroup": {"rxnormId": ["5640"]}}

    # Mock failed get_drug_properties (404)
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response_404 = AsyncMock(status_code=404)

        def raise_for_status():
            raise httpx.HTTPStatusError(
                "Not found", request=AsyncMock(), response=mock_response_404
            )

        mock_response_404.raise_for_status = raise_for_status

        mock_get.side_effect = [
            AsyncMock(
                status_code=200, json=lambda: mock_rxcui_response, raise_for_status=lambda: None
            ),
            mock_response_404,
        ]

        result = await normalize_drug_name("ibuprofen")

        assert "error" in result
        assert result["original_name"] == "ibuprofen"
        assert result["rxcui"] == "5640"


@pytest.mark.asyncio
async def test_normalize_drug_name_no_ingredients():
    """Test normalize_drug_name when no ingredients found."""
    # Mock get_rxcui
    mock_rxcui_response = {"idGroup": {"rxnormId": ["5640"]}}

    # Mock get_drug_properties
    mock_props_response = {
        "properties": {
            "name": "Ibuprofen",
            "tty": "IN",
            "synonym": "Ibuprofen",
            "language": "ENG",
            "suppress": "N",
            "umlscui": "C0020740",
        }
    }

    # Mock get_related_drugs with no ingredients
    mock_related_response = {
        "allRelatedGroup": {
            "conceptGroup": [
                {
                    "tty": "BN",
                    "conceptProperties": [{"rxcui": "203368", "name": "Advil"}],
                }
            ]
        }
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = [
            AsyncMock(
                status_code=200, json=lambda: mock_rxcui_response, raise_for_status=lambda: None
            ),
            AsyncMock(
                status_code=200, json=lambda: mock_props_response, raise_for_status=lambda: None
            ),
            AsyncMock(
                status_code=200, json=lambda: mock_related_response, raise_for_status=lambda: None
            ),
        ]

        result = await normalize_drug_name("ibuprofen")

        assert "error" not in result
        # Should fall back to props.name
        assert result["normalized_name"] == "Ibuprofen"


@pytest.mark.asyncio
async def test_normalize_drug_name_unexpected_error():
    """Test normalize_drug_name handles unexpected errors."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = ValueError("Unexpected error")

        result = await normalize_drug_name("ibuprofen")

        assert "error" in result
        assert result["error"] == "Unexpected error occurred"
