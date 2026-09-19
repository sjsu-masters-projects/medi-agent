"""Prompts keep clinical extraction and patient explanation separate."""

from app.agents.ingestion.prompts import EXTRACT_CONTENT_SYSTEM, GENERATE_SUMMARY_SYSTEM


def test_extraction_prompt_requires_source_wording_without_route_coding() -> None:
    assert "clinician-facing" in EXTRACT_CONTENT_SYSTEM
    assert "copy the source wording exactly" in EXTRACT_CONTENT_SYSTEM
    assert "Do not normalize, code, translate, or infer" in EXTRACT_CONTENT_SYSTEM
    assert "clinician-reviewed terminology step" in EXTRACT_CONTENT_SYSTEM


def test_patient_summary_prompt_is_plain_language_but_source_bounded() -> None:
    assert "patient-facing" in GENERATE_SUMMARY_SYSTEM
    assert "simple, warm language" in GENERATE_SUMMARY_SYSTEM
    assert "Do not diagnose" in GENERATE_SUMMARY_SYSTEM
    assert "unless that is explicitly present" in GENERATE_SUMMARY_SYSTEM
