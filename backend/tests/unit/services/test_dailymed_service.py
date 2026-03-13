"""Tests for DailyMed service."""

import pytest
from app.services.dailymed_service import search_drug, get_drug_label, get_ndc_info


@pytest.mark.asyncio
async def test_search_drug_success():
    """Test successful drug search."""
    result = await search_drug("ibuprofen")
    
    assert "error" not in result
    assert result["query"] == "ibuprofen"
    assert result["total_results"] > 0
    assert len(result["drugs"]) > 0
    assert "name" in result["drugs"][0]
    assert "type" in result["drugs"][0]


@pytest.mark.asyncio
async def test_search_drug_not_found():
    """Test drug search with no results."""
    result = await search_drug("nonexistentdrugxyz123")
    
    # May return error or empty results
    assert result["query"] == "nonexistentdrugxyz123"
    assert result["total_results"] == 0 or "error" in result


@pytest.mark.asyncio
async def test_get_drug_label_invalid_setid():
    """Test get drug label with invalid setid."""
    result = await get_drug_label("invalid-setid-12345")
    
    assert "error" in result
    assert result["setid"] == "invalid-setid-12345"


@pytest.mark.asyncio
async def test_get_ndc_info_not_found():
    """Test NDC lookup with invalid code."""
    result = await get_ndc_info("99999-9999-99")
    
    assert "error" in result
    assert result["ndc"] == "99999-9999-99"


@pytest.mark.asyncio
async def test_search_drug_response_format():
    """Test that search_drug returns correct format."""
    result = await search_drug("aspirin")
    
    assert "query" in result
    assert "total_results" in result
    assert "drugs" in result
    assert isinstance(result["drugs"], list)
    
    if result["drugs"]:
        drug = result["drugs"][0]
        assert "name" in drug
        assert "type" in drug
        assert drug["type"] in ["Brand", "Generic"]
