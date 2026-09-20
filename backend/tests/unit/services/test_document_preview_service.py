import io

import pytest
from PIL import Image

from app.core.exceptions import ValidationError
from app.services.document_preview_service import DocumentPreviewService


def _tiff(*frames: Image.Image) -> bytes:
    output = io.BytesIO()
    frames[0].save(output, format="TIFF", save_all=True, append_images=list(frames[1:]))
    return output.getvalue()


def test_tiff_preview_is_a_pdf_with_one_page_per_frame() -> None:
    source = _tiff(Image.new("RGB", (100, 80), "white"), Image.new("RGB", (100, 80), "black"))

    preview = DocumentPreviewService().create_tiff_pdf_preview(source)

    assert preview.mime_type == "application/pdf"
    assert preview.page_count == 2
    assert preview.content.startswith(b"%PDF")


def test_invalid_tiff_never_returns_a_preview() -> None:
    with pytest.raises(ValidationError, match="could not be decoded safely"):
        DocumentPreviewService().create_tiff_pdf_preview(b"not-a-tiff")
