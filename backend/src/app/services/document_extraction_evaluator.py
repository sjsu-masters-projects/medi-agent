"""Deterministically score recorded synthetic document-extraction output."""

from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from app.models.document_evaluation import DocumentExtractionEvaluation
from app.models.document_extraction import DocumentExtractionResult

_SPACE = re.compile(r"\s+")


def evaluate_recorded_extraction(
    *,
    source_pages: list[str],
    expected: DocumentExtractionResult,
    output: dict[str, Any],
    latency_ms: int | None = None,
    estimated_cost_usd: float | None = None,
) -> DocumentExtractionEvaluation:
    """Score stored JSON without invoking a provider or accepting clinical data."""
    try:
        actual = DocumentExtractionResult.model_validate(output)
    except ValidationError as exc:
        return DocumentExtractionEvaluation(
            schema_valid=False,
            candidate_precision=0,
            candidate_recall=0,
            evidence_valid_rate=0,
            abstained=not _has_candidates(output),
            latency_ms=latency_ms,
            estimated_cost_usd=estimated_cost_usd,
            errors=[item["msg"] for item in exc.errors()],
        )

    expected_keys = _keys(expected)
    actual_keys = _keys(actual)
    matched = expected_keys & actual_keys
    precision = len(matched) / len(actual_keys) if actual_keys else 1.0
    recall = len(matched) / len(expected_keys) if expected_keys else 1.0
    evidence_total, evidence_valid = _evidence_score(actual, source_pages)
    return DocumentExtractionEvaluation(
        schema_valid=True,
        candidate_precision=precision,
        candidate_recall=recall,
        evidence_valid_rate=evidence_valid / evidence_total if evidence_total else 1.0,
        abstained=not actual_keys,
        latency_ms=latency_ms,
        estimated_cost_usd=estimated_cost_usd,
    )


def _keys(extraction: DocumentExtractionResult) -> set[tuple[str, str]]:
    return (
        {("medication", item.name.casefold()) for item in extraction.medications}
        | {("condition", item.name.casefold()) for item in extraction.conditions}
        | {("allergy", item.allergen.casefold()) for item in extraction.allergies}
        | {("obligation", item.description.casefold()) for item in extraction.obligations}
    )


def _evidence_score(extraction: DocumentExtractionResult, pages: list[str]) -> tuple[int, int]:
    evidence = [
        item
        for collection in (
            extraction.medications,
            extraction.conditions,
            extraction.allergies,
            extraction.obligations,
        )
        for candidate in collection
        for item in candidate.evidence
    ]
    valid = sum(
        1
        for item in evidence
        if item.page <= len(pages) and _normalize(item.excerpt) in _normalize(pages[item.page - 1])
    )
    return len(evidence), valid


def _has_candidates(output: dict[str, Any]) -> bool:
    return any(
        isinstance(output.get(key), list) and output[key]
        for key in ("medications", "conditions", "allergies", "obligations")
    )


def _normalize(value: str) -> str:
    return _SPACE.sub(" ", value).strip()
