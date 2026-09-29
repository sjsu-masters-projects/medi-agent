"""Contract for evidence-only care-plan categorization.

The worker and the synthetic preflight exercise this same prompt, native schema, and
semantic validation. A provider-shape regression is therefore found before a scheduled
job sees document-derived facts.
"""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from pydantic import ValidationError as PydanticValidationError

from app.adk.background_generation import generate_for_workload
from app.adk.registry import Workload
from app.models.care_plan import CarePlanCategory, CarePlanDraftProposal
from app.services.care_plan_prompts import CARE_PLAN_DRAFT_SYSTEM, CARE_PLAN_DRAFT_USER


class CarePlanClassificationError(ValueError):
    """Safe diagnostics for a response that cannot become a care-plan draft."""

    def __init__(self, code: str, diagnostics: dict[str, int | str]) -> None:
        super().__init__(code)
        self.code = code
        # Counts and categories only: never model text, fact values, or identifiers.
        self.diagnostics = diagnostics


def prompt_for_facts(facts: list[dict[str, Any]], *, repair: bool = False) -> str:
    """Build the fixed-evidence prompt without allowing the model to author care."""
    prompt_facts = [
        {
            "source_fact_id": str(fact["id"]),
            "fact_type": fact["fact_type"],
            "value": fact.get("value") or {},
            "confidence_score": fact.get("confidence_score"),
            "uncertainty": fact.get("uncertainty") or [],
        }
        for fact in facts
    ]
    prefix = (
        "This is a final schema-repair attempt. Return only the required JSON object; "
        "include every supplied source_fact_id exactly once.\n\n"
        if repair
        else ""
    )
    return prefix + CARE_PLAN_DRAFT_USER.format(facts_json=json.dumps(prompt_facts, sort_keys=True))


def response_schema() -> dict[str, Any]:
    """A small native schema for Vertex; Pydantic remains the final validator.

    The full generated schema contains ``$defs``, references, and array-size
    keywords. Vertex rejected that dialect during the synthetic preflight. The
    supported shape constrains the item fields while our validator enforces counts,
    UUIDs, and all fact/category relationships.
    """
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_fact_id": {"type": "string"},
                        "category": {
                            "type": "string",
                            "enum": [category.value for category in CarePlanCategory],
                        },
                    },
                    "required": ["source_fact_id", "category"],
                },
            }
        },
        "required": ["items"],
    }


async def classify_facts(
    facts: list[dict[str, Any]], *, record_telemetry: bool = True
) -> dict[str, str]:
    """Use the production route and validate at most two model responses."""
    schema = response_schema()
    for repair in (False, True):
        response = await generate_for_workload(
            Workload.CARE_PLAN_CLASSIFICATION,
            prompt=prompt_for_facts(facts, repair=repair),
            system_instruction=CARE_PLAN_DRAFT_SYSTEM,
            temperature=0,
            response_schema=schema,
            record_telemetry=record_telemetry,
        )
        try:
            return validate_response(response.text, facts)
        except CarePlanClassificationError as error:
            if repair:
                error.diagnostics["repair_attempted"] = 1
                raise
    raise AssertionError("Care-plan classification attempt loop ended without an outcome")


def validate_response(response_text: str, facts: list[dict[str, Any]]) -> dict[str, str]:
    """Validate schema and evidence-preserving semantics without retaining model text."""
    try:
        proposal = CarePlanDraftProposal.model_validate_json(response_text)
    except PydanticValidationError as error:
        errors = error.errors()
        error_types = {str(item.get("type") or "unknown") for item in errors}
        code = "json_invalid" if "json_invalid" in error_types else "schema_invalid"
        raise CarePlanClassificationError(
            code,
            {"validation_error_count": len(errors), "validation_kind": code},
        ) from None

    expected_ids = {str(fact["id"]) for fact in facts}
    selected_ids = [str(item.source_fact_id) for item in proposal.items]
    selected_set = set(selected_ids)
    duplicate_count = sum(count - 1 for count in Counter(selected_ids).values() if count > 1)
    missing_count = len(expected_ids - selected_set)
    unknown_count = len(selected_set - expected_ids)
    if missing_count or unknown_count or duplicate_count:
        raise CarePlanClassificationError(
            "fact_selection_mismatch",
            {
                "expected_fact_count": len(expected_ids),
                "returned_item_count": len(selected_ids),
                "missing_fact_count": missing_count,
                "unknown_fact_count": unknown_count,
                "duplicate_fact_count": duplicate_count,
            },
        )

    categories = {str(item.source_fact_id): item.category.value for item in proposal.items}
    medication_mismatch_count = sum(
        1
        for fact in facts
        if fact["fact_type"] == "medication"
        and categories[str(fact["id"])] != CarePlanCategory.MEDICATION.value
    )
    obligation_mismatch_count = sum(
        1
        for fact in facts
        if fact["fact_type"] == "obligation"
        and categories[str(fact["id"])] == CarePlanCategory.MEDICATION.value
    )
    if medication_mismatch_count or obligation_mismatch_count:
        raise CarePlanClassificationError(
            "category_type_mismatch",
            {
                "medication_category_mismatch_count": medication_mismatch_count,
                "obligation_category_mismatch_count": obligation_mismatch_count,
            },
        )
    return categories
