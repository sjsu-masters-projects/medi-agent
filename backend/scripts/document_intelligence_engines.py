"""Benchmark-only OCR engines for candidate comparison; none of these ship in the app.

Each class satisfies the ``OcrEngine`` contract used by the extraction pipeline so the
same synthetic corpus and metrics apply to every candidate:

- ``RapidOcrEngine``: PaddleOCR PP-OCRv5 models through RapidOCR (ONNX Runtime, CPU,
  Apache-2.0). Requires ``rapidocr`` and ``onnxruntime`` on ``PYTHONPATH``; they are
  deliberately not in the project lockfile.
- ``NimOcrEngine``: a hosted NVIDIA NIM image-OCR endpoint (PaddleOCR or Nemotron OCR)
  called with the trial key from ``NVIDIA_API_KEY``.
- ``NemotronParseEngine``: hosted Nemotron-Parse, a document parser that returns text
  elements with semantic classes and boxes but no confidence.

Hosted trial endpoints log requests and carry no BAA: synthetic corpus only. Line-level
engines report one confidence per line; words are split proportionally so citations
still get a box, but the split is approximate. Every engine borrows Tesseract's
orientation detector when it is installed, so rotation handling is compared fairly.
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import urllib.request
from collections.abc import Sequence
from typing import Any

from app.services.document_intelligence.ocr import OcrResult, OcrWord

HOSTED_ENDPOINTS: dict[str, str] = {
    "paddleocr": "https://ai.api.nvidia.com/v1/cv/baidu/paddleocr",
    # nemoretriever-ocr-v1 reported end of life on 2026-05-18; nemotron-ocr-v1 replaces it.
    "nemotron-ocr-v1": "https://ai.api.nvidia.com/v1/cv/nvidia/nemotron-ocr-v1",
}
CHAT_COMPLETIONS_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
HOSTED_PAYLOAD_LIMIT_BYTES = 170_000
# Nemotron-Parse reports no per-element confidence; a fixed placeholder keeps the
# pipeline's quality routing usable and is disclosed in every result's warnings.
PARSE_PLACEHOLDER_CONFIDENCE = 0.9

Row = tuple[float, float, float, float, str, float]


def tesseract_orientation(image: Any) -> int | None:
    """Engine-agnostic orientation detection through Tesseract OSD when installed.

    PaddleOCR-family and parser models stay confident on sideways pages, so the
    comparison gives every candidate the same cheap orientation detector.
    """
    try:
        import pytesseract

        report = pytesseract.image_to_osd(image, config="--psm 0")
    except Exception:  # noqa: BLE001 - missing binary or sparse page
        return None
    match = re.search(r"Rotate:\s*(\d+)", str(report))
    return int(match.group(1)) % 360 if match else None


def order_rows(rows: list[Row]) -> list[Row]:
    """Order line fragments top-to-bottom, then left-to-right within one text line.

    Fragments of the same printed line differ by a few pixels in y; sorting on raw y
    would put a right-hand fragment first and scramble the reading order.
    """
    if not rows:
        return []
    heights = sorted(y1 - y0 for (y0, _, _, y1, _, _) in rows)
    line_height = max(4.0, heights[len(heights) // 2])
    return sorted(
        rows, key=lambda row: (round(((row[0] + row[3]) / 2) / (line_height * 0.8)), row[1])
    )


def split_line_into_words(
    text: str,
    box: tuple[float, float, float, float],
    confidence: float,
    line_id: int,
) -> list[OcrWord]:
    """Approximate word boxes inside a line box by character-count proportion."""
    tokens = text.split()
    if not tokens:
        return []
    x0, y0, x1, y1 = box
    total = sum(len(token) for token in tokens) + (len(tokens) - 1)
    width = max(1.0, x1 - x0)
    cursor = x0
    words: list[OcrWord] = []
    for token in tokens:
        span = width * (len(token) / max(1, total))
        words.append(
            OcrWord(
                text=token,
                left=int(cursor),
                top=int(y0),
                width=max(1, int(span)),
                height=max(1, int(y1 - y0)),
                confidence=max(0.0, min(1.0, confidence)),
                block=1,
                paragraph=1,
                line=line_id,
            )
        )
        cursor += span + width / max(1, total)
    return words


def words_from_rows(rows: list[Row]) -> list[OcrWord]:
    words: list[OcrWord] = []
    for line_id, (y0, x0, x1, y1, text, confidence) in enumerate(order_rows(rows), start=1):
        words.extend(split_line_into_words(text, (x0, y0, x1, y1), confidence, line_id))
    return words


class RapidOcrEngine:
    """PaddleOCR PP-OCRv5 through RapidOCR on CPU.

    The mobile detector drops long text lines on 300 dpi pages (CER 0.13 versus 0.00
    on a clean discharge page in this workstream's measurements); the server detector
    with the mobile Latin recognizer read every test page correctly at about 3.6 s per
    page on a laptop CPU, so that is the default here.
    """

    name = "rapidocr"

    def __init__(
        self,
        lang: str = "LATIN",
        version: str = "PPOCRV5",
        *,
        det_model_type: str = "SERVER",
        rec_model_type: str = "MOBILE",
    ):
        import importlib.metadata as metadata

        from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR

        self._ocr = RapidOCR(
            params={
                "Rec.lang_type": getattr(LangRec, lang),
                "Rec.ocr_version": getattr(OCRVersion, version),
                "Rec.model_type": getattr(ModelType, rec_model_type),
                "Det.ocr_version": getattr(OCRVersion, version),
                "Det.model_type": getattr(ModelType, det_model_type),
            }
        )
        self.version = (
            f"{metadata.version('rapidocr')}+{version.lower()}"
            f"-det_{det_model_type.lower()}-rec_{rec_model_type.lower()}-{lang.lower()}"
        )

    def available_languages(self) -> frozenset[str]:
        return frozenset({"eng", "spa"})

    def orientation_degrees(self, image: Any) -> int | None:
        return tesseract_orientation(image)

    def recognize(self, image: Any, *, languages: Sequence[str], timeout_seconds: int) -> OcrResult:
        import numpy as np

        result = self._ocr(np.asarray(image.convert("RGB")))
        boxes = getattr(result, "boxes", None)
        texts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        if boxes is None or texts is None or scores is None:
            return OcrResult(languages=list(languages), warnings=["rapidocr returned no text"])
        rows: list[Row] = []
        for box, text, score in zip(boxes, texts, scores, strict=True):
            xs = [float(p[0]) for p in box]
            ys = [float(p[1]) for p in box]
            rows.append((min(ys), min(xs), max(xs), max(ys), str(text), float(score)))
        return OcrResult(words=words_from_rows(rows), languages=list(languages))


class NimOcrEngine:
    """Hosted NVIDIA NIM image OCR (PaddleOCR or Nemotron OCR v1)."""

    def __init__(self, model: str, *, api_key: str | None = None):
        if model not in HOSTED_ENDPOINTS:
            raise ValueError(f"Unknown hosted OCR model {model!r}")
        self.name = f"nim_{model.replace('-', '_')}"
        self.version = "hosted-trial"
        self.model = model
        self.api_key = api_key or os.environ.get("NVIDIA_API_KEY") or ""
        if not self.api_key:
            raise RuntimeError("NVIDIA_API_KEY is not set")

    def available_languages(self) -> frozenset[str]:
        return frozenset({"eng"})

    def orientation_degrees(self, image: Any) -> int | None:
        return tesseract_orientation(image)

    def recognize(self, image: Any, *, languages: Sequence[str], timeout_seconds: int) -> OcrResult:
        data, scale = _encode_under_limit(image, HOSTED_PAYLOAD_LIMIT_BYTES)
        body = {
            "input": [
                {
                    "type": "image_url",
                    "url": "data:image/jpeg;base64," + base64.b64encode(data).decode(),
                }
            ]
        }
        payload = _post_json(HOSTED_ENDPOINTS[self.model], body, self.api_key, timeout_seconds)
        width, height = image.width, image.height
        rows: list[Row] = []
        for detection in payload.get("data", [{}])[0].get("text_detections", []):
            points = detection.get("bounding_box", {}).get("points", [])
            if not points:
                continue
            xs = [float(p["x"]) * width for p in points]
            ys = [float(p["y"]) * height for p in points]
            prediction = detection.get("text_prediction", {})
            rows.append(
                (
                    min(ys),
                    min(xs),
                    max(xs),
                    max(ys),
                    str(prediction.get("text", "")),
                    float(prediction.get("confidence", 0.0)),
                )
            )
        warnings = (
            []
            if scale == 1.0
            else [f"Image downscaled x{scale:.2f} to fit the hosted payload limit."]
        )
        return OcrResult(words=words_from_rows(rows), languages=["eng"], warnings=warnings)


class NemotronParseEngine:
    """Hosted NVIDIA Nemotron-Parse: element text, semantic class, and box; no confidence."""

    name = "nim_nemotron_parse"
    version = "hosted-trial"

    def __init__(self, api_key: str | None = None, *, render_max_side: int = 1650) -> None:
        self.api_key = api_key or os.environ.get("NVIDIA_API_KEY") or ""
        if not self.api_key:
            raise RuntimeError("NVIDIA_API_KEY is not set")
        self.render_max_side = render_max_side

    def available_languages(self) -> frozenset[str]:
        return frozenset({"eng", "spa"})

    def orientation_degrees(self, image: Any) -> int | None:
        return tesseract_orientation(image)

    def recognize(self, image: Any, *, languages: Sequence[str], timeout_seconds: int) -> OcrResult:
        current = image.convert("L")
        longest = max(current.width, current.height)
        if longest > self.render_max_side:
            factor = self.render_max_side / longest
            current = current.resize((int(current.width * factor), int(current.height * factor)))
        buffer = io.BytesIO()
        current.save(buffer, format="JPEG", quality=75)
        body = {
            "model": "nvidia/nemotron-parse",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/jpeg;base64,"
                                + base64.b64encode(buffer.getvalue()).decode()
                            },
                        }
                    ],
                }
            ],
            "max_tokens": 4000,
            "temperature": 0.0,
        }
        payload = _post_json(CHAT_COMPLETIONS_URL, body, self.api_key, timeout_seconds)
        width, height = image.width, image.height
        rows: list[Row] = []
        for element in _parse_elements(payload):
            bbox = element.get("bbox")
            if not isinstance(bbox, dict):
                continue
            for line_text in str(element.get("text", "")).splitlines():
                rows.append(
                    (
                        float(bbox["ymin"]) * height,
                        float(bbox["xmin"]) * width,
                        float(bbox["xmax"]) * width,
                        float(bbox["ymax"]) * height,
                        line_text,
                        PARSE_PLACEHOLDER_CONFIDENCE,
                    )
                )
        return OcrResult(
            words=words_from_rows(rows),
            languages=["eng", "spa"],
            warnings=["Nemotron-Parse reports no confidence; placeholder 0.90 used."],
        )


def _encode_under_limit(image: Any, limit: int) -> tuple[bytes, float]:
    """JPEG-encode under a payload limit, downscaling by 0.8 steps when necessary."""
    current = image.convert("L")
    scale = 1.0
    data = b""
    for _ in range(6):
        buffer = io.BytesIO()
        current.save(buffer, format="JPEG", quality=80)
        data = buffer.getvalue()
        if len(data) <= limit:
            return data, scale
        current = current.resize((int(current.width * 0.8), int(current.height * 0.8)))
        scale *= 0.8
    return data, scale


def _post_json(url: str, body: dict[str, Any], api_key: str, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return dict(json.loads(response.read().decode()))


def _parse_elements(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Nemotron-Parse returns its elements inside a ``markdown_bbox`` tool call."""
    try:
        message = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return []
    for call in message.get("tool_calls") or []:
        function = call.get("function", {})
        if function.get("name") != "markdown_bbox":
            continue
        try:
            parsed = json.loads(function.get("arguments", "[]"))
        except json.JSONDecodeError:
            return []
        elements: list[dict[str, Any]] = []
        for page in parsed if isinstance(parsed, list) else []:
            if isinstance(page, list):
                elements.extend(item for item in page if isinstance(item, dict))
            elif isinstance(page, dict):
                elements.append(page)
        return elements
    return []
