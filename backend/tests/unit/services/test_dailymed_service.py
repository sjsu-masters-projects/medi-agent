"""Tests for DailyMed service."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.dailymed_service import get_drug_label, get_ndc_info, search_drug


@pytest.mark.asyncio
async def test_search_drug_success():
    """Test successful drug search."""
    mock_response = {
        "metadata": {"total_elements": 25},
        "data": [
            {"drug_name": "Ibuprofen", "name_type": "G"},
            {"drug_name": "Advil", "name_type": "B"},
            {"drug_name": "Motrin", "name_type": "B"},
        ],
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await search_drug("ibuprofen")

        assert "error" not in result
        assert result["query"] == "ibuprofen"
        assert result["total_results"] == 25
        assert len(result["drugs"]) == 3
        assert result["drugs"][0]["name"] == "Ibuprofen"
        assert result["drugs"][0]["type"] == "Generic"
        assert result["drugs"][1]["type"] == "Brand"


@pytest.mark.asyncio
async def test_search_drug_not_found():
    """Test drug search with no results."""
    mock_response = {"metadata": {"total_elements": 0}, "data": []}

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await search_drug("nonexistentdrugxyz123")

        assert result["query"] == "nonexistentdrugxyz123"
        assert result["total_results"] == 0
        assert result["drugs"] == []
        # Empty results don't produce an error, just empty list


@pytest.mark.asyncio
async def test_search_drug_timeout():
    """Test drug search timeout."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = httpx.TimeoutException("Request timed out")

        result = await search_drug("ibuprofen")

        assert "error" in result
        assert result["error"] == "Request timed out"
        assert result["query"] == "ibuprofen"


@pytest.mark.asyncio
async def test_search_drug_http_error():
    """Test drug search HTTP error."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = AsyncMock(status_code=500)

        def raise_for_status():
            raise httpx.HTTPStatusError("Server error", request=AsyncMock(), response=mock_response)

        mock_response.raise_for_status = raise_for_status
        mock_get.return_value = mock_response

        result = await search_drug("ibuprofen")

        assert "error" in result
        assert "API error: 500" in result["error"]


@pytest.mark.asyncio
async def test_get_drug_label_success():
    """Test successful drug label retrieval."""
    mock_response = {
        "data": [
            {
                "title": "Ibuprofen Tablet",
                "generic_medicine_name": "Ibuprofen",
                "brand_name": "Advil",
                "labeler": "Pfizer",
                "warnings": "May cause stomach bleeding",
                "adverse_reactions": "Nausea, headache",
                "indications_and_usage": "Pain relief",
                "dosage_and_administration": "200mg every 4-6 hours",
            }
        ]
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await get_drug_label("test-setid-123")

        assert "error" not in result
        assert result["setid"] == "test-setid-123"
        assert result["title"] == "Ibuprofen Tablet"
        assert result["generic_name"] == "Ibuprofen"
        assert result["brand_name"] == "Advil"
        assert result["manufacturer"] == "Pfizer"


@pytest.mark.asyncio
async def test_get_drug_label_invalid_setid():
    """Test get drug label with invalid setid."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = AsyncMock(status_code=404)

        def raise_for_status():
            raise httpx.HTTPStatusError("Not found", request=AsyncMock(), response=mock_response)

        mock_response.raise_for_status = raise_for_status
        mock_get.return_value = mock_response

        result = await get_drug_label("invalid-setid-12345")

        assert "error" in result
        assert result["setid"] == "invalid-setid-12345"
        assert result["error"] == "Drug label not found"


