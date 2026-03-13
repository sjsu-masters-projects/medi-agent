"""Tests for RxNorm service."""

import pytest
from app.services.rxnorm_service import (
    get_rxcui,
    get_drug_properties,
    get_related_drugs,
    normalize_drug_name,
)


@pytest.mark.asyncio
async def test_get_rxcui_success():
    """Test successful RxCUI lookup."""
    result = await get_rxcui("ibuprofen")
    
    assert "error" not in result
    assert result["drug_name"] == "ibuprofen"
    assert result["rxcui"] is not None
    assert result["rxcui"] == "5640"  # Known RxCUI for ibuprofen
    assert isinstance(result["all_rxcuis"], list)


@pytest.mark.asyncio
async def test_get_rxcui_not_found():
    """Test RxCUI lookup with invalid drug."""
    result = await get_rxcui("nonexistentdrugxyz123")
    
    assert "error" in result
    assert result["drug_name"] == "nonexistentdrugxyz123"
    assert result["rxcui"] is None


@pytest.mark.asyncio
async def test_get_drug_properties_success():
    """Test successful drug properties lookup."""
    result = await get_drug_properties("5640")  # ibuprofen
    
    assert "error" not in result
    assert result["rxcui"] == "5640"
    assert result["name"] is not None
    assert "tty" in result


@pytest.mark.asyncio
async def test_get_drug_properties_invalid():
    """Test drug properties with invalid RxCUI."""
    result = await get_drug_properties("99999999")
    
    assert "error" in result
    assert result["rxcui"] == "99999999"


@pytest.mark.asyncio
async def test_get_related_drugs_success():
    """Test successful related drugs lookup."""
    result = await get_related_drugs("5640")  # ibuprofen
    
    assert "error" not in result
    assert result["rxcui"] == "5640"
    assert "ingredients" in result
    assert "brand_names" in result
    assert "clinical_drugs" in result
    assert "branded_drugs" in result
    assert isinstance(result["brand_names"], list)


@pytest.mark.asyncio
async def test_normalize_drug_name_brand_to_generic():
    """Test normalizing brand name to generic."""
    result = await normalize_drug_name("Advil")
    
    assert "error" not in result
    assert result["original_name"] == "Advil"
    assert result["normalized_name"] is not None
    assert result["rxcui"] is not None
    assert "term_type" in result
    assert "brand_names" in result


@pytest.mark.asyncio
async def test_normalize_drug_name_generic():
    """Test normalizing generic name."""
    result = await normalize_drug_name("ibuprofen")
    
    assert "error" not in result
    assert result["original_name"] == "ibuprofen"
    assert result["normalized_name"] is not None
    assert result["rxcui"] == "5640"


@pytest.mark.asyncio
async def test_normalize_drug_name_not_found():
    """Test normalizing invalid drug name."""
    result = await normalize_drug_name("nonexistentdrugxyz123")
    
    assert "error" in result
    assert result["original_name"] == "nonexistentdrugxyz123"
    assert result["normalized_name"] is None


@pytest.mark.asyncio
async def test_response_formats():
    """Test that all functions return correct formats."""
    # Test get_rxcui format
    rxcui_result = await get_rxcui("aspirin")
    assert "drug_name" in rxcui_result
    assert "rxcui" in rxcui_result
    assert "all_rxcuis" in rxcui_result
    
    # Test get_drug_properties format
    if rxcui_result.get("rxcui"):
        props_result = await get_drug_properties(rxcui_result["rxcui"])
        assert "rxcui" in props_result
        assert "name" in props_result
        
        # Test get_related_drugs format
        related_result = await get_related_drugs(rxcui_result["rxcui"])
        assert "rxcui" in related_result
        assert "ingredients" in related_result
        assert "brand_names" in related_result
