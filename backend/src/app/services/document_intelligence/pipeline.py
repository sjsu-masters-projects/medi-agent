"""Deterministic extraction pipeline: classify, read embedded text, OCR only when needed.

The pipeline never calls a language model. Its output is a versioned
``DocumentExtraction`` that records page class, method, words with coordinates,
confidence, quality, and a routing decision the caller must respect.
"""

from __future__ import annotations

import hashlib
import io
import logging
import time
from typing import Any

from app.services.document_intelligence.classification import (
    PageSignals,
    classify_page,
    embedded_text_sanity,
    sniff_container,
)
from app.services.document_intelligence.embedded_text import (
    EmbeddedPageText,
    extract_embedded_page,
)
from app.services.document_intelligence.models import (
    BoundingBox,
    DocumentClass,
    DocumentExtraction,
    DocumentIntelligencePolicy,
    ExtractionMethod,
    ExtractionRoute,
    FailureKind,
    PageClass,
    PageExtraction,
    PageQuality,
    TextLine,
    WordBox,
)
from app.services.document_intelligence.ocr import (
    OcrEngine,
    OcrEngineUnavailableError,
    OcrResult,
    TesseractOcrEngine,
)

logger = logging.getLogger(__name__)

EXTRACTOR_NAME = "document-intelligence"
EXTRACTOR_REVISION = 1
_POINTS_PER_INCH = 72.0
_DARK_PIXEL_THRESHOLD = 200
_ROTATION_CANDIDATES = (90, 180, 270)
_OSD_SCORE_TOLERANCE = 0.05
_MAX_PARSER_WARNINGS = 3
_ENGINE_MISSING = "OCR engine is unavailable in this environment."


