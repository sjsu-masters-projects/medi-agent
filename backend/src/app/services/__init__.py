"""Service layer for stateless HTTP API wrappers.

DailyMed and RxNorm are simple public APIs — no shared state, no connection pools.
For stateful operations (Supabase, Deepgram), use MCP servers in app.mcp.
"""

from app.services.dailymed_service import (
    get_drug_label,
    get_ndc_info,
    search_drug,
)
from app.services.rxnorm_service import (
    get_drug_properties,
    get_related_drugs,
    get_rxcui,
    normalize_drug_name,
)

__all__ = [
    "search_drug",
    "get_drug_label",
    "get_ndc_info",
    "get_rxcui",
    "get_drug_properties",
    "get_related_drugs",
    "normalize_drug_name",
]