@pytest.mark.asyncio
async def test_get_ndc_info_success():
    """Test successful NDC lookup."""
    mock_response = {
        "data": [
            {
                "ndc": "0002-1433-01",
                "product_name": "Advil Tablets",
                "generic_name": "Ibuprofen",
                "labeler_name": "Pfizer",
                "package_description": "100 tablets",
                "setid": "test-setid-123",
            }
        ]
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await get_ndc_info("0002-1433-01")

        assert "error" not in result
        assert result["ndc"] == "0002-1433-01"
        assert result["product_name"] == "Advil Tablets"
        assert result["generic_name"] == "Ibuprofen"


@pytest.mark.asyncio
async def test_get_ndc_info_not_found():
    """Test NDC lookup with invalid code."""
    mock_response = {"data": []}

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await get_ndc_info("99999-9999-99")

        assert "error" in result
        assert result["ndc"] == "99999-9999-99"
        assert result["error"] == "NDC not found"


@pytest.mark.asyncio
async def test_search_drug_response_format():
    """Test that search_drug returns correct format."""
    mock_response = {
        "metadata": {"total_elements": 10},
        "data": [
            {"drug_name": "Aspirin", "name_type": "G"},
            {"drug_name": "Bayer Aspirin", "name_type": "B"},
        ],
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await search_drug("aspirin")

        assert "query" in result
        assert "total_results" in result
        assert "drugs" in result
        assert isinstance(result["drugs"], list)

        assert len(result["drugs"]) == 2
        drug = result["drugs"][0]
        assert "name" in drug
        assert "type" in drug
        assert drug["type"] in ["Brand", "Generic"]


@pytest.mark.asyncio
async def test_search_drug_empty_data():
    """Test search_drug with empty data field."""
    mock_response = {"metadata": {"total_elements": 0}}  # Missing 'data' field

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await search_drug("nonexistent")

        assert result["query"] == "nonexistent"
        assert result["total_results"] == 0
        assert result["drugs"] == []
        assert "error" in result
        assert result["error"] == "No results found"


@pytest.mark.asyncio
async def test_search_drug_duplicate_names():
    """Test search_drug filters duplicate drug names."""
    mock_response = {
        "metadata": {"total_elements": 5},
        "data": [
            {"drug_name": "Ibuprofen", "name_type": "G"},
            {"drug_name": "Ibuprofen", "name_type": "G"},  # Duplicate
            {"drug_name": "Advil", "name_type": "B"},
            {"drug_name": "Advil", "name_type": "B"},  # Duplicate
            {"drug_name": "Motrin", "name_type": "B"},
        ],
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await search_drug("ibuprofen")

        # Should only have 3 unique drugs
        assert len(result["drugs"]) == 3
        drug_names = [d["name"] for d in result["drugs"]]
        assert drug_names == ["Ibuprofen", "Advil", "Motrin"]


@pytest.mark.asyncio
async def test_search_drug_limit_to_10():
    """Test search_drug limits results to 10 drugs."""
    # Create 15 unique drugs
    mock_data = [{"drug_name": f"Drug{i}", "name_type": "G"} for i in range(15)]
    mock_response = {"metadata": {"total_elements": 15}, "data": mock_data}

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await search_drug("drug")

        # Should limit to 10
        assert len(result["drugs"]) == 10
        assert result["total_results"] == 15


@pytest.mark.asyncio
async def test_search_drug_missing_drug_name():
    """Test search_drug handles items with missing drug_name."""
    mock_response = {
        "metadata": {"total_elements": 3},
        "data": [
            {"drug_name": "Aspirin", "name_type": "G"},
            {"name_type": "B"},  # Missing drug_name
            {"drug_name": None, "name_type": "G"},  # None drug_name
            {"drug_name": "Advil", "name_type": "B"},
        ],
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await search_drug("aspirin")

        # Should only include drugs with valid names
        assert len(result["drugs"]) == 2
        assert result["drugs"][0]["name"] == "Aspirin"
        assert result["drugs"][1]["name"] == "Advil"


@pytest.mark.asyncio
async def test_search_drug_unexpected_error():
    """Test search_drug handles unexpected errors."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = ValueError("Unexpected error")

        result = await search_drug("ibuprofen")

        assert "error" in result
        assert result["error"] == "Unexpected error occurred"
        assert result["query"] == "ibuprofen"


@pytest.mark.asyncio
async def test_get_drug_label_empty_data():
    """Test get_drug_label with empty data array."""
    mock_response = {"data": []}  # Empty array

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await get_drug_label("test-setid")

        assert "error" in result
        assert result["error"] == "Drug label not found"
        assert result["setid"] == "test-setid"


@pytest.mark.asyncio
async def test_get_drug_label_missing_data_field():
    """Test get_drug_label with missing data field."""
    mock_response = {}  # No 'data' field

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await get_drug_label("test-setid")

        assert "error" in result
        assert result["error"] == "Drug label not found"


@pytest.mark.asyncio
async def test_get_drug_label_timeout():
    """Test get_drug_label timeout."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = httpx.TimeoutException("Request timed out")

        result = await get_drug_label("test-setid")

        assert "error" in result
        assert result["error"] == "Request timed out"
        assert result["setid"] == "test-setid"


@pytest.mark.asyncio
async def test_get_drug_label_http_error_500():
    """Test get_drug_label with 500 error."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = AsyncMock(status_code=500)

        def raise_for_status():
            raise httpx.HTTPStatusError("Server error", request=AsyncMock(), response=mock_response)

        mock_response.raise_for_status = raise_for_status
        mock_get.return_value = mock_response

        result = await get_drug_label("test-setid")

        assert "error" in result
        assert "API error: 500" in result["error"]


@pytest.mark.asyncio
async def test_get_drug_label_unexpected_error():
    """Test get_drug_label handles unexpected errors."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = ValueError("Unexpected error")

        result = await get_drug_label("test-setid")

        assert "error" in result
        assert result["error"] == "Unexpected error occurred"


@pytest.mark.asyncio
async def test_get_ndc_info_fuzzy_match_no_exact():
    """Test get_ndc_info when fuzzy search returns results but no exact match."""
    mock_response = {
        "data": [
            {"ndc": "0002-1433-02", "product_name": "Similar Product"},  # Close but not exact
            {"ndc": "0002-1433-03", "product_name": "Another Similar"},
        ]
    }

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = AsyncMock(
            status_code=200, json=lambda: mock_response, raise_for_status=lambda: None
        )

        result = await get_ndc_info("0002-1433-01")

        assert "error" in result
        assert result["error"] == "NDC not found (no exact match)"
        assert result["ndc"] == "0002-1433-01"


@pytest.mark.asyncio
async def test_get_ndc_info_timeout():
    """Test get_ndc_info timeout."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = httpx.TimeoutException("Request timed out")

        result = await get_ndc_info("0002-1433-01")

        assert "error" in result
        assert result["error"] == "Request timed out"


@pytest.mark.asyncio
async def test_get_ndc_info_http_error():
    """Test get_ndc_info with HTTP error."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = AsyncMock(status_code=503)

        def raise_for_status():
            raise httpx.HTTPStatusError(
                "Service unavailable", request=AsyncMock(), response=mock_response
            )

        mock_response.raise_for_status = raise_for_status
        mock_get.return_value = mock_response

        result = await get_ndc_info("0002-1433-01")

        assert "error" in result
        assert "API error: 503" in result["error"]


@pytest.mark.asyncio
async def test_get_ndc_info_unexpected_error():
    """Test get_ndc_info handles unexpected errors."""
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = ValueError("Unexpected error")

        result = await get_ndc_info("0002-1433-01")

        assert "error" in result
        assert result["error"] == "Unexpected error occurred"
