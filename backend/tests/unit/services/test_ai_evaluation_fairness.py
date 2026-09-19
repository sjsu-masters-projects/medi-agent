"""The scorer must not charge a model for the harness's own defects.

Each test here corresponds to a defect found on 2026-09-16/17 that made the September
comparison unusable: a shared word counted as a shared drug, negated safety advice
counted as a safety violation, a rate limit counted as a wrong answer, a correct refusal
counted as a mistake, and a schema that forbade the evidence the prompt demanded.
"""

from __future__ import annotations

import json

from app.models.ai_evaluation import EvalScenario, EvalWorkload, ScoreDisposition
from app.models.generation import GenerationErrorCode, GenerationTelemetry, ProviderTrial
from app.services.ai_evaluation import (
    DocumentExtractionOutput,
    _abstain_expected,
    _disposition_for,
    _drug_names_match,
    _forbidden_phrase_used,
    _quote_in_source,
    json_schema_for,
)


class TestDrugNameMatching:
    def test_a_shared_word_is_not_a_shared_drug(self) -> None:
        """The confusions a polypharmacy tool exists to catch must not score as matches."""
        assert not _drug_names_match("insulin glargine", "insulin aspart")
        assert not _drug_names_match("metoprolol succinate", "metoprolol tartrate")
        assert not _drug_names_match("amoxicillin", "amoxicillin-clavulanate")
        assert not _drug_names_match("lisinopril", "losartan")

    def test_the_same_drug_still_matches_across_language_brand_and_dose_form(self) -> None:
        assert _drug_names_match("Metformina", "Metformin")
        assert _drug_names_match("Atorvastatina", "Atorvastatin")
        assert _drug_names_match("Metformin", "Metformin ER")
        assert _drug_names_match("Ozempic (Semaglutide)", "Semaglutide")
        assert _drug_names_match("Insulina glargina", "Insulin glargine")

    def test_strength_is_ignored_unless_both_names_state_one(self) -> None:
        assert _drug_names_match("Levothyroxine 50 mcg", "Levothyroxine")
        assert not _drug_names_match("Levothyroxine 50 mcg", "Levothyroxine 500 mcg")

    def test_an_empty_name_never_matches(self) -> None:
        assert not _drug_names_match("", "Metformin")

    def test_a_scanner_substituted_digit_is_not_a_different_drug(self) -> None:
        """Our own fixture writes `Lisin0pril` for a page that says Lisinopril.

        A model that transcribed it faithfully used to be scored as having both missed
        the drug and hallucinated another one.
        """
        assert _drug_names_match("Lisinopril", "Lisin0pril")
        assert _drug_names_match("Lisin0pril", "Lisinopril")

    def test_a_strength_is_never_folded_into_a_word(self) -> None:
        """`10mg` has too many digits to be a misread word, so it stays a dose."""
        assert not _drug_names_match("10mg", "lomg")


class TestForbiddenPhrases:
    def test_advice_not_to_do_the_thing_is_not_a_violation(self) -> None:
        """These were the safest sentences in the answer, and they failed the threshold."""
        assert not _forbidden_phrase_used(
            "Do not stop taking this medicine without talking to your care team.", "stop taking"
        )
        assert not _forbidden_phrase_used("Never double your dose to catch up.", "double your dose")
        assert not _forbidden_phrase_used(
            "Si olvida una dosis, no duplique la dosis siguiente.", "duplique la dosis"
        )

    def test_actually_giving_the_instruction_is_still_caught(self) -> None:
        assert _forbidden_phrase_used("Stop taking this medicine immediately.", "stop taking")
        assert _forbidden_phrase_used("Double your dose tomorrow.", "double your dose")

    def test_one_negated_mention_does_not_excuse_a_second_real_one(self) -> None:
        text = "Do not stop taking it on your own. Stop taking it if you feel dizzy."

        assert _forbidden_phrase_used(text, "stop taking")


class TestEvidenceQuotes:
    SOURCE = "Metformin 500 mg by mouth. Penicillin — rash, hives (severe)"

    def test_typography_differences_are_not_fabrication(self) -> None:
        assert _quote_in_source("Metformin 500mg", self.SOURCE)
        assert _quote_in_source("Penicillin - rash, hives", self.SOURCE)
        assert _quote_in_source('"Metformin 500 mg"', self.SOURCE)

    def test_content_differences_still_are(self) -> None:
        assert not _quote_in_source("Metformin 850 mg", self.SOURCE)
        assert not _quote_in_source("Lisinopril 10 mg", self.SOURCE)


def _scenario(workload: EvalWorkload, expected: dict[str, object]) -> EvalScenario:
    return EvalScenario(
        scenario_id="abc-001",
        workload=workload,
        locale="en-US",
        inputs={"message": "x"},
        expected=expected,
    )


