"""Test document service validation — file type and size checks."""

from unittest.mock import MagicMock

import pytest

from app.services.document_service import (
    ALLOWED_MIME_TYPES,
    MAX_FILE_SIZE_BYTES,
    DocumentService,
)


class TestFileValidation:
    """Tests for _validate_file — no DB needed."""

    def _make_service(self):
        """Create a service with a None db (we only test validation)."""
        return DocumentService(db=None)  # type: ignore[arg-type]

    def test_accepts_pdf(self):
        svc = self._make_service()
        svc._validate_file("application/pdf", 1024)  # should not raise

    def test_accepts_jpeg(self):
        svc = self._make_service()
        svc._validate_file("image/jpeg", 1024)

    def test_accepts_tiff(self):
        svc = self._make_service()
        svc._validate_file("image/tiff", 1024)

    def test_rejects_executable(self):
        from app.core.exceptions import ValidationError

        svc = self._make_service()
        with pytest.raises(ValidationError, match="not allowed"):
            svc._validate_file("application/x-executable", 1024)

    def test_rejects_html(self):
        from app.core.exceptions import ValidationError

        svc = self._make_service()
        with pytest.raises(ValidationError, match="not allowed"):
            svc._validate_file("text/html", 1024)

    def test_rejects_oversized_file(self):
        from app.core.exceptions import ValidationError

        svc = self._make_service()
        with pytest.raises(ValidationError, match="too large"):
            svc._validate_file("application/pdf", MAX_FILE_SIZE_BYTES + 1)

    def test_accepts_max_size(self):
        svc = self._make_service()
        svc._validate_file("application/pdf", MAX_FILE_SIZE_BYTES)  # boundary

    def test_allowed_mime_types_complete(self):
        """Ensure we haven't accidentally emptied the allowed list."""
        assert len(ALLOWED_MIME_TYPES) == 5
        assert "application/pdf" in ALLOWED_MIME_TYPES
        assert "image/jpeg" in ALLOWED_MIME_TYPES
        assert "image/tiff" in ALLOWED_MIME_TYPES


class TestDocumentViewUrls:
    """Derived previews are separately signed and never become a public URL."""

    def test_ready_preview_gets_a_fresh_signed_url_with_its_source(self):
        db = MagicMock()
        bucket = db.storage.from_.return_value
        bucket.create_signed_url.side_effect = [
            {"signedURL": "https://example.test/source"},
            {"signedURL": "https://example.test/preview"},
        ]
        document = {
            "file_path": "patient/source.tiff",
            "preview_path": "patient/previews/doc/source.pdf",
            "preview_status": "ready",
        }

        DocumentService(db)._attach_view_urls(document)

        assert document["file_url"] == "https://example.test/source"
        assert document["preview_url"] == "https://example.test/preview"
        assert bucket.create_signed_url.call_count == 2

    def test_pending_preview_never_gets_a_url(self):
        db = MagicMock()
        bucket = db.storage.from_.return_value
        bucket.create_signed_url.return_value = {"signedURL": "https://example.test/source"}
        document = {
            "file_path": "patient/source.tiff",
            "preview_path": None,
            "preview_status": "pending",
        }

        DocumentService(db)._attach_view_urls(document)

        assert document["file_url"] == "https://example.test/source"
        assert document["preview_url"] is None
        bucket.create_signed_url.assert_called_once()
