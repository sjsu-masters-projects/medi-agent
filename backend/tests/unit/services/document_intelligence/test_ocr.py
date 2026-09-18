"""Tesseract adapter behaviour with a scripted ``pytesseract`` module."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.document_intelligence.ocr import (
    OcrEngineUnavailableError,
    TesseractOcrEngine,
    _words_from_tsv,
)


def _tsv(*rows: tuple[str, float, int]) -> dict[str, list[Any]]:
    data: dict[str, list[Any]] = {
        key: []
        for key in (
            "text",
            "conf",
            "left",
            "top",
            "width",
            "height",
            "block_num",
            "par_num",
            "line_num",
        )
    }
    for text, conf, line in rows:
        data["text"].append(text)
        data["conf"].append(conf)
        data["left"].append(10)
        data["top"].append(20 * line)
        data["width"].append(50)
        data["height"].append(12)
        data["block_num"].append(1)
        data["par_num"].append(1)
        data["line_num"].append(line)
    return data


def _fake_pytesseract(
    monkeypatch: pytest.MonkeyPatch,
    *,
    languages: list[str] | None = None,
    osd: str = "Rotate: 90\nOrientation confidence: 5.1",
    version: str = "5.5.1",
) -> SimpleNamespace:
    calls: dict[str, Any] = {}

    def image_to_data(image: Any, **kwargs: Any) -> dict[str, list[Any]]:
        calls["image_to_data"] = kwargs
        return _tsv(("Metformin", 96.0, 1), ("500", 91.5, 1), ("", -1.0, 1), ("mg", 40.0, 2))

    def image_to_osd(image: Any, **kwargs: Any) -> str:
        calls["image_to_osd"] = kwargs
        return osd

    module = SimpleNamespace(
        get_tesseract_version=lambda: version,
        get_languages=lambda config="": languages if languages is not None else ["eng", "osd"],
        image_to_data=image_to_data,
        image_to_osd=image_to_osd,
        Output=SimpleNamespace(DICT="dict"),
        calls=calls,
    )
    monkeypatch.setitem(sys.modules, "pytesseract", module)
    return module


def test_missing_binary_raises_a_typed_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom() -> str:
        raise OSError("tesseract is not installed")

    monkeypatch.setitem(sys.modules, "pytesseract", SimpleNamespace(get_tesseract_version=_boom))

    with pytest.raises(OcrEngineUnavailableError, match="not available"):
        TesseractOcrEngine()


def test_recognize_returns_words_with_normalized_confidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _fake_pytesseract(monkeypatch, languages=["eng", "spa", "osd"])
    engine = TesseractOcrEngine(tessdata_dir="/data/tess")

    result = engine.recognize(object(), languages=["eng", "spa"], timeout_seconds=30)

    assert engine.version == "5.5.1"
    assert [word.text for word in result.words] == ["Metformin", "500", "mg"]
    assert result.words[0].confidence == pytest.approx(0.96)
    assert result.words[2].line == 2
    assert result.languages == ["eng", "spa"]
    assert result.warnings == []
    assert fake.calls["image_to_data"]["lang"] == "eng+spa"
    assert '--tessdata-dir "/data/tess"' in fake.calls["image_to_data"]["config"]
    assert fake.calls["image_to_data"]["timeout"] == 30


def test_missing_language_pack_falls_back_with_a_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _fake_pytesseract(monkeypatch, languages=["eng", "osd"])
    engine = TesseractOcrEngine()

    result = engine.recognize(object(), languages=["eng", "spa"], timeout_seconds=10)

    assert result.languages == ["eng"]
    assert result.warnings == ["OCR language model(s) not installed: spa; recognized with eng."]
    assert fake.calls["image_to_data"]["lang"] == "eng"


def test_orientation_is_parsed_from_osd_output(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_pytesseract(monkeypatch, osd="Page number: 0\nRotate: 270\nScript: Latin")
    assert TesseractOcrEngine().orientation_degrees(object()) == 270


def test_orientation_is_none_without_the_osd_model(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_pytesseract(monkeypatch, languages=["eng"])
    assert TesseractOcrEngine().orientation_degrees(object()) is None


def test_orientation_failure_is_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _fake_pytesseract(monkeypatch)

    def _boom(image: Any, **kwargs: Any) -> str:
        raise RuntimeError("Too few characters")

    module.image_to_osd = _boom
    assert TesseractOcrEngine().orientation_degrees(object()) is None


def test_tsv_rows_without_text_or_with_negative_confidence_are_dropped() -> None:
    words = _words_from_tsv(_tsv(("", -1.0, 1), ("   ", 90.0, 1), ("BID", 120.0, 1)))

    assert [word.text for word in words] == ["BID"]
    assert words[0].confidence == 1.0
