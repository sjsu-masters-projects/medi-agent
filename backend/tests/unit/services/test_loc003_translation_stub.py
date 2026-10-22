"""LOC-003: the offline translation stub, so these paths run without a live model.

The stub exists for one reason: every LOC-003 display rule, guard and attestation depends
on a translation, and a reviewer with no reachable Vertex AI model cannot exercise any of
them. These tests pin the two properties that make the stub safe to rely on — it never
changes a number, dose, medication name or negation, and it is inert in production.
"""

from __future__ import annotations

import json

import pytest

from app.services import translation_stub as stub
from app.services.care_plan_translation import back_translate_spanish, draft_translations
from app.services.fact_display_translation import translate_facts_to_english
from app.services.message_translation import translate_message
from app.services.translation_guards import guard_failure


@pytest.fixture
def stubbed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stub.settings, "translation_stub_enabled", True, raising=False)
    monkeypatch.setattr(stub.settings, "environment", "development", raising=False)


class TestStubEnablement:
    def test_off_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(stub.settings, "translation_stub_enabled", False, raising=False)
        assert stub.stub_enabled() is False

    def test_production_never_stubs_a_translation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unreviewed machine wording must not stand in for a translation for a patient."""
        monkeypatch.setattr(stub.settings, "translation_stub_enabled", True, raising=False)
        monkeypatch.setattr(stub.settings, "environment", "production", raising=False)
        assert stub.stub_enabled() is False

    def test_enabled_outside_production(self, stubbed: None) -> None:
        assert stub.stub_enabled() is True


class TestStubPreservesCheckedFacts:
    @pytest.mark.parametrize("target", ["es-MX", "en-US"])
    @pytest.mark.parametrize(
        "text",
        [
            "Take 1 tablet by mouth twice daily with meals",
            "Toma 2 vasos de agua cada día",
            "Metformin 500 mg, 1,000 mg weekly, 2.5 mL",
            "Do not take this without water",
            "No tomes esto sin agua",
        ],
    )
    def test_numbers_negations_and_names_survive(self, text: str, target: str) -> None:
        assert guard_failure(text, stub.translate_text(text, target), ["Metformin"]) is None

    def test_text_actually_changes_language(self) -> None:
        """A stub that returned the input would hide every display bug it exists to expose."""
        assert (
            stub.translate_text("Take 1 tablet with water", "es-MX") != "Take 1 tablet with water"
        )

    def test_unknown_words_pass_through_unchanged(self) -> None:
        assert "Jardiance" in stub.translate_text("Take Jardiance with water", "es-MX")

    def test_fields_are_translated_independently(self) -> None:
        translated = stub.translate_fields({"title": "water", "frequency": "daily"}, "es-MX")
        assert translated == {"title": "agua", "frequency": "al día"}


MEDICATION_ITEM = {
    "id": "item-1",
    "title": "Metformin 500 mg",
    "instructions": "Take 1 tablet by mouth twice daily with meals.",
    "frequency": "twice daily",
    "medication": {"name": "Metformin"},
}


@pytest.mark.asyncio
class TestEveryTranslationPathRunsOffline:
    async def test_second_language_drafting(self, stubbed: None) -> None:
        drafts, diagnostics = await draft_translations([MEDICATION_ITEM], record_telemetry=False)
        assert diagnostics["translation_drafted_count"] == 1
        draft = drafts["item-1"]
        assert draft.source_locale == "en-US"
        assert draft.target_locale == "es-MX"
        assert "500 mg" in draft.wording.title

    async def test_back_translation_reports_passing_guards(self, stubbed: None) -> None:
        english = {k: MEDICATION_ITEM[k] for k in ("title", "instructions", "frequency")}
        spanish = stub.translate_fields(english, "es-MX")
        result = await back_translate_spanish(spanish, english, MEDICATION_ITEM)
        assert result.numbers_match is True
        assert result.medication_names_match is True
        assert "500 mg" in result.title

    async def test_fact_display_fields(self, stubbed: None) -> None:
        translated = await translate_facts_to_english(
            [
                (
                    "f-1",
                    "obligation",
                    {"description": "Toma 2 vasos de agua", "frequency": "cada día"},
                )
            ]
        )
        assert translated["f-1"].fields == {
            "description": "Take 2 glasses of water",
            "frequency": "every day",
        }
        # The record says the text came from the stub, not from a reviewed model.
        assert translated["f-1"].model_id == stub.STUB_MODEL_ID

    async def test_message_translation_is_marked_as_stub_produced(self, stubbed: None) -> None:
        text, guard_passed, failure, model_id = await translate_message(
            "Toma 500 mg con agua", "es-MX", "en-US", ["Metformin"]
        )
        assert guard_passed is True
        assert failure is None
        assert "500 mg" in text
        # The record says where the wording came from, so it is never read as reviewed.
        assert model_id == stub.STUB_MODEL_ID


class TestStubResponseShape:
    def test_response_carries_stub_telemetry(self) -> None:
        response = stub.stub_response(json.dumps({"translated_text": "agua"}))
        assert response.telemetry.model == stub.STUB_MODEL_ID
        assert response.telemetry.provider == stub.STUB_PROVIDER
        assert json.loads(response.text) == {"translated_text": "agua"}