class DocumentIntelligenceService:
    """Classify a source file and extract text with page/region evidence."""

    def __init__(
        self,
        *,
        ocr_engine: OcrEngine | None = None,
        policy: DocumentIntelligencePolicy | None = None,
    ) -> None:
        self.policy = policy or DocumentIntelligencePolicy()
        self._ocr_engine = ocr_engine
        self._ocr_probe_failed = False

    # ── Public API ───────────────────────────────────────

    def extract(
        self, content: bytes, *, mime_type: str, file_name: str | None = None
    ) -> DocumentExtraction:
        started = time.perf_counter()
        source_sha256 = hashlib.sha256(content).hexdigest()
        container = sniff_container(content, mime_type)
        repaired = False
        if container == "pdf":
            document_class, pages, warnings, repaired = self._extract_pdf(content)
        elif container == "image":
            document_class, pages, warnings = self._extract_raster(content)
        elif container == "corrupt":
            document_class, pages, warnings = (
                DocumentClass.UNREADABLE,
                [],
                [f"File bytes do not match the declared MIME type {mime_type!r}."],
            )
        else:
            document_class, pages, warnings = (
                DocumentClass.UNSUPPORTED,
                [],
                [f"Unsupported container for MIME type {mime_type!r}."],
            )
        route, reason, failure = self._route(document_class, pages, repaired=repaired)
        return DocumentExtraction(
            document_class=document_class,
            mime_type=mime_type,
            file_name=file_name,
            source_sha256=source_sha256,
            page_count=len(pages),
            pages=pages,
            route=route,
            route_reason=reason,
            failure_kind=failure,
            repaired=repaired,
            extractor_version=self.extractor_version,
            engine_versions=self.engine_versions,
            languages_requested=list(self.policy.languages),
            warnings=warnings,
            latency_ms=_elapsed_ms(started),
        )

    @property
    def extractor_version(self) -> str:
        parts = [f"{EXTRACTOR_NAME}/{EXTRACTOR_REVISION}"]
        parts.extend(f"{name}/{version}" for name, version in sorted(self.engine_versions.items()))
        return ";".join(parts)

    @property
    def engine_versions(self) -> dict[str, str]:
        versions: dict[str, str] = {}
        try:
            import pymupdf  # type: ignore[import-untyped]

            versions["pymupdf"] = str(pymupdf.version[0])
        except Exception:  # noqa: BLE001 - version is informational
            logger.debug("PyMuPDF version unavailable")
        engine = self._ocr_engine
        if engine is not None:
            versions[engine.name] = engine.version
        return versions

    # ── OCR engine ───────────────────────────────────────

    def _engine(self) -> OcrEngine | None:
        if not self.policy.ocr_enabled or self._ocr_probe_failed:
            return None
        if self._ocr_engine is None:
            try:
                self._ocr_engine = TesseractOcrEngine()
            except OcrEngineUnavailableError as exc:
                logger.warning("OCR engine unavailable: %s", exc.message)
                self._ocr_probe_failed = True
                return None
        return self._ocr_engine

    # ── PDF ──────────────────────────────────────────────

    def _extract_pdf(
        self, content: bytes
    ) -> tuple[DocumentClass, list[PageExtraction], list[str], bool]:
        import pymupdf  # type: ignore[import-untyped]

        pymupdf.TOOLS.mupdf_display_errors(False)  # type: ignore[no-untyped-call]
        pymupdf.TOOLS.mupdf_warnings(reset=True)  # type: ignore[no-untyped-call]
        try:
            document = pymupdf.open(  # type: ignore[no-untyped-call]
                stream=content, filetype="pdf"
            )
        except Exception as exc:  # noqa: BLE001 - any parser failure is "unreadable"
            return DocumentClass.UNREADABLE, [], [f"PDF could not be opened: {exc}"], False
        repaired = bool(getattr(document, "is_repaired", False))
        try:
            if document.needs_pass:
                return DocumentClass.ENCRYPTED, [], ["PDF is password protected."], repaired
            warnings: list[str] = []
            if repaired:
                warnings.append(
                    "PDF structure was repaired on open; content may be incomplete and the "
                    "document requires clinician review against the original file."
                )
            page_numbers = range(min(document.page_count, self.policy.max_pages))
            if document.page_count > self.policy.max_pages:
                warnings.append(
                    f"Only the first {self.policy.max_pages} of {document.page_count} pages "
                    "were processed; the remainder requires clinician review."
                )
            pages = [self._process_pdf_page(document[index], index + 1) for index in page_numbers]
        except Exception as exc:  # noqa: BLE001 - corrupt page trees surface here
            return DocumentClass.UNREADABLE, [], [f"PDF pages could not be read: {exc}"], repaired
        finally:
            document.close()  # type: ignore[no-untyped-call]
        warnings.extend(
            _parser_warnings(pymupdf.TOOLS.mupdf_warnings(reset=True))  # type: ignore[no-untyped-call]
        )
        if not pages:
            return DocumentClass.BLANK, [], ["PDF contains no pages."], repaired
        return _document_class_for(pages), pages, warnings, repaired

    def _process_pdf_page(self, page: Any, page_number: int) -> PageExtraction:
        started = time.perf_counter()
        text = page.get_text()
        image_rects = _image_rects(page)
        signals = PageSignals(
            text_chars=len(text.strip()),
            text_sanity=embedded_text_sanity(text),
            image_coverage=_coverage(image_rects, page),
            ink_ratio=None if text.strip() or image_rects else self._ink_ratio(page),
        )
        page_class, warnings = classify_page(signals, self.policy)
        base = PageExtraction(
            page_number=page_number,
            page_class=page_class,
            method=ExtractionMethod.NONE,
            width=float(page.rect.width),
            height=float(page.rect.height),
            source_rotation=int(page.rotation),
            warnings=warnings,
        )
        if page_class is PageClass.BLANK:
            return base.model_copy(update={"latency_ms": _elapsed_ms(started)})
        if page_class is PageClass.BORN_DIGITAL_TEXT:
            return self._finish_embedded(base, extract_embedded_page(page), started)
        if page_class is PageClass.MIXED:
            regions = [
                self._ocr_pdf_region(page, base, rect)
                for rect in image_rects
                if _coverage([rect], page) >= self.policy.min_region_coverage
            ]
            return _merge_mixed(base, extract_embedded_page(page), regions, self.policy, started)
        return self._ocr_pdf_page(page, base, started)

    def _finish_embedded(
        self, base: PageExtraction, embedded: EmbeddedPageText, started: float
    ) -> PageExtraction:
        return base.model_copy(
            update={
                "method": ExtractionMethod.EMBEDDED_TEXT,
                "words": embedded.words,
                "lines": embedded.lines,
                "tables": embedded.tables,
                "text": embedded.text,
                "confidence": 1.0 if embedded.words else 0.0,
                "quality": self.policy.page_quality(1.0, has_words=bool(embedded.words)),
                "latency_ms": _elapsed_ms(started),
            }
        )

    def _ocr_pdf_page(self, page: Any, base: PageExtraction, started: float) -> PageExtraction:
        """Render the whole page, skip it when it holds no ink, otherwise OCR it."""
        dpi = self.policy.render_dpi
        image = self._render(page, dpi, clip=None)
        if _ink_ratio_of(image) < self.policy.blank_ink_ratio:
            return base.model_copy(
                update={
                    "page_class": PageClass.BLANK,
                    "warnings": [*base.warnings, "Image page contains no visible ink."],
                    "latency_ms": _elapsed_ms(started),
                }
            )
        prepared = base.model_copy(update={"render_dpi": dpi})
        return self._ocr_raster_image(image, prepared, _POINTS_PER_INCH / dpi, started)

    def _ocr_pdf_region(self, page: Any, base: PageExtraction, rect: Any) -> PageExtraction:
        """OCR one embedded image region of a text page, keeping page coordinates."""
        started = time.perf_counter()
        dpi = self.policy.render_dpi
        image = self._render(page, dpi, clip=rect)
        region = base.model_copy(update={"render_dpi": dpi, "warnings": []})
        return self._ocr_raster_image(
            image,
            region,
            _POINTS_PER_INCH / dpi,
            started,
            origin=(float(rect.x0), float(rect.y0)),
            allow_rotation=False,
        )

    def _render(self, page: Any, dpi: int, *, clip: Any) -> Any:
        """Grayscale render: a 300 dpi letter page is ~8 MB instead of ~25 MB in RGB."""
        import pymupdf
        from PIL import Image

        pixmap = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, clip=clip)
        return Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("L")

    def _ink_ratio(self, page: Any) -> float:
        return _ink_ratio_of(self._render(page, 50, clip=None))

    # ── Raster images ────────────────────────────────────

    def _extract_raster(
        self, content: bytes
    ) -> tuple[DocumentClass, list[PageExtraction], list[str]]:
        from PIL import Image, ImageSequence

        try:
            image = Image.open(io.BytesIO(content))
            frames = [frame.copy() for frame in ImageSequence.Iterator(image)]
        except Exception as exc:  # noqa: BLE001 - decoder failures are "unreadable"
            return DocumentClass.UNREADABLE, [], [f"Image could not be decoded: {exc}"]
        if not frames:
            return DocumentClass.UNREADABLE, [], ["Image contains no frames."]
        pages = [
            self._process_raster_frame(frame, index + 1)
            for index, frame in enumerate(frames[: self.policy.max_pages])
        ]
        return _document_class_for(pages), pages, []

    def _process_raster_frame(self, frame: Any, page_number: int) -> PageExtraction:
        started = time.perf_counter()
        grayscale = frame.convert("L")
        base = PageExtraction(
            page_number=page_number,
            page_class=PageClass.SCANNED_IMAGE,
            method=ExtractionMethod.NONE,
            coordinate_unit="px",
            width=float(grayscale.width),
            height=float(grayscale.height),
        )
        if _ink_ratio_of(grayscale) < self.policy.blank_ink_ratio:
            return base.model_copy(
                update={"page_class": PageClass.BLANK, "latency_ms": _elapsed_ms(started)}
            )
        return self._ocr_raster_image(grayscale, base, 1.0, started)

    # ── OCR of a raster page ─────────────────────────────

    def _ocr_raster_image(
        self,
        image: Any,
        base: PageExtraction,
        scale: float,
        started: float,
        *,
        origin: tuple[float, float] = (0.0, 0.0),
        allow_rotation: bool = True,
    ) -> PageExtraction:
        engine = self._engine()
        if engine is None:
            reason = (
                "OCR is disabled by policy." if not self.policy.ocr_enabled else _ENGINE_MISSING
            )
            return base.model_copy(
                update={
                    "method": ExtractionMethod.OCR,
                    "quality": PageQuality.UNUSABLE,
                    "warnings": [*base.warnings, reason],
                    "latency_ms": _elapsed_ms(started),
                }
            )
        prepared, prep_scale, prep_warnings = _prepare_raster(image, self.policy)
        if allow_rotation:
            rotation, result, rotation_warnings = self._recognize_upright(engine, prepared)
        else:
            rotation, result, rotation_warnings = 0, self._recognize(engine, prepared), []
        page_width, page_height = base.width, base.height
        if rotation in (90, 270):
            page_width, page_height = page_height, page_width
        words, lines = _words_and_lines(result, scale / prep_scale, origin)
        confidence = _mean_confidence(words)
        return base.model_copy(
            update={
                "method": ExtractionMethod.OCR,
                "width": page_width,
                "height": page_height,
                "rotation_applied": rotation,
                "languages": result.languages,
                "words": words,
                "lines": lines,
                "text": "\n".join(line.text for line in lines),
                "confidence": confidence,
                "quality": self.policy.page_quality(confidence, has_words=bool(words)),
                "warnings": [*base.warnings, *prep_warnings, *rotation_warnings, *result.warnings],
                "latency_ms": _elapsed_ms(started),
            }
        )

    def _recognize_upright(self, engine: OcrEngine, image: Any) -> tuple[int, OcrResult, list[str]]:
        """Recognize the page as-is, then accept a rotation only when it reads better.

        Orientation detection is cheap but misfires on short labels, so its suggestion is
        verified against the unrotated pass. A brute-force search over the remaining
        rotations runs only when the best result is still poor, so an upright page never
        pays for four OCR passes.
        """
        warnings: list[str] = []
        best_rotation, best_result = 0, self._recognize(engine, image)
        best_score = _mean_confidence_of_result(best_result)
        tried = {0}
        suggested = engine.orientation_degrees(image) or 0
        if suggested:
            tried.add(suggested)
            result = self._recognize(engine, image.rotate(-suggested, expand=True))
            score = _mean_confidence_of_result(result)
            # Some engines stay confident on sideways text, so the detector's suggestion
            # wins unless the upright pass is clearly better or reads more characters.
            if score >= best_score - _OSD_SCORE_TOLERANCE and _chars(result) >= _chars(best_result):
                best_rotation, best_result, best_score = suggested, result, score
                warnings.append(f"Page orientation corrected by {suggested} degrees (OSD).")
        if best_score < self.policy.rotation_search_below:
            for degrees in _ROTATION_CANDIDATES:
                if degrees in tried:
                    continue
                result = self._recognize(engine, image.rotate(-degrees, expand=True))
                score = _mean_confidence_of_result(result)
                if score > best_score:
                    best_rotation, best_result, best_score = degrees, result, score
            if best_rotation not in (0, suggested):
                warnings.append(
                    f"Page orientation corrected by {best_rotation} degrees (confidence search)."
                )
        return best_rotation, best_result, warnings

    def _recognize(self, engine: OcrEngine, image: Any) -> OcrResult:
        try:
            return engine.recognize(
                image,
                languages=self.policy.languages,
                timeout_seconds=self.policy.ocr_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - engine crash or timeout is a page failure
            logger.warning("OCR failed on a page: %s", type(exc).__name__)
            return OcrResult(warnings=[f"OCR failed: {type(exc).__name__}"])

    # ── Routing ──────────────────────────────────────────

    def _route(
        self, document_class: DocumentClass, pages: list[PageExtraction], *, repaired: bool
    ) -> tuple[ExtractionRoute, str, FailureKind]:
        if document_class in (
            DocumentClass.ENCRYPTED,
            DocumentClass.UNREADABLE,
            DocumentClass.UNSUPPORTED,
        ):
            return ExtractionRoute.REJECTED, document_class.value, FailureKind.PERMANENT
        content = [page for page in pages if page.page_class is not PageClass.BLANK]
        if not content:
            return ExtractionRoute.REJECTED, "blank_document", FailureKind.PERMANENT
        qualities = {page.quality for page in content}
        engine_missing = any(
            _ENGINE_MISSING in warning for page in content for warning in page.warnings
        )
        if qualities <= {PageQuality.UNUSABLE, PageQuality.EMPTY}:
            failure = FailureKind.TRANSIENT if engine_missing else FailureKind.NONE
            return ExtractionRoute.CLINICIAN_ONLY, "no_usable_page_text", failure
        if repaired:
            return ExtractionRoute.REVIEW_WITH_CAUTION, "pdf_repaired", FailureKind.NONE
        if qualities == {PageQuality.USABLE}:
            return ExtractionRoute.AUTOMATED_CANDIDATES, "all_pages_usable", FailureKind.NONE
        return ExtractionRoute.REVIEW_WITH_CAUTION, "low_quality_pages_present", FailureKind.NONE


# ── Helpers ──────────────────────────────────────────────


def _elapsed_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _parser_warnings(text: str) -> list[str]:
    distinct: list[str] = []
    for line in str(text or "").splitlines():
        line = line.strip()
        if line and line not in distinct:
            distinct.append(line)
    if not distinct:
        return []
    shown = "; ".join(distinct[:_MAX_PARSER_WARNINGS])
    more = (
        f" (+{len(distinct) - _MAX_PARSER_WARNINGS} more)"
        if len(distinct) > _MAX_PARSER_WARNINGS
        else ""
    )
    return [f"PDF parser reported: {shown}{more}"]


def _document_class_for(pages: list[PageExtraction]) -> DocumentClass:
    classes = {page.page_class for page in pages if page.page_class is not PageClass.BLANK}
    if not classes:
        return DocumentClass.BLANK
    if classes == {PageClass.BORN_DIGITAL_TEXT}:
        return DocumentClass.BORN_DIGITAL_TEXT
    if classes == {PageClass.SCANNED_IMAGE}:
        return DocumentClass.SCANNED_IMAGE
    return DocumentClass.MIXED


def _image_rects(page: Any) -> list[Any]:
    rects: list[Any] = []
    for info in page.get_images(full=True):
        try:
            rects.extend(page.get_image_rects(info[0]))
        except Exception:  # noqa: BLE001 - orphaned xref
            continue
    return [rect for rect in rects if rect.width > 0 and rect.height > 0]


def _coverage(rects: list[Any], page: Any) -> float:
    page_area = float(page.rect.width * page.rect.height)
    if page_area <= 0:
        return 0.0
    covered = sum(float(rect.width * rect.height) for rect in rects)
    return min(1.0, covered / page_area)


def _ink_ratio_of(grayscale: Any) -> float:
    histogram = grayscale.histogram()
    total = sum(histogram)
    if not total:
        return 0.0
    return float(sum(histogram[:_DARK_PIXEL_THRESHOLD]) / total)


def _prepare_raster(image: Any, policy: DocumentIntelligencePolicy) -> tuple[Any, float, list[str]]:
    """Grayscale, contrast-stretch, and upscale small rasters before OCR."""
    from PIL import Image, ImageOps

    prepared = ImageOps.autocontrast(image.convert("L"))
    scale = 1.0
    warnings: list[str] = []
    shortest = min(prepared.width, prepared.height)
    if shortest < policy.min_raster_side_px:
        scale = float(max(2, -(-policy.min_raster_side_px // max(1, shortest))))
        prepared = prepared.resize(
            (int(prepared.width * scale), int(prepared.height * scale)),
            Image.Resampling.LANCZOS,
        )
        warnings.append(f"Low-resolution raster upscaled {scale:.0f}x before OCR.")
    return prepared, scale, warnings


def _words_and_lines(
    result: OcrResult, scale: float, origin: tuple[float, float]
) -> tuple[list[WordBox], list[TextLine]]:
    words: list[WordBox] = []
    lines: list[TextLine] = []
    grouped: dict[tuple[int, int, int], list[Any]] = {}
    for word in result.words:
        grouped.setdefault((word.block, word.paragraph, word.line), []).append(word)
    for key in sorted(grouped):
        line_words = sorted(grouped[key], key=lambda w: w.left)
        line_id = len(lines)
        boxes = [
            WordBox(
                text=word.text,
                bbox=BoundingBox(
                    x0=origin[0] + word.left * scale,
                    y0=origin[1] + word.top * scale,
                    x1=origin[0] + (word.left + word.width) * scale,
                    y1=origin[1] + (word.top + word.height) * scale,
                ),
                confidence=word.confidence,
                line_id=line_id,
                method=ExtractionMethod.OCR,
            )
            for word in line_words
        ]
        bbox = boxes[0].bbox
        for box in boxes[1:]:
            bbox = bbox.union(box.bbox)
        words.extend(boxes)
        lines.append(
            TextLine(
                line_id=line_id,
                text=" ".join(box.text for box in boxes),
                bbox=bbox,
                confidence=_mean_confidence(boxes),
            )
        )
    return words, lines


def _mean_confidence(words: list[WordBox]) -> float:
    """Character-weighted mean so a long garbled token counts more than a stray dot."""
    weights = [(len(word.text), word.confidence) for word in words]
    total = sum(length for length, _ in weights)
    if not total:
        return 0.0
    return round(sum(length * conf for length, conf in weights) / total, 4)


def _chars(result: OcrResult) -> int:
    return sum(len(word.text) for word in result.words)


def _mean_confidence_of_result(result: OcrResult) -> float:
    total = sum(len(word.text) for word in result.words)
    if not total:
        return 0.0
    return sum(len(word.text) * word.confidence for word in result.words) / total


def _merge_mixed(
    base: PageExtraction,
    embedded: EmbeddedPageText,
    regions: list[PageExtraction],
    policy: DocumentIntelligencePolicy,
    started: float,
) -> PageExtraction:
    """Keep every embedded word, then append OCR words from each image region."""
    words = list(embedded.words)
    lines = list(embedded.lines)
    warnings = list(base.warnings)
    languages: list[str] = []
    for region in regions:
        offset = len(lines)
        for word in region.words:
            if any(word.bbox.overlap_ratio(existing.bbox) > 0.5 for existing in embedded.words):
                continue
            words.append(word.model_copy(update={"line_id": word.line_id + offset}))
        kept = {word.line_id - offset for word in words[len(embedded.words) :]}
        lines.extend(
            line.model_copy(update={"line_id": line.line_id + offset})
            for line in region.lines
            if line.line_id in kept
        )
        warnings.extend(region.warnings)
        languages = region.languages or languages
    ocr_added = len(words) > len(embedded.words)
    confidence = _mean_confidence(words)
    return base.model_copy(
        update={
            "method": ExtractionMethod.OCR if ocr_added else ExtractionMethod.EMBEDDED_TEXT,
            "render_dpi": regions[0].render_dpi if regions else None,
            "languages": languages,
            "words": words,
            "lines": lines,
            "tables": embedded.tables,
            "text": "\n".join(line.text for line in lines),
            "confidence": confidence,
            "quality": policy.page_quality(confidence, has_words=bool(words)),
            "warnings": warnings,
            "latency_ms": _elapsed_ms(started),
        }
    )
