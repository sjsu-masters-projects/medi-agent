"""Second-language drafting: deterministic guards and the review-only write path."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.core.exceptions import ValidationError
from app.models.generation import (
    GenerationErrorCode,
    GenerationProviderError,
    GenerationResponse,
    GenerationTelemetry,
)
from app.services import care_plan_service, care_plan_translation
from app.services.care_plan_service import CarePlanService
from app.services.care_plan_translation import (
    detect_locale,
    draft_translations,
    validate_draft,
)
from tests.unit.services.care_plan_ownership_stub import stub_ownership

ITEM = UUID(int=11)
PLAN = UUID(int=12)
PATIENT = UUID(int=13)
CLINICIAN = UUID(int=14)


def _response(items: list[dict[str, Any]]) -> GenerationResponse:
    return GenerationResponse(
        text=json.dumps({"items": items}),
        telemetry=GenerationTelemetry(provider="flash", model="gemini-test", latency_ms=1),
    )


def _medication(**changes: Any) -> dict[str, Any]:
    return {
        "id": str(ITEM),
        "plan_version_id": str(PLAN),
        "category": "medication",
        "title": "Metformin 500 mg",
        "instructions": "Take 1 tablet by mouth twice daily with meals.",
        "frequency": "twice daily",
        "medication": {"name": "Metformin", "dosage": "500 mg"},
        **changes,
    }


SPANISH = {
    "title": "Metformin 500 mg",
    "instructions": "Tome 1 tableta por vía oral dos veces al día con las comidas.",
    "frequency": "dos veces al día",
}


@pytest.mark.parametrize(
    "texts,expected",
    [
        (("Revise su glucosa en ayunas antes del desayuno todos los días",), "es-MX"),
        (("Take 1 tablet by mouth twice daily with meals",), "en-US"),
        (("Metformin 500 mg",), None),
    ],
)
def test_detect_locale_only_answers_when_the_wording_is_clear(texts, expected) -> None:
    assert detect_locale(*texts) == expected


@pytest.mark.parametrize(
    "draft,reason",
    [
        (SPANISH, None),
        ({**SPANISH, "title": "Metformin 850 mg"}, "numbers_changed"),
        ({**SPANISH, "instructions": "Tome tabletas dos veces al día."}, "numbers_changed"),
        ({**SPANISH, "frequency": ""}, "field_missing"),
        ({**SPANISH, "title": "Metformina 500 mg"}, "medication_name_changed"),
    ],
)
def test_validate_draft_rejects_changed_clinical_facts(draft, reason) -> None:
    item = _medication()
    source = {field: item[field] for field in ("title", "instructions", "frequency")}
    assert validate_draft(source, draft, item) == reason


@pytest.mark.asyncio
async def test_drafts_keep_only_checked_translations_and_report_counts(monkeypatch) -> None:
    second = _medication(id=str(UUID(int=21)))
    third = _medication(id=str(UUID(int=22)))
    generate = AsyncMock(
        return_value=_response(
            [
                {"id": str(ITEM), "source_locale": "es-MX", **SPANISH},
                {"id": second["id"], "source_locale": "en-US", **SPANISH, "title": "Metformin"},
            ]
        )
    )
    monkeypatch.setattr(care_plan_translation, "generate_for_workload", generate)

    drafts, diagnostics = await draft_translations([_medication(), second, third])

    # Local detection is confident here, so the model's wrong claim is ignored.
    assert drafts[str(ITEM)].source_locale == "en-US"
    assert drafts[str(ITEM)].target_locale == "es-MX"
    assert drafts[str(ITEM)].wording.instructions == SPANISH["instructions"]
    assert set(drafts) == {str(ITEM)}
    assert diagnostics == {
        "translation_requested_count": 3,
        "translation_drafted_count": 1,
        "translation_rejected_numbers_changed": 1,
        "translation_rejected_item_missing": 1,
    }
    prompt = generate.await_args.kwargs["prompt"]
    assert '"keep_unchanged": ["Metformin"]' in prompt
    assert generate.await_args.kwargs["temperature"] == 0


@pytest.mark.asyncio
async def test_invalid_response_drafts_nothing(monkeypatch) -> None:
    generate = AsyncMock(
        return_value=GenerationResponse(
            text="not json",
            telemetry=GenerationTelemetry(provider="flash", model="gemini-test", latency_ms=1),
        )
    )
    monkeypatch.setattr(care_plan_translation, "generate_for_workload", generate)
    drafts, diagnostics = await draft_translations([_medication()])
    assert drafts == {}
    assert diagnostics["translation_rejected_schema_invalid"] == 1


def _service(items: list[dict[str, Any]]) -> tuple[MagicMock, CarePlanService]:
    db = MagicMock()
    service = CarePlanService(db)
    stub_ownership(service)
    service._draft = MagicMock(return_value={"id": str(PLAN)})  # type: ignore[method-assign]
    service._items = MagicMock(return_value=items)  # type: ignore[method-assign]
    service._audit = MagicMock()  # type: ignore[method-assign]
    service._plan = MagicMock(return_value={"id": str(PLAN)})  # type: ignore[method-assign]
    service._hydrate_plan = MagicMock(return_value={"id": str(PLAN)})  # type: ignore[method-assign]
    return db, service


@pytest.mark.asyncio
async def test_generation_step_stores_unverified_drafts_for_untranslated_items(
    monkeypatch,
) -> None:
    translated = _medication(id=str(UUID(int=31)), wording={"en-US": SPANISH, "es-MX": SPANISH})
    removed = _medication(id=str(UUID(int=32)), is_removed=True)
    db, service = _service([_medication(), translated, removed])
    generate = AsyncMock(return_value=_response([{"id": str(ITEM), **SPANISH}]))
    monkeypatch.setattr(care_plan_translation, "generate_for_workload", generate)

    await service._draft_missing_translations(PLAN)

    assert '"id": "' + str(ITEM) in generate.await_args.kwargs["prompt"]
    assert str(UUID(int=31)) not in generate.await_args.kwargs["prompt"]
    assert str(UUID(int=32)) not in generate.await_args.kwargs["prompt"]
    payload = db.table.return_value.update.call_args.args[0]
    assert payload["source_locale"] == "en-US"
    assert payload["wording"]["en-US"]["title"] == "Metformin 500 mg"
    assert payload["wording"]["es-MX"] == SPANISH
    assert payload["wording_origin"] == {"en-US": "source", "es-MX": "ai_draft"}
    assert payload["wording_verified"] is False


@pytest.mark.asyncio
async def test_unavailable_translation_never_fails_generation(monkeypatch) -> None:
    db, service = _service([])
    service._plan_facts = MagicMock(return_value=[{"id": "f", "fact_type": "obligation"}])  # type: ignore[method-assign]
    service._select_categories = AsyncMock(return_value={"f": "movement"})  # type: ignore[method-assign]
    service._item_from_fact = MagicMock(return_value={"source_fact_id": "f"})  # type: ignore[method-assign]
    service._open_draft = MagicMock(return_value={"id": str(PLAN)})  # type: ignore[method-assign]
    service._draft_missing_translations = AsyncMock(  # type: ignore[method-assign]
        side_effect=GenerationProviderError(GenerationErrorCode.RATE_LIMITED, "busy")
    )
    logged = MagicMock()
    monkeypatch.setattr(service, "_log_translation_outcome", logged)

    await service._generate(
        {
            "patient_id": str(PATIENT),
            "care_plan_id": str(UUID(int=9)),
            "request_id": str(UUID(int=1)),
            "source_watermark": "x",
        }
    )

    db.rpc.assert_called_once()
    assert logged.call_args.args[1] == {"translation_provider_error": "rate_limited"}


@pytest.mark.asyncio
async def test_retranslate_drafts_from_the_source_language_only(monkeypatch) -> None:
    item = _medication(source_locale="en-US")
    db, service = _service([item])
    with pytest.raises(ValidationError, match="edit the source language first"):
        await service.retranslate_item(CLINICIAN, PATIENT, PLAN, ITEM, "es-MX")

    generate = AsyncMock(return_value=_response([{"id": str(ITEM), **SPANISH}]))
    monkeypatch.setattr(care_plan_translation, "generate_for_workload", generate)
    await service.retranslate_item(CLINICIAN, PATIENT, PLAN, ITEM, "en-US")

    payload = db.table.return_value.update.call_args.args[0]
    assert payload["wording_origin"]["es-MX"] == "ai_draft"
    assert payload["wording_verified"] is False
    service._audit.assert_called_once_with(
        PLAN, CLINICIAN, "translation_drafted", {"item_id": str(ITEM), "target_locale": "es-MX"}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome,message",
    [
        (GenerationProviderError(GenerationErrorCode.UNAVAILABLE, "down"), "unavailable right now"),
        (_response([{"id": str(ITEM), **SPANISH, "title": "Metformin 850 mg"}]), "was discarded"),
    ],
)
async def test_retranslate_failure_writes_nothing(monkeypatch, outcome, message) -> None:
    db, service = _service([_medication()])
    generate = AsyncMock(
        side_effect=outcome if isinstance(outcome, Exception) else None,
        return_value=None if isinstance(outcome, Exception) else outcome,
    )
    monkeypatch.setattr(care_plan_translation, "generate_for_workload", generate)
    with pytest.raises(ValidationError, match=message):
        await service.retranslate_item(CLINICIAN, PATIENT, PLAN, ITEM, "en-US")
    db.table.return_value.update.assert_not_called()
    service._audit.assert_not_called()


def test_service_module_uses_the_translation_workload() -> None:
    assert care_plan_service.draft_translations is draft_translations
