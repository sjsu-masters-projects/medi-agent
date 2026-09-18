"""Anchor an extracted value back to the page text that supports it.

An extraction model may only propose; the deterministic layer decides whether the
proposal was actually read on a page. A value that cannot be anchored is not
rejected, but it is marked low confidence and routed to clinician review rather than
being presented as read from the document.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from app.services.document_intelligence.models import (
    DocumentExtraction,
    DocumentIntelligencePolicy,
    EvidenceAnchor,
    PageExtraction,
)

_DIGIT_LETTER_BOUNDARY = re.compile(r"(?<=\d)(?=[a-z%])|(?<=[a-z])(?=\d)")
_DECIMAL_COMMA = re.compile(r"(?<=\d),(?=\d)")
_NON_TOKEN = re.compile(r"[^a-z0-9./%-]+")
_LETTER_DOTS = re.compile(r"(?<=[a-z])\.|\.(?=[a-z])")


def normalize_for_match(text: str) -> str:
    """Fold case, accents, decimal commas, and unit spacing so both sides compare alike."""
    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = folded.casefold().replace("µ", "u").replace("μ", "u")
    folded = _DECIMAL_COMMA.sub(".", folded)
    folded = _LETTER_DOTS.sub("", folded)
    folded = _DIGIT_LETTER_BOUNDARY.sub(" ", folded)
    folded = _NON_TOKEN.sub(" ", folded)
    return " ".join(folded.split())


def anchor_value(
    extraction: DocumentExtraction, value: str, *, policy: DocumentIntelligencePolicy
) -> EvidenceAnchor | None:
    """Find the best-supported page for ``value`` across every usable page."""
    best: EvidenceAnchor | None = None
    for page in extraction.model_input_pages():
        anchor = anchor_on_page(page, value, policy=policy)
        if anchor and (best is None or anchor.match_score > best.match_score):
            best = anchor
            if best.match_score >= 1.0:
                break
    return best


def anchor_on_page(
    page: PageExtraction, value: str, *, policy: DocumentIntelligencePolicy
) -> EvidenceAnchor | None:
    target = normalize_for_match(value).split()
    if not target or not page.words:
        return None
    tokens = [(index, normalize_for_match(word.text)) for index, word in enumerate(page.words)]
    tokens = [(index, token) for index, token in tokens if token]
    match = _best_window(tokens, target, policy.anchor_min_similarity)
    if match is None:
        return None
    score, word_indexes = match
    return _build_anchor(page, word_indexes, score, policy)


def _best_window(
    tokens: list[tuple[int, str]], target: list[str], minimum: float
) -> tuple[float, list[int]] | None:
    """Slide windows of about the target's length and keep the most similar one.

    Tokens are re-split after normalization so ``500mg`` on the page still matches
    ``500 mg`` in the value; the window spans original word indexes for the bbox.
    """
    flat: list[tuple[int, str]] = []
    for index, token in tokens:
        flat.extend((index, piece) for piece in token.split())
    target_text = " ".join(target)
    best: tuple[float, list[int]] | None = None
    for size in {len(target), len(target) + 1, max(1, len(target) - 1)}:
        for start in range(0, max(1, len(flat) - size + 1)):
            window = flat[start : start + size]
            if not window:
                continue
            candidate = " ".join(piece for _, piece in window)
            if candidate == target_text:
                return 1.0, sorted({index for index, _ in window})
            score = SequenceMatcher(None, candidate, target_text).ratio()
            if score >= minimum and (best is None or score > best[0]):
                best = (score, sorted({index for index, _ in window}))
    return best


def _build_anchor(
    page: PageExtraction,
    word_indexes: list[int],
    score: float,
    policy: DocumentIntelligencePolicy,
) -> EvidenceAnchor:
    words = [page.words[index] for index in word_indexes]
    bbox = words[0].bbox
    for word in words[1:]:
        bbox = bbox.union(word.bbox)
    line_ids = sorted({word.line_id for word in words})
    lines_by_id = {line.line_id: line for line in page.lines}
    quote = " ".join(lines_by_id[line_id].text for line_id in line_ids if line_id in lines_by_id)
    return EvidenceAnchor(
        page_number=page.page_number,
        bbox=bbox,
        coordinate_unit=page.coordinate_unit,
        quote=quote[: policy.max_quote_chars] or " ".join(word.text for word in words),
        matched_text=" ".join(word.text for word in words),
        match_score=round(score, 4),
        word_confidence=round(min(word.confidence for word in words), 4),
        method=words[0].method,
        line_ids=line_ids,
    )
