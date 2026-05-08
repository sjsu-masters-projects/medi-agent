"""DailyMed service - FDA drug labels and ADR profiles.

Provides functions to query drug information, labels, and adverse reactions.
"""

from typing import Any
from xml.etree import ElementTree

import httpx
import structlog

logger = structlog.get_logger(__name__)

BASE_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v2"


async def search_drug(drug_name: str) -> dict[str, Any]:
    """Search for drugs by name.

    Args:
        drug_name: Drug name to search for

    Returns:
        dict with query, total_results, drugs list, and error if failed
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{BASE_URL}/drugnames.json", params={"drug_name": drug_name}, timeout=10.0
            )
            response.raise_for_status()
            data = response.json()

            if not data or "data" not in data:
                logger.warning("dailymed_empty_response", drug_name=drug_name)
                return {
                    "query": drug_name,
                    "total_results": 0,
                    "drugs": [],
                    "error": "No results found",
                }

            # Extract unique drugs (limit to 10)
            drugs = []
            seen = set()
            for item in data.get("data", [])[:20]:
                name = item.get("drug_name")
                if name and name not in seen:
                    drugs.append(
                        {
                            "name": name,
                            "type": "Brand" if item.get("name_type") == "B" else "Generic",
                        }
                    )
                    seen.add(name)
                if len(drugs) >= 10:
                    break

            logger.info("dailymed_search_success", drug_name=drug_name, results=len(drugs))

            return {
                "query": drug_name,
                "total_results": data.get("metadata", {}).get("total_elements", 0),
                "drugs": drugs,
            }

    except httpx.TimeoutException:
        logger.error("dailymed_timeout", drug_name=drug_name)
        return {"query": drug_name, "total_results": 0, "drugs": [], "error": "Request timed out"}
    except httpx.HTTPStatusError as e:
        logger.error("dailymed_http_error", drug_name=drug_name, status=e.response.status_code)
        return {
            "query": drug_name,
            "total_results": 0,
            "drugs": [],
            "error": f"API error: {e.response.status_code}",
        }
    except Exception as e:
        logger.error("dailymed_unexpected_error", drug_name=drug_name, error=str(e))
        return {
            "query": drug_name,
            "total_results": 0,
            "drugs": [],
            "error": "Unexpected error occurred",
        }


async def get_drug_label(setid: str) -> dict[str, Any]:
    """Get drug label by Set ID.

    Args:
        setid: DailyMed Set ID

    Returns:
        dict with label details (warnings, ADRs, dosage, etc) and error if failed
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/spls/{setid}.xml", timeout=10.0)
            response.raise_for_status()
            spl_data = _parse_label_response(response, setid)
            if spl_data.get("error"):
                return spl_data

            logger.info("dailymed_label_success", setid=setid)

            return spl_data

    except httpx.TimeoutException:
        logger.error("dailymed_label_timeout", setid=setid)
        return {"setid": setid, "error": "Request timed out"}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            logger.warning("dailymed_label_404", setid=setid)
            return {"setid": setid, "error": "Drug label not found"}
        logger.error("dailymed_label_http_error", setid=setid, status=e.response.status_code)
        return {"setid": setid, "error": f"API error: {e.response.status_code}"}
    except Exception as e:
        logger.error("dailymed_label_unexpected_error", setid=setid, error=str(e))
        return {"setid": setid, "error": "Unexpected error occurred"}


def _parse_label_response(response: httpx.Response, setid: str) -> dict[str, Any]:
    xml_text = _response_xml_text(response)
    if xml_text:
        return _parse_spl_xml_label(setid, xml_text)

    # Compatibility path for tests and any internal callers still using the old JSON shape.
    data = response.json()
    if not data or "data" not in data or not data["data"]:
        logger.warning("dailymed_label_not_found", setid=setid)
        return {"setid": setid, "error": "Drug label not found"}
    spl_data = data["data"][0]
    return {
        "setid": setid,
        "title": spl_data.get("title"),
        "generic_name": spl_data.get("generic_medicine_name"),
        "brand_name": spl_data.get("brand_name"),
        "manufacturer": spl_data.get("labeler"),
        "warnings": spl_data.get("warnings"),
        "adverse_reactions": spl_data.get("adverse_reactions"),
        "indications": spl_data.get("indications_and_usage"),
        "dosage": spl_data.get("dosage_and_administration"),
    }


