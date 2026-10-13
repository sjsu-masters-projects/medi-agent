"""Synthetic phone-photo and scan degradations of a synthetic lab report.

Every image is generated in memory from vector text, so no binary fixture is
committed and nothing here resembles a real patient's document. Each degradation
is deterministic (fixed parameters, seeded noise) so a test failure is reproducible.
"""

from __future__ import annotations

import io
from collections.abc import Callable

import numpy as np
import pymupdf
from PIL import Image, ImageFilter

RENDER_DPI = 200
# Cells are separate spans, as on a real report, so each row is a layout test too.
LAB_ROWS = (
    ("Hemoglobin A1c", "7.8", "H", "%", "4.0 - 5.6"),
    ("Sodium", "139", "", "mmol/L", "136 - 145"),
    ("Potassium", "4.2", "", "mmol/L", "3.5 - 5.1"),
    ("Glucosa en ayunas", "146", "H", "mg/dL", "70 - 99"),
)
LAB_COLUMNS = (40, 260, 330, 370, 450)
# The printed row each recovered value must stay on.
EXPECTED_ROW_VALUES = {"Hemoglobin": "7.8", "Sodium": "139", "Glucosa": "146"}
EXPECTED_PHRASES = ("Metformin 500 mg",)


def lab_report_pdf() -> bytes:
    """One synthetic report page: inverse header band, result table, medication list."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    dark = (0.15, 0.15, 0.15)
    page.draw_rect(pymupdf.Rect(36, 46, 400, 66), color=dark, fill=dark)
    page.insert_text(
        (40, 60), "SYNTHETIC TEST DOCUMENT - LABORATORY REPORT", fontsize=11, color=(1, 1, 1)
    )
    page.insert_text((40, 80), "Collected 10/12/2026 07:45 PT", fontsize=9)
    for index, row in enumerate(LAB_ROWS):
        y = 120 + index * 18
        for x, cell in zip(LAB_COLUMNS, row, strict=True):
            if cell:
                page.insert_text((x, y), cell, fontsize=10)
    page.insert_text((40, 220), "Medications", fontsize=10)
    page.insert_text((40, 240), "Metformin 500 mg twice daily", fontsize=10)
    page.insert_text((40, 258), "Lisinopril 10 mg once daily", fontsize=10)
    content = bytes(doc.tobytes())
    doc.close()
    return content


def lab_report_image(dpi: int = RENDER_DPI) -> Image.Image:
    """The report as a clean grayscale scan."""
    doc = pymupdf.open(stream=lab_report_pdf(), filetype="pdf")
    pixmap = doc[0].get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    image = Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("L")
    doc.close()
    return image


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def jpeg_bytes(image: Image.Image, quality: int) -> bytes:
    buffer = io.BytesIO()
    image.convert("L").save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


# ── Degradations ─────────────────────────────────────────


def rotate(image: Image.Image, degrees: float) -> Image.Image:
    """Counter-clockwise rotation on a white, growing canvas (a tilted sheet)."""
    return image.rotate(degrees, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)


def keystone(image: Image.Image, inset: float = 0.06) -> Image.Image:
    """Perspective of a phone held below the sheet: the top edge is narrower."""
    width, height = image.size
    source = [(0, 0), (width, 0), (width, height), (0, height)]
    target = [
        (width * inset, 0),
        (width * (1 - inset), height * 0.02),
        (width, height),
        (0, height),
    ]
    rows: list[list[float]] = []
    values: list[float] = []
    for (x, y), (u, v) in zip(target, source, strict=True):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        values.extend([u, v])
    coefficients = np.linalg.solve(np.array(rows, dtype=float), np.array(values, dtype=float))
    return image.transform(
        image.size,
        Image.Transform.PERSPECTIVE,
        tuple(float(c) for c in coefficients),
        Image.Resampling.BICUBIC,
        fillcolor=255,
    )


def jpeg(image: Image.Image, quality: int = 15) -> Image.Image:
    return Image.open(io.BytesIO(jpeg_bytes(image, quality))).convert("L")


def blur(image: Image.Image, radius: float = 1.5) -> Image.Image:
    return image.filter(ImageFilter.GaussianBlur(radius))


def uneven_lighting(image: Image.Image) -> Image.Image:
    """A shadow falling across the left of the sheet and a lamp glare at upper right."""
    width, height = image.size
    pixels = np.asarray(image, dtype=np.float32)
    shade = np.linspace(0.45, 1.0, width)[None, :] * np.linspace(1.0, 0.85, height)[:, None]
    columns = (np.arange(width)[None, :] - width * 0.7) / (width * 0.15)
    lines = (np.arange(height)[:, None] - height * 0.25) / (height * 0.12)
    glare = 90.0 * np.exp(-(columns**2 + lines**2))
    return Image.fromarray(np.clip(pixels * shade + glare, 0, 255).astype(np.uint8))


def dim_low_contrast(image: Image.Image) -> Image.Image:
    """A dark room: ink at grey 95 on paper at grey 150."""
    pixels = np.asarray(image, dtype=np.float32)
    return Image.fromarray((95 + pixels * (150 - 95) / 255).astype(np.uint8))


def sensor_noise(image: Image.Image, sigma: float = 25.0, seed: int = 7) -> Image.Image:
    rng = np.random.default_rng(seed)
    pixels = np.asarray(image, dtype=np.float32) + rng.normal(0, sigma, (image.height, image.width))
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8))


def low_resolution(image: Image.Image, width: int = 800) -> Image.Image:
    height = round(image.height * width / image.width)
    return image.resize((width, height), Image.Resampling.BILINEAR)


def phone_photo(image: Image.Image) -> Image.Image:
    """Several mild faults at once, as a quick photo in a doctor's office produces."""
    tilted = rotate(keystone(image, 0.04), 4)
    return jpeg(sensor_noise(uneven_lighting(tilted), sigma=12), quality=35)


def heavy_blur(image: Image.Image) -> Image.Image:
    return image.filter(ImageFilter.GaussianBlur(8))


def thumbnail(image: Image.Image) -> Image.Image:
    return low_resolution(image, 250).filter(ImageFilter.GaussianBlur(1.5))


Degradation = Callable[[Image.Image], Image.Image]

READABLE_DEGRADATIONS: dict[str, Degradation] = {
    "clean": lambda image: image,
    "tilt_4_degrees": lambda image: rotate(image, 4),
    "tilt_minus_7_degrees": lambda image: rotate(image, -7),
    "sideways_90": lambda image: rotate(image, 90),
    "sideways_270": lambda image: rotate(image, 270),
    "keystone": keystone,
    "jpeg_quality_15": jpeg,
    "slight_blur": blur,
    "uneven_lighting_and_glare": uneven_lighting,
    "dim_low_contrast": dim_low_contrast,
    "sensor_noise": sensor_noise,
    "low_resolution_800px": low_resolution,
    "phone_photo_combined": phone_photo,
}

UNREADABLE_DEGRADATIONS: dict[str, Degradation] = {
    "heavy_blur": heavy_blur,
    "thumbnail_250px": thumbnail,
}
