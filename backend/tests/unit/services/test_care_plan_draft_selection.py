"""Safety tests for the evidence-constrained automatic draft selector."""

from __future__ import annotations

import json
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.models.clinical_fact import SourceArtifactType
from app.models.generation import (
    GenerationErrorCode,
    GenerationProviderError,
    GenerationResponse,
    GenerationTelemetry,
)
from app.services import care_plan_classification, care_plan_service
from app.services.care_plan_service import CarePlanService

MEDICATION_FACT_ID = UUID("00000000-0000-0000-0000-000000000101")
MONITORING_FACT_ID = UUID("00000000-0000-0000-0000-000000000102")


@pytest.mark.parametrize(
    "field,maximum", [("description", 300), ("instructions", 2000), ("frequency", 200)]
)
@pytest.mark.parametrize("extra", [0, 1, 38])
def test_source_field_limits_preserve_evidence_and_block_overflow(
    field: str, maximum: int, extra: int
) -> None:
    fact = _facts()[0 if field == "instructions" else 1]
    fact["value"][field] = "é" * (maximum + extra)
    original = deepcopy(fact)
    item = CarePlanService(MagicMock())._item_from_fact(
        fact, category="medication" if field == "instructions" else "monitoring", conflict={}
    )
    assert fact == original
    assert item["source_fact_id"] == fact["id"]
    assert len(item["title"]) <= 300
    assert len(item["instructions"]) <= 2000
    assert len(item["frequency"]) <= 200
    assert bool(item["blocker_reason"]) is bool(extra)
    if extra and field != "description":
        assert item[field] == ""
    if extra and field == "description":
        assert item["title"].endswith("…")
        assert item["instructions"] == original["value"][field]


@pytest.mark.asyncio
async def test_oversized_title_does_not_fail_the_generation_batch() -> None:
    service = CarePlanService(MagicMock())
    facts = _facts()
    facts[1]["value"]["description"] = "x" * 338
    service._plan_facts = MagicMock(return_value=facts)
    service._select_categories = AsyncMock(
        return_value={str(MEDICATION_FACT_ID): "medication", str(MONITORING_FACT_ID): "monitoring"}
    )
    service._open_draft = MagicMock(return_value={"id": str(UUID(int=303))})
    await service._generate(
        {
            "patient_id": str(UUID(int=302)),
            "request_id": str(UUID(int=301)),
            "source_watermark": "2026-10-01T23:00:00Z",
        }
    )
    name, payload = service.db.rpc.call_args.args
    assert name == "complete_care_plan_generation"
    assert len(payload["p_items"]) == 2
    assert payload["p_items"][1]["blocker_reason"] == care_plan_service._SOURCE_TITLE_REVIEW
    assert len(payload["p_items"][1]["title"]) == 300
    service.db.table.assert_not_called()


@pytest.mark.asyncio
async def test_missing_frequency_commits_a_cited_blocker_without_inventing_wording() -> None:
    service = CarePlanService(MagicMock())
    facts = _facts()
    facts[1]["value"].pop("frequency")
    service._plan_facts = MagicMock(return_value=facts)
    service._select_categories = AsyncMock(
        return_value={
            str(MEDICATION_FACT_ID): "medication",
            str(MONITORING_FACT_ID): "monitoring",
        }
    )
    service._open_draft = MagicMock(return_value={"id": str(UUID(int=303))})
    await service._generate(
        {
            "patient_id": str(UUID(int=302)),
            "request_id": str(UUID(int=301)),
            "source_watermark": "2026-10-01T23:00:00Z",
        }
    )
    name, payload = service.db.rpc.call_args.args
    assert name == "complete_care_plan_generation"
    item = payload["p_items"][1]
    assert item["source_fact_id"] == str(MONITORING_FACT_ID)
    assert item["frequency"] == ""
    assert item["blocker_reason"]
    service.db.table.assert_not_called()


@pytest.mark.asyncio
async def test_source_contract_failure_has_a_safe_nonretryable_code() -> None:
    service = _service_with_claim()
    service._generate = AsyncMock(side_effect=care_plan_service.CarePlanSourceFieldsError())
    service._finish_request = MagicMock()
    service._retry = MagicMock()
    counts = await service.process_pending(limit=1)
    assert counts["care_plans_failed"] == 1
    assert service._finish_request.call_args.kwargs["failure"] == "source_fields_incomplete"
    service._retry.assert_not_called()


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


def _response(response: dict[str, object]) -> GenerationResponse:
    return GenerationResponse(
        text=json.dumps(response),
        telemetry=GenerationTelemetry(provider="flash", model="gemini-test", latency_ms=1),
    )


