"""Safety tests for the evidence-constrained automatic draft selector."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.services import care_plan_service
from app.services.care_plan_service import CarePlanService

MEDICATION_FACT_ID = UUID("00000000-0000-0000-0000-000000000101")
MONITORING_FACT_ID = UUID("00000000-0000-0000-0000-000000000102")


def _facts() -> list[dict[str, object]]:
    return [
        {
            "id": str(MEDICATION_FACT_ID),
            "fact_type": "medication",
            "value": {
                "name": "Metformin",
                "dosage": "500 mg",
                "frequency": "twice daily",
                "route": "oral",
                "instructions": "Take one tablet by mouth twice daily with meals.",
            },
            "confidence_score": 0.92,
            "uncertainty": [],
        },
        {
            "id": str(MONITORING_FACT_ID),
            "fact_type": "obligation",
            "value": {
                "description": "Check fasting blood glucose before breakfast each day.",
                "frequency": "daily",
                "obligation_type": "monitoring",
            },
            "confidence_score": 0.91,
            "uncertainty": [],
        },
    ]


def _router_for(response: dict[str, object]) -> MagicMock:
    router = MagicMock()
    router.generate_text_with_telemetry = AsyncMock(
        return_value=(json.dumps(response), MagicMock())
    )
    return router


@pytest.mark.asyncio
async def test_draft_selector_accepts_only_complete_fixed_fact_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = _router_for(
        {
            "items": [
                {"source_fact_id": str(MEDICATION_FACT_ID), "category": "medication"},
                {"source_fact_id": str(MONITORING_FACT_ID), "category": "monitoring"},
            ]
        }
    )
    monkeypatch.setattr(care_plan_service, "get_router", lambda: router)

    selected = await CarePlanService(MagicMock())._select_categories(_facts())

    assert selected == {
        str(MEDICATION_FACT_ID): "medication",
        str(MONITORING_FACT_ID): "monitoring",
    }
    prompt = router.generate_text_with_telemetry.await_args.kwargs["prompt"]
    assert "Metformin" in prompt
    assert "source_fact_id" in prompt


@pytest.mark.asyncio
async def test_draft_selector_rejects_an_invented_or_missing_fact_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    router = _router_for(
        {
            "items": [
                {"source_fact_id": str(MEDICATION_FACT_ID), "category": "medication"},
                {
                    "source_fact_id": "00000000-0000-0000-0000-000000000999",
                    "category": "monitoring",
                },
            ]
        }
    )
    monkeypatch.setattr(care_plan_service, "get_router", lambda: router)

    with pytest.raises(ValueError, match="exactly once"):
        await CarePlanService(MagicMock())._select_categories(_facts())


def test_conflicting_medication_sources_block_every_candidate() -> None:
    facts = [
        _facts()[0],
        {
            "id": "00000000-0000-0000-0000-000000000103",
            "fact_type": "medication",
            "value": {
                "name": "Metformin",
                "dosage": "1000 mg",
                "frequency": "once daily",
                "route": "oral",
                "instructions": "Take one tablet by mouth once daily with the evening meal.",
            },
        },
    ]

    conflicts = CarePlanService._medication_conflicts(facts)

    assert set(conflicts) == {str(MEDICATION_FACT_ID), "00000000-0000-0000-0000-000000000103"}
    item = CarePlanService(MagicMock())._item_from_fact(
        facts[0], category="medication", conflict=conflicts[str(MEDICATION_FACT_ID)]
    )
    assert item["instructions"] == "Take one tablet by mouth twice daily with meals."
    assert item["blocker_reason"] == "Resolve conflicting medication instructions before approval."
