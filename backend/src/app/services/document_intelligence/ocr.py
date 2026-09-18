"""OCR engine contract and the Tesseract implementation.

Tesseract is the auditable local baseline: it returns per-word confidence and
coordinates, runs offline, and costs nothing per page. A managed or deep-learning
engine plugs in through ``OcrEngine`` without changing the pipeline or the
citation format.
"""

from __future__ import annotations

import logging
import re
from abc import abstractmethod
from collections.abc import Sequence
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.core.exceptions import MediAgentError

logger = logging.getLogger(__name__)

_OSD_ROTATE_PATTERN = re.compile(r"Rotate:\s*(\d+)")


class OcrEngineUnavailableError(MediAgentError):
    """The configured OCR engine cannot run in this environment."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="OCR_ENGINE_UNAVAILABLE")


class OcrWord(BaseModel):
    """One recognized word in raster pixel coordinates."""

    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float = Field(ge=0.0, le=1.0)
    block: int
    paragraph: int
    line: int


class OcrResult(BaseModel):
    words: list[OcrWord] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class OcrEngine(Protocol):
    name: str
    version: str

    @abstractmethod
    def available_languages(self) -> frozenset[str]:
        pass

    @abstractmethod
    def recognize(self, image: Any, *, languages: Sequence[str], timeout_seconds: int) -> OcrResult:
        pass

    @abstractmethod
    def orientation_degrees(self, image: Any) -> int | None:
        pass


class TesseractOcrEngine:
    """Tesseract through ``pytesseract`` with word-level confidence and coordinates."""

    name = "tesseract"

    def __init__(self, tessdata_dir: str | None = None) -> None:
        try:
            import pytesseract  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - dependency is pinned
            raise OcrEngineUnavailableError("pytesseract is not installed") from exc
        self._pytesseract = pytesseract
        self._tessdata_dir = tessdata_dir
        try:
            self.version = str(pytesseract.get_tesseract_version())
        except Exception as exc:
            raise OcrEngineUnavailableError(f"Tesseract binary is not available: {exc}") from exc
        self._languages = self._load_languages()

    def _config(self, *extra: str) -> str:
        parts = list(extra)
        if self._tessdata_dir:
            parts.insert(0, f'--tessdata-dir "{self._tessdata_dir}"')
        return " ".join(parts)

    def _load_languages(self) -> frozenset[str]:
        try:
            return frozenset(self._pytesseract.get_languages(config=self._config()))
        except Exception as exc:  # noqa: BLE001 - language listing is advisory
            logger.warning("Could not list Tesseract languages: %s", exc)
            return frozenset({"eng"})

    def available_languages(self) -> frozenset[str]:
        return self._languages

    def recognize(self, image: Any, *, languages: Sequence[str], timeout_seconds: int) -> OcrResult:
        selected, warnings = self._select_languages(languages)
        data = self._pytesseract.image_to_data(
            image,
            lang="+".join(selected),
            config=self._config("--psm 3"),
            output_type=self._pytesseract.Output.DICT,
            timeout=timeout_seconds,
        )
        return OcrResult(words=_words_from_tsv(data), languages=selected, warnings=warnings)

    def orientation_degrees(self, image: Any) -> int | None:
        """Return the clockwise rotation Tesseract believes will upright the page."""
        if "osd" not in self._languages:
            return None
        try:
            report = self._pytesseract.image_to_osd(image, config=self._config("--psm 0"))
        except Exception:  # noqa: BLE001 - OSD fails on sparse pages; caller falls back
            return None
        match = _OSD_ROTATE_PATTERN.search(str(report))
        return int(match.group(1)) % 360 if match else None

    def _select_languages(self, requested: Sequence[str]) -> tuple[list[str], list[str]]:
        selected = [lang for lang in requested if lang in self._languages]
        warnings: list[str] = []
        missing = [lang for lang in requested if lang not in self._languages]
        if missing:
            warnings.append(
                f"OCR language model(s) not installed: {', '.join(missing)}; "
                f"recognized with {'+'.join(selected) or 'eng'}."
            )
        return selected or ["eng"], warnings


def _words_from_tsv(data: dict[str, list[Any]]) -> list[OcrWord]:
    words: list[OcrWord] = []
    for index, raw_text in enumerate(data.get("text", [])):
        text = str(raw_text).strip()
        confidence = float(data["conf"][index])
        if not text or confidence < 0:
            continue
        words.append(
            OcrWord(
                text=text,
                left=int(data["left"][index]),
                top=int(data["top"][index]),
                width=int(data["width"][index]),
                height=int(data["height"][index]),
                confidence=min(confidence, 100.0) / 100.0,
                block=int(data["block_num"][index]),
                paragraph=int(data["par_num"][index]),
                line=int(data["line_num"][index]),
            )
        )
    return words