def _service_with_claim() -> CarePlanService:
    db = MagicMock()
    db.rpc.return_value.execute.return_value.data = [
        {
            "request_id": "00000000-0000-0000-0000-000000000301",
            "patient_id": "00000000-0000-0000-0000-000000000302",
            "attempt": 1,
            "source_watermark": "2026-10-01T23:00:00Z",
        }
    ]
    return CarePlanService(db)


@pytest.mark.asyncio
async def test_draft_selector_accepts_only_complete_fixed_fact_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _response(
        {
            "items": [
                {"source_fact_id": str(MEDICATION_FACT_ID), "category": "medication"},
                {"source_fact_id": str(MONITORING_FACT_ID), "category": "monitoring"},
            ]
        }
    )
    generate = AsyncMock(return_value=response)
    monkeypatch.setattr(care_plan_classification, "generate_for_workload", generate)

    selected = await CarePlanService(MagicMock())._select_categories(_facts())

    assert selected == {
        str(MEDICATION_FACT_ID): "medication",
        str(MONITORING_FACT_ID): "monitoring",
    }
    prompt = generate.await_args.kwargs["prompt"]
    assert "Metformin" in prompt
    assert "source_fact_id" in prompt
    assert generate.await_args.kwargs["response_schema"]["type"] == "object"


