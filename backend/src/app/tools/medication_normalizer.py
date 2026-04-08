"""Medication normalizer — parse dosage strings + RxNorm lookup."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, cast

from app.services.rxnorm_service import normalize_drug_name

logger = logging.getLogger(__name__)

DOSAGE_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|units?|iu|meq)",
    re.IGNORECASE,
)

FREQUENCY_MAP: dict[str, str] = {
    "once daily": "daily",
    "daily": "daily",
    "qd": "daily",
    "od": "daily",
    "twice daily": "twice_daily",
    "bid": "twice_daily",
    "b.i.d.": "twice_daily",
    "two times daily": "twice_daily",
    "three times daily": "three_times_daily",
    "tid": "three_times_daily",
    "t.i.d.": "three_times_daily",
    "four times daily": "four_times_daily",
    "qid": "four_times_daily",
    "every 4 hours": "every_4h",
    "q4h": "every_4h",
    "every 6 hours": "every_6h",
    "q6h": "every_6h",
    "every 8 hours": "every_8h",
    "q8h": "every_8h",
    "every 12 hours": "every_12h",
    "q12h": "every_12h",
    "as needed": "as_needed",
    "prn": "as_needed",
    "p.r.n.": "as_needed",
    "weekly": "weekly",
    "monthly": "monthly",
    "at bedtime": "at_bedtime",
    "qhs": "at_bedtime",
}

_RXNORM_SEMAPHORE: asyncio.Semaphore | None = None


def _get_rxnorm_semaphore() -> asyncio.Semaphore:
    global _RXNORM_SEMAPHORE
    if _RXNORM_SEMAPHORE is None:
        _RXNORM_SEMAPHORE = asyncio.Semaphore(3)
    return _RXNORM_SEMAPHORE


def parse_dosage(dosage_str: str) -> dict[str, Any]:
    """Parse dosage string like '500mg' into machine-readable parts."""
    match = DOSAGE_PATTERN.search(dosage_str or "")
    if not match:
        return {"value": None, "unit": None, "raw": dosage_str}

    return {
        "value": float(match.group(1)),
        "unit": match.group(2).lower(),
        "raw": dosage_str,
    }


def normalize_frequency(frequency_str: str) -> str:
    """Normalize frequency string to a machine-readable key."""
    value = (frequency_str or "").strip()
    return FREQUENCY_MAP.get(value.lower(), value)


async def normalize_medication(med: dict[str, Any]) -> dict[str, Any]:
    """Normalize a single medication from AI extraction."""
    name = str(med.get("name") or "").strip()
    dosage = str(med.get("dosage") or "").strip()
    frequency = str(med.get("frequency") or "").strip()

    normalized: dict[str, Any] = {
        **med,
        "name": name,
        "dosage": dosage,
        "frequency": frequency,
        "parsed_dosage": parse_dosage(dosage),
        "normalized_frequency": normalize_frequency(frequency),
        "generic_name": name,
        "rxcui": None,
    }

    if not name:
        return normalized

    try:
        async with _get_rxnorm_semaphore():
            response = await normalize_drug_name(name)
    except Exception as exc:
        logger.warning("RxNorm lookup failed for %s: %s", name, exc)
        return normalized

    normalized["generic_name"] = response.get("normalized_name") or name
    normalized["rxcui"] = response.get("rxcui")
    return normalized


async def normalize_all(medications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize a list of medications concurrently."""
    if not medications:
        return []

    results = await asyncio.gather(
        *(normalize_medication(med) for med in medications),
        return_exceptions=True,
    )

    normalized: list[dict[str, Any]] = []
    for original, result in zip(medications, results, strict=False):
        if isinstance(result, Exception):
            logger.warning("Medication normalization failed for %s: %s", original, result)
            fallback = {
                **original,
                "parsed_dosage": parse_dosage(str(original.get("dosage") or "")),
                "normalized_frequency": normalize_frequency(str(original.get("frequency") or "")),
                "generic_name": str(original.get("name") or ""),
                "rxcui": None,
            }
            normalized.append(fallback)
            continue
        normalized.append(cast(dict[str, Any], result))

    return normalized
