"""RxNorm service - Drug normalization and standardization.

Provides functions to normalize drug names and get RxCUI codes.
"""

from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

BASE_URL = "https://rxnav.nlm.nih.gov/REST"


async def get_rxcui(drug_name: str) -> dict[str, Any]:
    """Get RxCUI for drug name.

    Args:
        drug_name: Drug name to look up

    Returns:
        dict with drug_name, rxcui, all_rxcuis, and error if failed
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}/rxcui.json", params={"name": drug_name}, timeout=10.0
            )
            response.raise_for_status()
            data = response.json()

            rxcui_list = data.get("idGroup", {}).get("rxnormId", [])

            if not rxcui_list:
                logger.warning("rxnorm_no_rxcui", drug_name=drug_name)
                return {
                    "drug_name": drug_name,
                    "rxcui": None,
                    "all_rxcuis": [],
                    "error": "Drug not found in RxNorm",
                }

            logger.info("rxnorm_rxcui_success", drug_name=drug_name, rxcui=rxcui_list[0])

            return {"drug_name": drug_name, "rxcui": rxcui_list[0], "all_rxcuis": rxcui_list}

    except httpx.TimeoutException:
        logger.error("rxnorm_timeout", drug_name=drug_name)
        return {
            "drug_name": drug_name,
            "rxcui": None,
            "all_rxcuis": [],
            "error": "Request timed out",
        }
    except httpx.HTTPStatusError as e:
        logger.error("rxnorm_http_error", drug_name=drug_name, status=e.response.status_code)
        return {
            "drug_name": drug_name,
            "rxcui": None,
            "all_rxcuis": [],
            "error": f"API error: {e.response.status_code}",
        }
    except Exception as e:
        logger.error("rxnorm_unexpected_error", drug_name=drug_name, error=str(e))
        return {
            "drug_name": drug_name,
            "rxcui": None,
            "all_rxcuis": [],
            "error": "Unexpected error occurred",
        }


async def get_drug_properties(rxcui: str) -> dict[str, Any]:
    """Get drug properties by RxCUI.

    Args:
        rxcui: RxCUI code

    Returns:
        dict with properties (name, type, synonym) and error if failed
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/rxcui/{rxcui}/properties.json", timeout=10.0)
            response.raise_for_status()
            data = response.json()

            props = data.get("properties", {})

            if not props:
                logger.warning("rxnorm_props_not_found", rxcui=rxcui)
                return {"rxcui": rxcui, "error": "Properties not found"}

            logger.info("rxnorm_props_success", rxcui=rxcui)

            return {
                "rxcui": rxcui,
                "name": props.get("name"),
                "synonym": props.get("synonym"),
                "tty": props.get("tty"),
                "language": props.get("language"),
                "suppress": props.get("suppress"),
                "umlscui": props.get("umlscui"),
            }

    except httpx.TimeoutException:
        logger.error("rxnorm_props_timeout", rxcui=rxcui)
        return {"rxcui": rxcui, "error": "Request timed out"}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning("rxnorm_props_404", rxcui=rxcui)
            return {"rxcui": rxcui, "error": "RxCUI not found"}
        logger.error("rxnorm_props_http_error", rxcui=rxcui, status=e.response.status_code)
        return {"rxcui": rxcui, "error": f"API error: {e.response.status_code}"}
    except Exception as e:
        logger.error("rxnorm_props_unexpected_error", rxcui=rxcui, error=str(e))
        return {"rxcui": rxcui, "error": "Unexpected error occurred"}


async def get_related_drugs(rxcui: str) -> dict[str, Any]:
    """Get related drugs for RxCUI.

    Args:
        rxcui: RxCUI code

    Returns:
        dict with ingredients, brand_names, clinical_drugs, branded_drugs, and error if failed
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/rxcui/{rxcui}/allrelated.json", timeout=10.0)
            response.raise_for_status()
            data = response.json()

            related_group = data.get("allRelatedGroup", {}).get("conceptGroup", [])

            if not related_group:
                logger.warning("rxnorm_related_not_found", rxcui=rxcui)
                return {
                    "rxcui": rxcui,
                    "ingredients": [],
                    "brand_names": [],
                    "clinical_drugs": [],
                    "branded_drugs": [],
                    "error": "No related drugs found",
                }

            related = {}
            for group in related_group:
                tty = group.get("tty")
                concepts = group.get("conceptProperties", [])
                if concepts:
                    related[tty] = [
                        {"rxcui": c.get("rxcui"), "name": c.get("name")} for c in concepts[:5]
                    ]

            logger.info("rxnorm_related_success", rxcui=rxcui)

            return {
                "rxcui": rxcui,
                "ingredients": related.get("IN", []),
                "brand_names": related.get("BN", []),
                "clinical_drugs": related.get("SCD", []),
                "branded_drugs": related.get("SBD", []),
            }

    except httpx.TimeoutException:
        logger.error("rxnorm_related_timeout", rxcui=rxcui)
        return {
            "rxcui": rxcui,
            "ingredients": [],
            "brand_names": [],
            "clinical_drugs": [],
            "branded_drugs": [],
            "error": "Request timed out",
        }
    except httpx.HTTPStatusError as e:
        logger.error("rxnorm_related_http_error", rxcui=rxcui, status=e.response.status_code)
        return {
            "rxcui": rxcui,
            "ingredients": [],
            "brand_names": [],
            "clinical_drugs": [],
            "branded_drugs": [],
            "error": f"API error: {e.response.status_code}",
        }
    except Exception as e:
        logger.error("rxnorm_related_unexpected_error", rxcui=rxcui, error=str(e))
        return {
            "rxcui": rxcui,
            "ingredients": [],
            "brand_names": [],
            "clinical_drugs": [],
            "branded_drugs": [],
            "error": "Unexpected error occurred",
        }


async def normalize_drug_name(drug_name: str) -> dict[str, Any]:
    """Normalize drug name (brand → generic).

    Args:
        drug_name: Brand or generic drug name

    Returns:
        dict with original_name, normalized_name, rxcui, term_type, brand_names, and error if failed
    """
    try:
        # Get RxCUI
        rxcui_data = await get_rxcui(drug_name)

        if "error" in rxcui_data:
            return {
                "original_name": drug_name,
                "normalized_name": None,
                "error": rxcui_data["error"],
            }

        rxcui = rxcui_data.get("rxcui")
        if not rxcui:
            return {
                "original_name": drug_name,
                "normalized_name": None,
                "error": "Drug not found in RxNorm",
            }

        # Get properties
        props = await get_drug_properties(rxcui)

        if "error" in props:
            return {
                "original_name": drug_name,
                "normalized_name": None,
                "rxcui": rxcui,
                "error": props["error"],
            }

        # Get related drugs
        related = await get_related_drugs(rxcui)

        # Extract generic name (ingredient)
        generic_name = None
        if related.get("ingredients"):
            generic_name = related["ingredients"][0]["name"]

        logger.info(
            "rxnorm_normalize_success",
            original=drug_name,
            normalized=generic_name or props.get("name"),
        )

        return {
            "original_name": drug_name,
            "normalized_name": generic_name or props.get("name"),
            "rxcui": rxcui,
            "term_type": props.get("tty"),
            "brand_names": [b["name"] for b in related.get("brand_names", [])[:3]],
        }

    except Exception as e:
        logger.error("rxnorm_normalize_unexpected_error", drug_name=drug_name, error=str(e))
        return {
            "original_name": drug_name,
            "normalized_name": None,
            "error": "Unexpected error occurred",
        }
