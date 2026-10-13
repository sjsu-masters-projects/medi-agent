"""Pre-OCR raster clean-up, measured on synthetic pages without an OCR engine."""

from __future__ import annotations

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageStat

from app.services.document_intelligence import DocumentIntelligencePolicy
from app.services.document_intelligence.raster_preprocessing import (
    estimate_row_height,
    estimate_skew_degrees,
    flatten_illumination,
    ink_sharpness,
    prepare_raster,
    upscale_factor,
)
from tests.unit.services.document_intelligence.phone_photo_fixtures import (
    blur,
    lab_report_image,
    rotate,
    sensor_noise,
    uneven_lighting,
)

POLICY = DocumentIntelligencePolicy()


@pytest.fixture(scope="module")
def report() -> Image.Image:
    return lab_report_image()


def _mean(image: Image.Image, box: tuple[int, int, int, int]) -> float:
    return float(ImageStat.Stat(image.crop(box)).mean[0])


def _striped(width: int, height: int, *, row: int, pitch: int) -> Image.Image:
    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    for top in range(pitch, height - pitch, pitch):
        draw.rectangle((width // 10, top, width - width // 10, top + row), fill=0)
    return image


@pytest.mark.parametrize("tilt", [-8.0, -3.0, 4.0, 7.0])
def test_skew_estimate_recovers_the_tilt_of_a_photographed_sheet(report, tilt: float) -> None:
    assert estimate_skew_degrees(rotate(report, tilt)) == pytest.approx(-tilt, abs=0.3)


def test_skew_estimate_also_works_on_a_sideways_sheet(report) -> None:
    assert estimate_skew_degrees(rotate(rotate(report, 90), 5)) == pytest.approx(-5, abs=0.3)


def test_upright_and_blank_pages_are_not_rotated(report) -> None:
    assert estimate_skew_degrees(report) == 0.0
    assert estimate_skew_degrees(Image.new("L", (1200, 1600), 255)) == 0.0


def test_flattening_evens_out_a_shadow_without_erasing_inverse_text(report) -> None:
    shaded = uneven_lighting(report)
    flattened = flatten_illumination(shaded)

    # Bare paper in the shadowed left margin and the lit right margin.
    left, right = (5, 1500, 60, 2100), (1640, 1500, 1695, 2100)
    assert _mean(shaded, right) - _mean(shaded, left) > 60
    assert abs(_mean(flattened, right) - _mean(flattened, left)) < 15
    # The dark header band behind white lettering stays dark rather than becoming paper.
    header_band = (110, 135, 1100, 180)
    assert _mean(flattened, header_band) < 128


def test_flattening_leaves_an_evenly_lit_scan_unchanged(report) -> None:
    difference = ImageChops.difference(report, flatten_illumination(report))
    # Only the edge of the dark header band is lightened slightly; paper and text are not.
    assert ImageStat.Stat(difference).mean[0] < 0.5
    assert difference.getextrema()[1] <= 20


def test_noise_and_soft_focus_are_treated_only_when_measured(report) -> None:
    clean = prepare_raster(report, POLICY)
    noisy = prepare_raster(sensor_noise(report), POLICY)
    soft = prepare_raster(blur(report, 2.0), POLICY)

    assert not any("noise" in w or "sharpened" in w for w in clean.warnings)
    assert any("noise reduced" in warning for warning in noisy.warnings)
    assert any("sharpened" in warning for warning in soft.warnings)
    assert ink_sharpness(Image.new("L", (10, 10), 255)) == 1.0


def test_small_print_is_enlarged_toward_ocr_size(report) -> None:
    row_height = estimate_row_height(report)

    assert row_height is not None and row_height < 28
    assert upscale_factor(report, POLICY.min_raster_side_px) == 1.5
    assert upscale_factor(_striped(2400, 3000, row=34, pitch=70), 1000) == 1.0


def test_enlargement_respects_the_pixel_budget() -> None:
    tiny_print_large_page = _striped(5000, 6000, row=8, pitch=24)

    assert upscale_factor(tiny_print_large_page, 1000) == 1.0
    assert upscale_factor(_striped(400, 500, row=6, pitch=20), 1000) == 3.0


def test_row_height_needs_several_printed_rows() -> None:
    assert estimate_row_height(_striped(800, 300, row=10, pitch=120)) is None


def test_preparation_is_deterministic_and_reports_the_straightening(report) -> None:
    tilted = rotate(report, -6)

    first, second = prepare_raster(tilted, POLICY), prepare_raster(tilted, POLICY)

    assert first.image.tobytes() == second.image.tobytes()
    assert first.deskew_degrees == pytest.approx(6.0, abs=0.3)
    assert first.scale == 1.5
    assert any("deskewed" in warning for warning in first.warnings)


def test_embedded_regions_are_never_straightened(report) -> None:
    prepared = prepare_raster(rotate(report, 5), POLICY, deskew=False)

    assert prepared.deskew_degrees == 0.0
    assert not any("deskewed" in warning for warning in prepared.warnings)
