"""Contract tests shared by the worker and synthetic preflight."""

from __future__ import annotations

import json

import pytest

from app.services.care_plan_classification import (
    CarePlanClassificationError,
    prompt_for_facts,
    response_schema,
    validate_response,
)

FACTS = [
    {"id": "10000000-0000-4000-8000-000000000001", "fact_type": "medication"},
    {"id": "10000000-0000-4000-8000-000000000002", "fact_type": "obligation"},
]


def test_validator_accepts_exact_fact_mapping() -> None:
    categories = validate_response(
        json.dumps(
            {
                "items": [
                    {"source_fact_id": FACTS[0]["id"], "category": "medication"},
                    {"source_fact_id": FACTS[1]["id"], "category": "monitoring"},
                ]
            }
        ),
        FACTS,
    )

    assert categories == {FACTS[0]["id"]: "medication", FACTS[1]["id"]: "monitoring"}


def test_validator_reports_safe_selection_counts_without_ids() -> None:
    with pytest.raises(CarePlanClassificationError) as raised:
        validate_response(
            json.dumps({"items": [{"source_fact_id": FACTS[0]["id"], "category": "medication"}]}),
            FACTS,
        )

    assert raised.value.code == "fact_selection_mismatch"
    assert raised.value.diagnostics == {
        "expected_fact_count": 2,
        "returned_item_count": 1,
        "missing_fact_count": 1,
        "unknown_fact_count": 0,
        "duplicate_fact_count": 0,
    }
    assert FACTS[1]["id"] not in str(raised.value.diagnostics)


def test_validator_rejects_wrong_fact_type_category() -> None:
    with pytest.raises(CarePlanClassificationError, match="category_type_mismatch"):
        validate_response(
            json.dumps(
                {
                    "items": [
                        {"source_fact_id": FACTS[0]["id"], "category": "movement"},
                        {"source_fact_id": FACTS[1]["id"], "category": "monitoring"},
                    ]
                }
            ),
            FACTS,
        )


def test_repair_prompt_is_explicit_but_reuses_the_evidence_contract() -> None:
    prompt = prompt_for_facts(FACTS, repair=True)

    assert "final schema-repair attempt" in prompt
    assert FACTS[0]["id"] in prompt


def test_native_schema_uses_the_supported_inline_dialect() -> None:
    schema = response_schema()

    assert "$defs" not in schema
    assert schema["properties"]["items"]["items"]["required"] == [
        "source_fact_id",
        "category",
    ]
