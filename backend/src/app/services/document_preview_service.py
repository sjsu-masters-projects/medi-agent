"""Safe, bounded preview generation for non-browser clinical source formats."""

from __future__ import annotations

import io
import warnings
from dataclasses import dataclass

from app.core.exceptions import ValidationError

MAX_PREVIEW_FRAMES = 50
MAX_PREVIEW_PIXELS = 40_000_000
MAX_PREVIEW_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class DocumentPreview:
    """A derived, non-authoritative representation of an original source artifact."""

    content: bytes
    mime_type: str
    page_count: int


class DocumentPreviewService:
    """Generate previews only for formats the browser cannot render reliably."""

    def create_tiff_pdf_preview(self, content: bytes) -> DocumentPreview:
        """Render a TIFF's frames as a bounded PDF preview.

        The original TIFF remains the source of record. This preview makes the
        same visual pages available to both portals without trusting browser TIFF
        support or sending a clinical document to a third-party conversion service.
        """
        import pymupdf
        from PIL import Image, ImageSequence

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                image = Image.open(io.BytesIO(content))
        except Exception as exc:  # noqa: BLE001 - decoder errors are client-visible only as state
            raise ValidationError("TIFF preview could not be decoded safely") from exc

        document = pymupdf.open()  # type: ignore[no-untyped-call]  # PyMuPDF stub is incomplete.
        total_pixels = 0
        page_count = 0
        try:
            for page_count, frame in enumerate(ImageSequence.Iterator(image), start=1):
                if page_count > MAX_PREVIEW_FRAMES:
                    raise ValidationError("TIFF has too many pages for an inline preview")
                total_pixels += frame.width * frame.height
                if total_pixels > MAX_PREVIEW_PIXELS:
                    raise ValidationError("TIFF is too large for an inline preview")

                rendered = frame.convert("RGB")
                rendered_bytes = io.BytesIO()
                rendered.save(rendered_bytes, format="JPEG", quality=95, optimize=True)
                page = document.new_page(width=rendered.width, height=rendered.height)
                page.insert_image(  # type: ignore[no-untyped-call]  # PyMuPDF stub is incomplete.
                    page.rect, stream=rendered_bytes.getvalue()
                )

            if page_count == 0:
                raise ValidationError("TIFF has no renderable pages")
            pdf = document.tobytes(  # type: ignore[no-untyped-call]  # PyMuPDF stub is incomplete.
                garbage=4, deflate=True
            )
            if len(pdf) > MAX_PREVIEW_BYTES:
                raise ValidationError("TIFF preview exceeds the document size limit")
            return DocumentPreview(
                content=pdf,
                mime_type="application/pdf",
                page_count=page_count,
            )
        except ValidationError:
            raise
        except Exception as exc:  # noqa: BLE001 - library errors must not escape the worker boundary
            raise ValidationError("TIFF preview could not be rendered safely") from exc
        finally:
            document.close()  # type: ignore[no-untyped-call]  # PyMuPDF stub is incomplete.
            image.close()