def _response_xml_text(response: httpx.Response) -> str | None:
    if not isinstance(response, httpx.Response):
        return None

    content = getattr(response, "content", b"")
    if isinstance(content, bytes) and content.lstrip().startswith(b"<"):
        return content.decode(response.encoding or "utf-8", errors="replace")

    text = getattr(response, "text", "")
    if isinstance(text, str) and text.lstrip().startswith("<"):
        return text
    return None


def _parse_spl_xml_label(setid: str, xml_text: str) -> dict[str, Any]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        logger.warning("dailymed_label_invalid_xml", setid=setid)
        return {"setid": setid, "error": "Drug label not found"}

    ns = {"hl7": "urn:hl7-org:v3"}
    title = _xml_text(root.find("./hl7:title", ns))
    sections = _extract_label_sections(root, ns)
    if not title and not sections:
        logger.warning("dailymed_label_not_found", setid=setid)
        return {"setid": setid, "error": "Drug label not found"}

    return {
        "setid": setid,
        "title": title,
        "generic_name": None,
        "brand_name": None,
        "manufacturer": None,
        "warnings": sections.get("warnings"),
        "adverse_reactions": sections.get("adverse_reactions"),
        "indications": sections.get("indications"),
        "dosage": sections.get("dosage"),
    }


def _extract_label_sections(root: ElementTree.Element, ns: dict[str, str]) -> dict[str, str | None]:
    section_aliases = {
        "warnings": ("warnings", "boxed warning", "warnings and precautions"),
        "adverse_reactions": ("adverse reactions",),
        "indications": ("indications and usage",),
        "dosage": ("dosage and administration",),
    }
    sections: dict[str, str | None] = {
        "warnings": None,
        "adverse_reactions": None,
        "indications": None,
        "dosage": None,
    }
    for section in root.findall(".//hl7:section", ns):
        section_title = _xml_text(section.find("hl7:title", ns)).lower()
        text_node = section.find("hl7:text", ns)
        section_text = _xml_text(text_node)
        if not section_title or not section_text:
            continue
        for key, aliases in section_aliases.items():
            if sections[key] is None and any(alias in section_title for alias in aliases):
                sections[key] = section_text
                break
    return sections


def _xml_text(element: ElementTree.Element | None) -> str:
    if element is None:
        return ""
    return " ".join(" ".join(element.itertext()).split())


async def get_ndc_info(ndc: str) -> dict[str, Any]:
    """Get drug info by National Drug Code (NDC).

    Args:
        ndc: National Drug Code (e.g., '0002-1433-01')

    Returns:
        dict with NDC details and error if failed
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/ndcs.json", params={"ndc": ndc}, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            if not data or "data" not in data or not data["data"]:
                logger.warning("dailymed_ndc_not_found", ndc=ndc)
                return {"ndc": ndc, "error": "NDC not found"}

            # DailyMed does fuzzy search, verify exact match
            ndc_data = None
            for item in data["data"]:
                if item.get("ndc") == ndc:
                    ndc_data = item
                    break

            if not ndc_data:
                logger.warning(
                    "dailymed_ndc_no_exact_match", ndc=ndc, total_results=len(data["data"])
                )
                return {"ndc": ndc, "error": "NDC not found (no exact match)"}

            logger.info("dailymed_ndc_success", ndc=ndc)

            return {
                "ndc": ndc,
                "product_name": ndc_data.get("product_name"),
                "generic_name": ndc_data.get("generic_name"),
                "labeler_name": ndc_data.get("labeler_name"),
                "package_description": ndc_data.get("package_description"),
                "setid": ndc_data.get("setid"),
            }

    except httpx.TimeoutException:
        logger.error("dailymed_ndc_timeout", ndc=ndc)
        return {"ndc": ndc, "error": "Request timed out"}
    except httpx.HTTPStatusError as e:
        logger.error("dailymed_ndc_http_error", ndc=ndc, status=e.response.status_code)
        return {"ndc": ndc, "error": f"API error: {e.response.status_code}"}
    except Exception as e:
        logger.error("dailymed_ndc_unexpected_error", ndc=ndc, error=str(e))
        return {"ndc": ndc, "error": "Unexpected error occurred"}
