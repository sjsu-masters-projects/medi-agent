"""Drug reference lookups. Public terminology only — no patient data.

These tools read RxNorm, which is a public drug vocabulary. Nothing here is scoped to a
patient, and nothing here should ever be given patient data to look up: a drug name is
not a record, but "the warfarin Maria Gomez takes" would be.

`app/tools/medication_normalizer.py` also wraps RxNorm, for a different caller — it
normalises batches of already-extracted medication dicts during ingestion, behind a
semaphore. This is a single lookup made by a model mid-conversation, so it calls
`normalize_drug_name` directly rather than routing through that batch path.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.rxnorm_service import normalize_drug_name

logger = logging.getLogger(__name__)


async def lookup_rxnorm_ingredient(drug_name: str) -> dict[str, Any]:
    """Look up the generic ingredient and RxNorm identifier for a drug name.

    Use this to resolve a brand name to its ingredient before reasoning about whether two
    medications are the same drug. Returns the normalised ingredient name, the RxCUI, and
    known brand names.

    Args:
        drug_name: The medication name to resolve, brand or generic.
    """
    name = (drug_name or "").strip()
    if not name:
        # Returned rather than raised: a tool error ends the turn, whereas a result the
        # model can read lets it ask the patient which medication they meant.
        return {"error": "No drug name was provided."}

    result = await normalize_drug_name(name)

    if result.get("error"):
        logger.info("RxNorm lookup did not resolve a drug name")
        return {"drug_name": name, "error": str(result["error"])}

    return {
        "drug_name": result.get("original_name", name),
        "ingredient": result.get("normalized_name"),
        "rxcui": result.get("rxcui"),
        "brand_names": result.get("brand_names", []),
    }
