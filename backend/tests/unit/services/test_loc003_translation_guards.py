"""LOC-003 deterministic logic: translation guards, locale routing, fact-field selection.

These cover the safety-relevant, model-independent parts: numbers must be counted
consistently (the guard that blocks a bad translation), messages must route to the
correct target language, and only translatable fact fields are ever sent for translation
(values, units and dates are never translated).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services import fact_display_translation as facts
from app.services import message_translation as messages
from app.services.message_translation import MessageTranslationService


class TestMessageNumberGuard:
    def test_identical_numbers_match(self) -> None:
        assert messages._numbers("Take 500 mg twice") == messages._numbers("Toma 500 mg dos veces")

    def test_different_numbers_do_not_match(self) -> None:
        assert messages._numbers("Take 500 mg") != messages._numbers("Take 250 mg")

    def test_decimal_comma_and_dot_are_equivalent(self) -> None:
        # Spanish often writes 2,5 where English writes 2.5; the guard treats them the same.
        assert messages._numbers("2,5 ml") == messages._numbers("2.5 ml")

    def test_other_locale_flips(self) -> None:
        assert messages._other_locale("en-US") == "es-MX"
        assert messages._other_locale("es-MX") == "en-US"


class TestMessageLocaleRouting:
    def _service(self) -> MessageTranslationService:
        return MessageTranslationService(MagicMock())

    def test_clinician_always_translates_to_spanish(self) -> None:
        source, target = self._service().detect_and_get_target_locale(
            "Please take your medication tonight.", "clinician"
        )
        assert source == "en-US"
        assert target == "es-MX"

    def test_patient_spanish_translates_to_english(self) -> None:
        source, target = self._service().detect_and_get_target_locale(
            "Hola doctora, no me siento bien y tengo mucho dolor hoy.", "patient"
        )
        assert source == "es-MX"
        assert target == "en-US"

    def test_patient_english_translates_to_spanish(self) -> None:
        source, target = self._service().detect_and_get_target_locale(
            "Hello doctor, I do not feel well and have a lot of pain today.", "patient"
        )
        assert source == "en-US"
        assert target == "es-MX"


class TestFactTranslatableFields:
    def test_only_whitelisted_fields_are_returned(self) -> None:
        value = {
            "name": "Metformina",
            "dosage": "500 mg",  # never translated
            "frequency": "dos veces al día",
            "route": "oral",  # never translated
        }
        fields = facts.translatable_fields("medication", value)
        assert set(fields) == {"frequency"}
        assert "dosage" not in fields
        assert "route" not in fields

    def test_lab_result_value_and_unit_are_never_translatable(self) -> None:
        value = {"test_name": "Glucosa en ayunas", "value": "126", "unit": "mg/dL"}
        fields = facts.translatable_fields("lab_result", value)
        assert set(fields) == {"test_name"}

    def test_empty_fields_are_skipped(self) -> None:
        value = {"name": "Metformina", "frequency": "   "}
        fields = facts.translatable_fields("medication", value)
        assert fields == {}


class TestFactSpanishDetection:
    def test_spanish_instruction_is_detected(self) -> None:
        value = {
            "description": "Tome un vaso de agua con cada comida y camine después de cenar",
            "frequency": "tres veces al día",
        }
        assert facts.is_spanish_fact(value, "obligation") is True

    def test_english_instruction_is_not_spanish(self) -> None:
        value = {
            "description": "Drink a glass of water with each meal and walk after dinner",
            "frequency": "three times a day",
        }
        assert facts.is_spanish_fact(value, "obligation") is False

    def test_fact_with_no_translatable_fields_is_not_spanish(self) -> None:
        value = {"value": "126", "unit": "mg/dL"}
        assert facts.is_spanish_fact(value, "lab_result") is False


class TestFactNumberGuard:
    def test_numbers_counted_across_all_fields(self) -> None:
        source = {"name": "Metformina 500", "frequency": "2 veces"}
        same = {"name": "Metformin 500", "frequency": "2 times"}
        changed = {"name": "Metformin 850", "frequency": "2 times"}
        assert facts._all_numbers(source) == facts._all_numbers(same)
        assert facts._all_numbers(source) != facts._all_numbers(changed)


class TestProperNamesAreNeverTranslated:
    def test_drug_and_allergen_names_are_not_translatable(self) -> None:
        assert "name" not in facts.translatable_fields(
            "medication", {"name": "Losartán", "instructions": "tomar con agua"}
        )
        assert facts.translatable_fields("allergy", {"allergen": "Penicilina"}) == {}
        assert facts.translatable_fields("immunization", {"vaccine": "Tdap"}) == {}

    def test_a_spanish_name_only_fact_is_still_detected_as_spanish(self) -> None:
        value = {"name": "Metformina", "instructions": "Tome una tableta con cada comida"}
        assert facts.is_spanish_fact(value, "medication") is True

    @pytest.mark.asyncio
    async def test_name_is_never_sent_to_the_model_nor_returned(self) -> None:
        sent: dict[str, str] = {}

        async def fake(*_args, **kwargs):
            sent["prompt"] = kwargs["prompt"]
            return SimpleNamespace(text='{"fields": {"instructions": "take with water"}}')

        with patch.object(facts, "generate_for_workload", fake):
            out = await facts.translate_fact_to_english(
                "medication", {"name": "Losartán", "instructions": "tomar con agua"}
            )
        assert "Losartán" not in sent["prompt"]
        assert out == {"instructions": "take with water"}
