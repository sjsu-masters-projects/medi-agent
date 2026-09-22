"""Test document service validation — file type and size checks."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from postgrest.exceptions import APIError

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


class TestParseResultSummaryLifecycle:
    """An imported explanation is recorded as ready; a missing one stays owed."""

    def _service(self):
        db = MagicMock()
        table = MagicMock()
        db.table.return_value = table
        for method in ["update", "eq"]:
            getattr(table, method).return_value = table
        return DocumentService(db), table

    def test_supplied_summary_is_not_queued_for_regeneration(self):
        service, table = self._service()

        service.update_parse_result(
            document_id=uuid4(),
            patient_id=uuid4(),
            ai_summary="Imported explanation.",
            parse_status="completed",
            parsed=True,
        )

        assert table.update.call_args.args[0]["summary_status"] == "ready"

    def test_completed_extraction_without_a_summary_still_owes_one(self):
        service, table = self._service()

        service.update_parse_result(
            document_id=uuid4(),
            patient_id=uuid4(),
            ai_summary=None,
            parse_status="completed",
            parsed=True,
        )

        assert table.update.call_args.args[0]["summary_status"] == "pending"

    def test_failed_parse_is_never_owed_an_explanation(self):
        service, table = self._service()

        service.update_parse_result(
            document_id=uuid4(),
            patient_id=uuid4(),
            ai_summary=None,
            parse_status="failed",
            parsed=False,
            parse_failure_code="source_unreadable",
        )

        assert table.update.call_args.args[0]["summary_status"] == "not_required"

    def test_parse_result_survives_a_deploy_before_migration_038(self):
        service, table = self._service()
        table.execute.side_effect = [
            APIError({"code": "PGRST204", "message": "Could not find the 'summary_status' column"}),
            MagicMock(data=None),
        ]

        service.update_parse_result(
            document_id=uuid4(),
            patient_id=uuid4(),
            ai_summary="Imported explanation.",
            parse_status="completed",
            parsed=True,
        )

        retried = table.update.call_args.args[0]
        assert retried["ai_summary"] == "Imported explanation."
        assert "summary_status" not in retried