@pytest.mark.asyncio
async def test_draft_selector_rejects_an_invented_or_missing_fact_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _response(
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
    generate = AsyncMock(return_value=response)
    monkeypatch.setattr(care_plan_classification, "generate_for_workload", generate)

    with pytest.raises(ValueError, match="fact_selection_mismatch"):
        await CarePlanService(MagicMock())._select_categories(_facts())

    assert generate.await_count == 2


@pytest.mark.asyncio
async def test_draft_selector_repairs_one_semantic_contract_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generate = AsyncMock(
        side_effect=[
            _response(
                {"items": [{"source_fact_id": str(MEDICATION_FACT_ID), "category": "medication"}]}
            ),
            _response(
                {
                    "items": [
                        {"source_fact_id": str(MEDICATION_FACT_ID), "category": "medication"},
                        {"source_fact_id": str(MONITORING_FACT_ID), "category": "monitoring"},
                    ]
                }
            ),
        ]
    )
    monkeypatch.setattr(care_plan_classification, "generate_for_workload", generate)

    assert await CarePlanService(MagicMock())._select_categories(_facts()) == {
        str(MEDICATION_FACT_ID): "medication",
        str(MONITORING_FACT_ID): "monitoring",
    }
    assert "final schema-repair attempt" in generate.await_args.kwargs["prompt"]


@pytest.mark.asyncio
async def test_transient_provider_failure_is_scheduled_for_retry() -> None:
    service = _service_with_claim()
    service._generate = AsyncMock(
        side_effect=GenerationProviderError(GenerationErrorCode.TIMEOUT, "safe test failure")
    )
    service._retry = MagicMock(return_value=False)

    counts = await service.process_pending(limit=1)

    assert counts == {
        "care_plans_claimed": 1,
        "care_plans_ready": 0,
        "care_plans_retry": 1,
        "care_plans_failed": 0,
    }
    service._retry.assert_called_once_with(
        {
            "request_id": "00000000-0000-0000-0000-000000000301",
            "patient_id": "00000000-0000-0000-0000-000000000302",
            "attempt": 1,
            "source_watermark": "2026-10-01T23:00:00Z",
        },
        failure="provider_timeout",
    )


@pytest.mark.asyncio
async def test_invalid_model_response_fails_without_a_retry() -> None:
    service = _service_with_claim()
    service._generate = AsyncMock(side_effect=ValueError("safe test failure"))
    service._finish_request = MagicMock()

    counts = await service.process_pending(limit=1)

    assert counts == {
        "care_plans_claimed": 1,
        "care_plans_ready": 0,
        "care_plans_retry": 0,
        "care_plans_failed": 1,
    }
    service._finish_request.assert_called_once_with(
        {
            "request_id": "00000000-0000-0000-0000-000000000301",
            "patient_id": "00000000-0000-0000-0000-000000000302",
            "attempt": 1,
            "source_watermark": "2026-10-01T23:00:00Z",
        },
        status="failed",
        plan_id=None,
        failure="invalid_model_response",
    )


@pytest.mark.asyncio
async def test_terminal_generation_failure_logs_only_safe_operational_fields(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = _service_with_claim()
    service._generate = AsyncMock(side_effect=ValueError("private source text must not be logged"))
    service._finish_request = MagicMock()

    with caplog.at_level("WARNING", logger=care_plan_service.__name__):
        await service.process_pending(limit=1)

    events = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.getMessage().startswith("{")
    ]
    assert events == [
        {
            "attempt": 1,
            "event": "care_plan_generation_outcome",
            "failure_code": "invalid_model_response",
            "outcome": "care_plans_failed",
            "request_id": "00000000-0000-0000-0000-000000000301",
        }
    ]
    assert "private source text" not in caplog.text
    assert "00000000-0000-0000-0000-000000000302" not in caplog.text


@pytest.mark.asyncio
async def test_invalid_contract_logs_only_safe_validation_counts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = _service_with_claim()
    service._generate = AsyncMock(
        side_effect=care_plan_service.CarePlanClassificationError(
            "fact_selection_mismatch",
            {"missing_fact_count": 1, "returned_item_count": 1, "repair_attempted": 1},
        )
    )
    service._finish_request = MagicMock()

    with caplog.at_level("WARNING", logger=care_plan_service.__name__):
        await service.process_pending(limit=1)

    event = next(
        json.loads(record.getMessage())
        for record in caplog.records
        if record.getMessage().startswith("{")
    )
    assert event["failure_code"] == "invalid_model_response"
    assert event["missing_fact_count"] == 1
    assert event["repair_attempted"] == 1


@pytest.mark.asyncio
async def test_non_transient_provider_failure_fails_without_a_retry() -> None:
    service = _service_with_claim()
    service._generate = AsyncMock(
        side_effect=GenerationProviderError(GenerationErrorCode.CONFIGURATION, "safe test failure")
    )
    service._finish_request = MagicMock()

    counts = await service.process_pending(limit=1)

    assert counts["care_plans_failed"] == 1
    assert counts["care_plans_retry"] == 0
    service._finish_request.assert_called_once_with(
        {
            "request_id": "00000000-0000-0000-0000-000000000301",
            "patient_id": "00000000-0000-0000-0000-000000000302",
            "attempt": 1,
            "source_watermark": "2026-10-01T23:00:00Z",
        },
        status="failed",
        plan_id=None,
        failure="provider_configuration",
    )


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


@pytest.mark.parametrize("removed,confirmed,blocked", [(False, True, True), (True, False, False)])
def test_confirmation_cannot_supply_missing_instructions(
    removed: bool, confirmed: bool, blocked: bool
) -> None:
    blocker = CarePlanService._blocker(
        category="monitoring",
        title="Record walking",
        instructions="",
        frequency="",
        medication={},
        confidence=0.95,
        removed=removed,
        confirmed=confirmed,
    )
    assert bool(blocker) is blocked


def test_incomplete_removed_item_can_be_submitted_without_fabrication() -> None:
    from app.models.care_plan import CarePlanItemUpdate

    item = CarePlanItemUpdate(
        id=MONITORING_FACT_ID,
        title="Record walking",
        instructions="",
        frequency="",
        is_removed=True,
    )
    assert item.instructions == item.frequency == ""


def test_legacy_obligation_payload_stages_a_provenance_backed_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clinician_id = UUID("00000000-0000-0000-0000-000000000201")
    patient_id = UUID("00000000-0000-0000-0000-000000000202")
    fact_id = UUID("00000000-0000-0000-0000-000000000203")
    created_candidates = []

    class FakeFactService:
        def __init__(self, _db: MagicMock) -> None:
            pass

        def create_candidate(self, candidate: object, *, actor_id: UUID) -> dict[str, str]:
            created_candidates.append((candidate, actor_id))
            return {"id": str(fact_id)}

    db = MagicMock()
    service = CarePlanService(db)
    monkeypatch.setattr(care_plan_service, "ClinicalFactService", FakeFactService)
    monkeypatch.setattr(service, "_require_assignment", lambda *_args: None)
    monkeypatch.setattr(service, "_open_draft", lambda *_args: {"id": str(UUID(int=204))})
    monkeypatch.setattr(
        service, "_hydrate_plan", lambda plan: {"id": plan["id"], "status": "draft"}
    )

    result = service.add_clinician_authored_obligation(
        clinician_id,
        patient_id,
        {
            "obligation_type": "exercise",
            "description": "Walk for 20 minutes.",
            "frequency": "3x per week",
            "notes": "Stop if you feel unwell.",
        },
    )

    assert result["status"] == "draft"
    candidate, actor_id = created_candidates[0]
    assert actor_id == clinician_id
    assert candidate.provenance.artifact_type is SourceArtifactType.CLINICIAN_ENTRY
    assert candidate.value == {
        "description": "Walk for 20 minutes.",
        "frequency": "3x per week",
        "obligation_type": "exercise",
        "instructions": "Stop if you feel unwell.",
    }
    assert candidate.citations[0].excerpt.startswith("Walk for 20 minutes.")

    item_chain = db.table.return_value
    item_chain.insert.assert_any_call(
        {
            "plan_version_id": str(UUID(int=204)),
            "source_fact_id": str(fact_id),
            "category": "movement",
            "title": "Walk for 20 minutes.",
            "instructions": "Stop if you feel unwell.",
            "frequency": "3x per week",
            "confidence_score": 1.0,
            "uncertainty": [],
            "conflict": {},
            "blocker_reason": None,
        }
    )
