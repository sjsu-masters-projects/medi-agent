"""Page classification from measured signals, decided before any OCR runs.

Classification only looks at what the container reports (text characters, image
coverage) and, when neither exists, at rendered ink. It never consults a model, so
the decision to run OCR is auditable and cheap.
"""

from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel, Field

from app.services.document_intelligence.models import DocumentIntelligencePolicy, PageClass

PDF_MAGIC = b"%PDF-"
RASTER_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
)
SUPPORTED_RASTER_MIME = frozenset({"image/png", "image/jpeg", "image/webp", "image/tiff"})

_VOWELS = frozenset("aeiouy")
_MAX_ABBREVIATION_LENGTH = 5


class PageSignals(BaseModel):
    """Container-level facts about a page, measured without OCR."""

    text_chars: int = Field(ge=0)
    text_sanity: float = Field(ge=0.0, le=1.0)
    image_coverage: float = Field(ge=0.0, le=1.0)
    ink_ratio: float | None = Field(default=None, ge=0.0, le=1.0)


def sniff_container(content: bytes, mime_type: str) -> str | None:
    """Return ``pdf``, ``image``, ``corrupt``, or ``None`` for an unsupported type.

    Magic bytes win over the declared MIME type: a renamed file must not be opened with
    the wrong parser. A supported MIME type whose bytes match no known container is
    ``corrupt`` (unreadable), while an unknown MIME type is unsupported.
    """
    if content.startswith(PDF_MAGIC):
        return "pdf"
    for magic, _ in RASTER_MAGIC:
        if content.startswith(magic):
            return "image"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image"
    if mime_type == "application/pdf" or mime_type in SUPPORTED_RASTER_MIME:
        return "corrupt"
    return None


def embedded_text_sanity(text: str) -> float:
    """Fraction of alphabetic tokens that look like language rather than OCR debris.

    A PDF produced by an earlier, poor OCR pass carries an invisible text layer full of
    consonant clusters. Trusting it would skip OCR and feed garbage to the model.
    Short tokens are accepted as abbreviations (``mg``, ``BID``, ``HbA1c``).
    """
    normalized = unicodedata.normalize("NFKD", text).casefold()
    tokens = [token for token in re.split(r"\s+", normalized) if token]
    alphabetic = [token for token in tokens if sum(ch.isalpha() for ch in token) >= 2]
    if not alphabetic:
        return 1.0
    plausible = sum(1 for token in alphabetic if _looks_like_a_word(token))
    return plausible / len(alphabetic)


def _looks_like_a_word(token: str) -> bool:
    letters = "".join(ch for ch in token if ch.isalpha())
    if len(letters) <= _MAX_ABBREVIATION_LENGTH:
        return True
    if len(letters) > 30:
        return False
    return any(ch in _VOWELS for ch in letters)


def classify_page(
    signals: PageSignals, policy: DocumentIntelligencePolicy
) -> tuple[PageClass, list[str]]:
    """Decide how a page will be read and explain any fallback."""
    warnings: list[str] = []
    has_text = signals.text_chars >= policy.min_text_chars
    text_is_sane = signals.text_sanity >= policy.embedded_text_sanity_floor

    if has_text and text_is_sane:
        if signals.image_coverage >= policy.mixed_page_image_coverage:
            return PageClass.MIXED, warnings
        return PageClass.BORN_DIGITAL_TEXT, warnings

    if has_text and not text_is_sane:
        warnings.append(
            "Embedded text layer failed the sanity check and was ignored; OCR was used instead."
        )
        return PageClass.SCANNED_IMAGE, warnings

    if signals.image_coverage >= policy.scanned_page_image_coverage:
        return PageClass.SCANNED_IMAGE, warnings

    if signals.ink_ratio is None or signals.ink_ratio < policy.blank_ink_ratio:
        return PageClass.BLANK, warnings

    warnings.append("Page has drawn content but no text layer or image; OCR was used.")
    return PageClass.SCANNED_IMAGE, warnings
