"""Run the deployed care-plan classifier contract against synthetic evidence only.

Use before deploying a change to the care-plan model route. It invokes the exact
registry workload and validator used by the Cloud Run worker, but never reads a
database or sends document content.

    PYTHONPATH=src .venv/bin/python scripts/preflight_care_plan_classification.py
    PYTHONPATH=src .venv/bin/python scripts/preflight_care_plan_classification.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any
from uuid import UUID

from app.models.generation import GenerationProviderError
from app.services.care_plan_classification import (
    CarePlanClassificationError,
    classify_facts,
    response_schema,
)

SYNTHETIC_FACTS: list[dict[str, Any]] = [
    {
        "id": "10000000-0000-4000-8000-000000000001",
        "fact_type": "medication",
        "value": {
            "name": "Sampleformin",
            "dosage": "500 mg",
            "frequency": "twice daily",
            "route": "oral",
            "instructions": "Take with meals.",
        },
        "confidence_score": 0.95,
        "uncertainty": [],
    },
    {
        "id": "10000000-0000-4000-8000-000000000002",
        "fact_type": "obligation",
        "value": {
            "description": "Take a 20-minute walk.",
            "frequency": "three times weekly",
            "obligation_type": "movement",
        },
        "confidence_score": 0.91,
        "uncertainty": [],
    },
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the synthetic fixture and schema without calling a model.",
    )
    parser.add_argument(
        "--fact-count",
        type=int,
        default=12,
        help="Number of synthetic source facts to classify (2–100; default 12).",
    )
    args = parser.parse_args(argv)
    if not 2 <= args.fact_count <= 100:
        parser.error("--fact-count must be between 2 and 100")
    return args


def synthetic_facts(count: int) -> list[dict[str, Any]]:
    """Vary only fictional IDs and labels; never load a patient's database row."""
    facts: list[dict[str, Any]] = []
    for index in range(count):
        template = SYNTHETIC_FACTS[index % len(SYNTHETIC_FACTS)]
        value = dict(template["value"])
        if template["fact_type"] == "medication":
            value["name"] = f"Sampleformin-{index + 1}"
        else:
            value["description"] = f"Take a 20-minute walk on day {index + 1}."
        facts.append({**template, "id": str(UUID(int=10_000 + index)), "value": value})
    return facts


def _result(**fields: object) -> None:
    """Print only contract metadata, never prompt or provider response text."""
    print(json.dumps(fields, sort_keys=True))


async def run(*, dry_run: bool, fact_count: int = 12) -> int:
    facts = synthetic_facts(fact_count)
    schema = response_schema()
    if dry_run:
        _result(
            status="dry_run_passed",
            fact_count=len(facts),
            schema_property_count=len(schema.get("properties", {})),
        )
        return 0
    try:
        categories = await classify_facts(facts, record_telemetry=False)
    except CarePlanClassificationError as error:
        _result(status="failed", failure_code=error.code, **error.diagnostics)
        return 1
    except GenerationProviderError as error:
        _result(status="failed", failure_code=f"provider_{error.code.value}")
        return 1

    _result(
        status="passed",
        fact_count=len(facts),
        selected_item_count=len(categories),
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return asyncio.run(run(dry_run=args.dry_run, fact_count=args.fact_count))


if __name__ == "__main__":  # pragma: no cover - command entry point
    raise SystemExit(main())
