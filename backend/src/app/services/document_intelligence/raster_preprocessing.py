"""Deterministic clean-up of photographed and scanned pages before OCR.

Phone photos differ from flatbed scans in predictable ways: the paper is lit
unevenly, the sheet is a few degrees off square, sensor noise survives JPEG
compression, and the text is small. Each step here addresses one of those and is
a fixed sequence of Pillow operations, so the same upload always produces the same
prepared raster and the work per page is bounded by the image size.

Nothing here judges whether a page is readable; OCR confidence still decides that.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from app.services.document_intelligence.models import DocumentIntelligencePolicy

# Illumination: the paper level is estimated on a reduced copy with a max filter
# wide enough to step over printed rows and table header bands.
_BACKGROUND_TARGET_SIDE = 160
_BACKGROUND_MAX_FILTER = 7
_BACKGROUND_BLUR_RADIUS = 2
# A dark block wider than the filter (a logo, an inverse-video band) must not be
# mistaken for shadowed paper, or its white lettering would be flattened away.
_BACKGROUND_FLOOR_OF_PAPER = 0.35
_PAPER_PERCENTILE = 0.95

# Noise: mean difference between the page and its 3x3 median, in grey levels.
_NOISE_MEDIAN_THRESHOLD = 6.0

# Skew: projection-profile search on a reduced, binarized copy.
_SKEW_TARGET_SIDE = 700
_SKEW_MAX_DEGREES = 10.0
_SKEW_COARSE_STEP = 0.5
_SKEW_FINE_STEP = 0.1
_SKEW_MIN_DEGREES = 0.4
_SKEW_MIN_GAIN = 1.05
_INK_LEVEL = 140

# Soft focus: below this share of solid ink, edges are sharpened before OCR.
_PAPER_LEVEL = 200
_SOLID_INK_LEVEL = 64
_SOFT_FOCUS_SHARPNESS = 0.5
_UNSHARP = {"radius": 2, "percent": 150, "threshold": 0}

# Print size: rows are enlarged toward this height, within a fixed pixel budget.
_TARGET_ROW_HEIGHT_PX = 32
_ROW_HEIGHT_TOLERANCE = 0.85
_ROW_INK_MEAN = 2
_MIN_ROW_PX = 3
_MIN_ROWS = 3
_MAX_UPSCALE = 3.0
_MAX_PREPARED_PIXELS = 24_000_000


@dataclass(frozen=True)
class PreparedRaster:
    """The raster OCR will read and how it relates to the source raster."""

    image: Any
    scale: float = 1.0
    deskew_degrees: float = 0.0
    warnings: list[str] = field(default_factory=list)


def prepare_raster(
    image: Any, policy: DocumentIntelligencePolicy, *, deskew: bool = True
) -> PreparedRaster:
    """Clean the page, straighten it, then enlarge it until its text is OCR-sized."""
    from PIL import Image

    warnings: list[str] = []
    prepared = _clean(image.convert("L"), warnings)
    angle = estimate_skew_degrees(prepared) if deskew else 0.0
    if angle:
        prepared = rotate_with_white_fill(prepared, angle)
        warnings.append(
            f"Page deskewed by {angle:.1f} degrees before OCR; coordinates are in the "
            "straightened frame."
        )
    scale = upscale_factor(prepared, policy.min_raster_side_px)
    if scale > 1:
        prepared = prepared.resize(
            (round(prepared.width * scale), round(prepared.height * scale)),
            Image.Resampling.LANCZOS,
        )
        warnings.append(f"Small print or low-resolution raster upscaled {scale:g}x before OCR.")
    return PreparedRaster(image=prepared, scale=scale, deskew_degrees=angle, warnings=warnings)


def _clean(grayscale: Any, warnings: list[str]) -> Any:
    from PIL import ImageFilter, ImageOps

    cleaned, denoised = _denoise_if_noisy(flatten_illumination(grayscale))
    if denoised:
        warnings.append("Image noise reduced with a median filter before OCR.")
    cleaned = ImageOps.autocontrast(cleaned)
    if ink_sharpness(cleaned) < _SOFT_FOCUS_SHARPNESS:
        cleaned = cleaned.filter(ImageFilter.UnsharpMask(**_UNSHARP))
        warnings.append("Soft-focus image sharpened before OCR.")
    return cleaned


def ink_sharpness(grayscale: Any) -> float:
    """Share of ink pixels that are solid rather than a blurred grey edge."""
    histogram = grayscale.histogram()
    ink = sum(histogram[:_PAPER_LEVEL])
    return sum(histogram[:_SOLID_INK_LEVEL]) / ink if ink else 1.0


def upscale_factor(grayscale: Any, min_side_px: int) -> float:
    """Enlarge small rasters and small print, within a fixed pixel budget.

    Tesseract drops decimal points and confuses 1/l once printed rows are only about
    20 px tall, which is ordinary 10 pt print in a phone photo. The factor is the
    larger of the minimum-side rule and the measured row height, in half steps.
    """
    shortest = min(grayscale.width, grayscale.height)
    side_scale = (
        float(max(2, -(-min_side_px // max(1, shortest)))) if shortest < min_side_px else 1.0
    )
    row_height = estimate_row_height(grayscale)
    text_scale = 1.0
    if row_height and row_height < _TARGET_ROW_HEIGHT_PX * _ROW_HEIGHT_TOLERANCE:
        text_scale = max(1.0, round(2 * _TARGET_ROW_HEIGHT_PX / row_height) / 2)
    scale = min(max(side_scale, text_scale), _MAX_UPSCALE)
    budget = math.sqrt(_MAX_PREPARED_PIXELS / max(1, int(grayscale.width * grayscale.height)))
    return max(1.0, min(scale, math.floor(budget * 2) / 2))


def estimate_row_height(grayscale: Any) -> float | None:
    """Median height of the inked bands in the row profile of an upright page."""
    from PIL import Image

    mask = grayscale.point(lambda value: 255 if value < _INK_LEVEL else 0)
    profile = mask.resize((1, mask.height), Image.Resampling.BOX).tobytes()
    runs: list[int] = []
    current = 0
    for value in [*profile, 0]:
        if value > _ROW_INK_MEAN:
            current += 1
            continue
        if current >= _MIN_ROW_PX:
            runs.append(current)
        current = 0
    if len(runs) < _MIN_ROWS:
        return None
    return float(sorted(runs)[len(runs) // 2])


def flatten_illumination(grayscale: Any) -> Any:
    """Divide by the estimated paper level so shadows and glare stop hiding text."""
    from PIL import ImageMath

    background = _paper_background(grayscale)
    flattened = ImageMath.lambda_eval(
        lambda args: args["page"] * 255.0 / args["paper"],
        page=grayscale.convert("F"),
        paper=background.convert("F"),
    )
    return flattened.convert("L")


def _paper_background(grayscale: Any) -> Any:
    from PIL import Image, ImageFilter

    factor = max(1, min(grayscale.size) // _BACKGROUND_TARGET_SIDE)
    reduced = grayscale.reduce(factor) if factor > 1 else grayscale.copy()
    reduced = reduced.filter(ImageFilter.MaxFilter(_BACKGROUND_MAX_FILTER))
    reduced = reduced.filter(ImageFilter.GaussianBlur(_BACKGROUND_BLUR_RADIUS))
    floor = max(1, round(_percentile(reduced, _PAPER_PERCENTILE) * _BACKGROUND_FLOOR_OF_PAPER))
    reduced = reduced.point(lambda value: max(value, floor))
    return reduced.resize(grayscale.size, Image.Resampling.BILINEAR)


def _percentile(grayscale: Any, fraction: float) -> int:
    histogram = grayscale.histogram()
    target = fraction * sum(histogram)
    running = 0
    for level, count in enumerate(histogram):
        running += count
        if running >= target:
            return level
    return 255


def _denoise_if_noisy(grayscale: Any) -> tuple[Any, bool]:
    """Median-filter only when speckle is measurable; clean text keeps its thin strokes."""
    from PIL import ImageChops, ImageFilter, ImageStat

    smoothed = grayscale.filter(ImageFilter.MedianFilter(3))
    noise = ImageStat.Stat(ImageChops.difference(grayscale, smoothed)).mean[0]
    if noise < _NOISE_MEDIAN_THRESHOLD:
        return grayscale, False
    return smoothed, True


def rotate_with_white_fill(grayscale: Any, degrees: float) -> Any:
    """Rotate counter-clockwise, growing the canvas so no printed corner is cut off."""
    from PIL import Image

    return grayscale.rotate(degrees, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)


def estimate_skew_degrees(grayscale: Any) -> float:
    """The counter-clockwise rotation that makes printed rows horizontal, or 0.

    Text rows produce sharp peaks in the row (or, for a sideways page, column) ink
    profile only when they are aligned with the axis. The search is a fixed grid, so
    its cost does not depend on page content. A correction is returned only when it
    clearly sharpens the profile; ambiguous pages are left untouched.
    """
    ink = _ink_mask(grayscale)
    if ink is None:
        return 0.0
    scores: dict[float, float] = {}

    def rank(angle: float) -> tuple[float, float]:
        if angle not in scores:
            scores[angle] = _profile_score(ink, angle)
        # Ties go to the smaller correction.
        return scores[angle], -abs(angle)

    best = max(_frange(-_SKEW_MAX_DEGREES, _SKEW_MAX_DEGREES, _SKEW_COARSE_STEP), key=rank)
    best = max(
        _frange(best - _SKEW_COARSE_STEP, best + _SKEW_COARSE_STEP, _SKEW_FINE_STEP), key=rank
    )
    if abs(best) < _SKEW_MIN_DEGREES or rank(best)[0] < rank(0.0)[0] * _SKEW_MIN_GAIN:
        return 0.0
    return round(best, 1)


def _ink_mask(grayscale: Any) -> Any | None:
    """A reduced copy where ink is bright, so rotation fills with "no ink"."""
    factor = max(1, max(grayscale.size) // _SKEW_TARGET_SIDE)
    reduced = grayscale.reduce(factor) if factor > 1 else grayscale
    mask = reduced.point(lambda value: 255 if value < _INK_LEVEL else 0)
    return mask if mask.getbbox() else None


def _profile_score(ink: Any, degrees: float) -> float:
    from PIL import Image

    rotated = ink.rotate(degrees, resample=Image.Resampling.NEAREST, expand=True, fillcolor=0)
    # BOX resampling yields per-row and per-column means; scaling back to sums keeps
    # the canvas growth of a rotated copy from biasing the score toward zero degrees.
    rows = rotated.resize((1, rotated.height), Image.Resampling.BOX).tobytes()
    columns = rotated.resize((rotated.width, 1), Image.Resampling.BOX).tobytes()
    row_score = sum(value * value for value in rows) * rotated.width**2
    column_score = sum(value * value for value in columns) * rotated.height**2
    return float(row_score + column_score)


def _frange(start: float, stop: float, step: float) -> list[float]:
    count = round((stop - start) / step)
    return [round(start + index * step, 2) for index in range(count + 1)]