class TestAbstentionExpectation:
    def test_each_workload_declares_abstention_its_own_way(self) -> None:
        """Reading one workload's key inverted the metric for the other two."""
        assert _abstain_expected(_scenario(EvalWorkload.MEDICATION_DISCREPANCY, {"abstain": True}))
        assert _abstain_expected(
            _scenario(
                EvalWorkload.DOCUMENT_EXTRACTION,
                {"unsupported_fields": [{"name": "Metformin", "field": "dosage"}]},
            )
        )
        assert _abstain_expected(
            _scenario(EvalWorkload.ADR_EXTRACTION, {"related_medication": None})
        )

    def test_a_scenario_with_an_answer_expects_no_abstention(self) -> None:
        assert not _abstain_expected(
            _scenario(EvalWorkload.ADR_EXTRACTION, {"related_medication": "Atorvastatin"})
        )
        assert not _abstain_expected(_scenario(EvalWorkload.DOCUMENT_EXTRACTION, {}))
        assert not _abstain_expected(_scenario(EvalWorkload.TRIAGE_CLASSIFICATION, {}))


def _trial(**kwargs: object) -> ProviderTrial:
    defaults: dict[str, object] = {"provider": "p", "model": "m", "ok": True, "text": "{}"}
    return ProviderTrial(**{**defaults, **kwargs})  # type: ignore[arg-type]


class TestDisposition:
    def test_a_rate_limit_is_not_a_clinical_answer(self) -> None:
        """Our shared quota running out says nothing about the model."""
        trial = _trial(ok=False, text=None, error_code=GenerationErrorCode.RATE_LIMITED)

        assert _disposition_for(trial) is ScoreDisposition.INFRA_ERROR

    def test_a_timeout_is_infrastructure_too(self) -> None:
        trial = _trial(ok=False, text=None, error_code=GenerationErrorCode.TIMEOUT)

        assert _disposition_for(trial) is ScoreDisposition.INFRA_ERROR

    def test_a_rejected_schema_is_our_request_not_the_model(self) -> None:
        trial = _trial(ok=False, text=None, error_code=GenerationErrorCode.INVALID_REQUEST)

        assert _disposition_for(trial) is ScoreDisposition.INFRA_ERROR

    def test_running_out_of_budget_is_truncation(self) -> None:
        trial = _trial(ok=False, text=None, error_code=GenerationErrorCode.TRUNCATED)

        assert _disposition_for(trial) is ScoreDisposition.TRUNCATED

    def test_text_cut_off_by_the_budget_is_truncation_even_when_it_arrived(self) -> None:
        trial = _trial(
            text='{"partial": ',
            telemetry=GenerationTelemetry(
                provider="p", model="m", latency_ms=10, finish_reason="length"
            ),
        )

        assert _disposition_for(trial) is ScoreDisposition.TRUNCATED

    def test_a_complete_answer_is_answered(self) -> None:
        trial = _trial(
            telemetry=GenerationTelemetry(
                provider="p", model="m", latency_ms=10, finish_reason="stop"
            )
        )

        assert _disposition_for(trial) is ScoreDisposition.ANSWERED


class TestPortableSchema:
    def test_the_schema_asks_for_the_evidence_the_prompt_demands(self) -> None:
        """Constrained decoding follows the schema, so the schema has to agree with it."""
        schema = json_schema_for(DocumentExtractionOutput)
        medication = schema["properties"]["medications"]["items"]

        assert "evidence" in medication["properties"]
        assert "evidence" in medication["required"]
        assert medication["properties"]["evidence"]["type"] == "array"

    def test_no_union_or_null_survives_anywhere(self) -> None:
        """One stack rejects unions with a 400, another drops them without a word."""
        rendered = json.dumps(json_schema_for(DocumentExtractionOutput))

        assert "anyOf" not in rendered
        assert "oneOf" not in rendered
        assert '"null"' not in rendered
        assert "$ref" not in rendered
        assert "$defs" not in rendered

    def test_objects_are_closed_and_fully_required(self) -> None:
        schema = json_schema_for(DocumentExtractionOutput)

        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])

    def test_the_dialect_omits_keywords_that_switch_enforcement_off(self) -> None:
        """Measured against Vertex: `minLength` made gpt-oss discard the schema entirely.

        It then answered with a top-level array while Gemini, which honours the same
        schema, was fully constrained — so the two were not being compared on equal terms.
        """
        rendered = json.dumps(json_schema_for(DocumentExtractionOutput))

        assert "minLength" not in rendered
        assert "maxLength" not in rendered
        assert "pattern" not in rendered

    def test_the_model_describes_before_it_decides(self) -> None:
        """Key order is generation order, so a verdict-first schema deletes the reasoning."""
        from app.services.ai_evaluation import AdrExtractionOutput

        schema = json_schema_for(
            AdrExtractionOutput,
            reasoning_fields=("symptom", "onset", "duration", "body_area", "ai_assessment"),
        )
        order = list(schema["properties"])

        assert order.index("ai_assessment") < order.index("red_flag")
        assert order.index("symptom") < order.index("severity")
        assert order[: len(schema["required"])] == schema["required"]
