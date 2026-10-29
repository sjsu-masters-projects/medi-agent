"""Integration tests for Document API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import status

from app.core.security import get_current_user
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser


@pytest.fixture
def patient_id():
    """Fixed patient ID for testing."""
    return uuid4()


@pytest.fixture
def mock_patient_user(patient_id):
    """Mock authenticated patient user."""
    return CurrentUser(id=patient_id, email="patient@test.com", role="patient")


@pytest.fixture
def mock_supabase_db():
    """Mock Supabase client with chainable methods and storage."""
    db = MagicMock()
    table = MagicMock()
    db.table.return_value = table

    # Make all query methods chainable
    for method in ["select", "eq", "single", "insert", "order", "delete", "in_"]:
        getattr(table, method).return_value = table

    runs = MagicMock()
    for method in ["select", "in_", "order"]:
        getattr(runs, method).return_value = runs
    runs.execute.return_value = MagicMock(data=[])
    db.table.side_effect = lambda name=None: runs if name == "document_ingestion_runs" else table

    # Mock storage
    storage = MagicMock()
    bucket = MagicMock()
    bucket.create_signed_url.return_value = {"signedURL": "https://storage.example.com/signed-url"}
    bucket.remove.return_value = []
    storage.from_.return_value = bucket
    db.storage = storage

    return db


@pytest.fixture
def override_auth(mock_patient_user):
    """Override authentication dependency."""

    def _get_current_user_override():
        return mock_patient_user

    app.dependency_overrides[get_current_user] = _get_current_user_override
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def override_db(mock_supabase_db):
    """Override database dependency."""

    def _get_db_override():
        return mock_supabase_db

    app.dependency_overrides[get_db] = _get_db_override
    yield
    app.dependency_overrides.clear()


class TestCreateDocument:
    """POST /api/v1/documents/ - Register uploaded document."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully create document metadata."""
        document_id = uuid4()
        document_data = {
            "id": str(document_id),
            "patient_id": str(patient_id),
            "uploaded_by": str(patient_id),
            "uploaded_by_role": "patient",
            "file_name": "lab-results.pdf",
            "file_url": "https://storage.example.com/signed-url",
            "file_path": f"{patient_id}/lab-results.pdf",
            "file_size_bytes": 1024000,
            "mime_type": "application/pdf",
            "document_type": "lab_report",
            "source_clinic": "Test Clinic",
            "notes": "Annual checkup results",
            "parsed": False,
            "ai_summary": None,
            "parse_status": "pending",
            "parse_error": None,
            "parse_attempts": 0,
            "visibility": "all_providers",
            "created_at": "2025-01-15T00:00:00Z",
        }

        mock_supabase_db.table().insert().execute.return_value = MagicMock(data=[document_data])

        response = client.post(
            "/api/v1/documents/",
            json={
                "file_name": "lab-results.pdf",
                "file_path": f"{patient_id}/lab-results.pdf",
                "file_size_bytes": 1024000,
                "mime_type": "application/pdf",
                "document_type": "lab_report",
                "source_clinic": "Test Clinic",
                "notes": "Annual checkup results",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["file_name"] == "lab-results.pdf"
        assert data["document_type"] == "lab_report"
        assert "file_url" in data
        assert data["parse_status"] == "pending"
        # Registration is request-only; the Cloud Run Job claims this pending row.

    def test_can_defer_background_ingestion_for_verified_extraction(
        self, client, override_auth, override_db, mock_supabase_db, patient_id
    ):
        """Allow a separately verified extraction to defer background parsing."""
        document_id = uuid4()
        document_data = {
            "id": str(document_id),
            "patient_id": str(patient_id),
            "uploaded_by": str(patient_id),
            "uploaded_by_role": "patient",
            "file_name": "discharge-summary.pdf",
            "file_url": "https://storage.example.com/signed-url",
            "file_path": f"{patient_id}/discharge-summary.pdf",
            "file_size_bytes": 1024000,
            "mime_type": "application/pdf",
            "document_type": "discharge_summary",
            "source_clinic": "Patient uploaded document",
            "notes": None,
            "parsed": False,
            "ai_summary": None,
            "parse_status": "pending",
            "parse_error": None,
            "parse_attempts": 0,
            "visibility": "all_providers",
            "created_at": "2025-01-15T00:00:00Z",
        }

        mock_supabase_db.table().insert().execute.return_value = MagicMock(data=[document_data])

        response = client.post(
            "/api/v1/documents/",
            json={
                "document_type": "discharge_summary",
                "file_name": "discharge-summary.pdf",
                "file_path": f"{patient_id}/discharge-summary.pdf",
                "file_size_bytes": 1024000,
                "mime_type": "application/pdf",
                "source_clinic": "Patient uploaded document",
                "start_ingestion": False,
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["file_name"] == "discharge-summary.pdf"
        assert mock_supabase_db.table().insert.call_args.args[0]["parse_status"] == "none"

    def test_invalid_mime_type(self, client, override_auth, override_db):
        """Reject unsupported file type."""
        response = client.post(
            "/api/v1/documents/",
            json={
                "file_name": "document.exe",
                "file_path": "path/to/document.exe",
                "file_size_bytes": 1024,
                "mime_type": "application/x-msdownload",
                "document_type": "other",
            },
        )

        # ValidationError returns 422 for invalid data
        assert response.status_code == 422

    def test_file_too_large(self, client, override_auth, override_db):
        """Reject oversized file."""
        response = client.post(
            "/api/v1/documents/",
            json={
                "file_name": "huge-file.pdf",
                "file_path": "path/to/huge-file.pdf",
                "file_size_bytes": 25 * 1024 * 1024,  # 25 MB
                "mime_type": "application/pdf",
                "document_type": "other",
            },
        )

        # ValidationError returns 422 for invalid data
        assert response.status_code == 422

    def test_missing_required_fields(self, client, override_auth, override_db):
        """Reject request with missing required fields."""
        response = client.post(
            "/api/v1/documents/",
            json={
                "file_name": "test.pdf"
                # Missing file_path, file_size_bytes, mime_type, document_type
            },
        )

        assert response.status_code == 422


class TestListDocuments:
    """GET /api/v1/documents/ - List my documents."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully retrieve document list."""
        documents_data = [
            {
                "id": str(uuid4()),
                "patient_id": str(patient_id),
                "uploaded_by": str(patient_id),
                "uploaded_by_role": "patient",
                "file_name": "lab-results.pdf",
                "file_path": f"{patient_id}/lab-results.pdf",
                "file_url": "https://storage.example.com/signed-url-1",
                "file_size_bytes": 1024000,
                "mime_type": "application/pdf",
                "document_type": "lab_report",
                "source_clinic": None,
                "parsed": False,
                "ai_summary": None,
                "parse_status": "pending",
                "parse_error": None,
                "parse_attempts": 1,
                "visibility": "all_providers",
                "created_at": "2025-01-15T00:00:00Z",
            },
            {
                "id": str(uuid4()),
                "patient_id": str(patient_id),
                "uploaded_by": str(patient_id),
                "uploaded_by_role": "patient",
                "file_name": "prescription.pdf",
                "file_path": f"{patient_id}/prescription.pdf",
                "file_url": "https://storage.example.com/signed-url-2",
                "file_size_bytes": 512000,
                "mime_type": "application/pdf",
                "document_type": "prescription",
                "source_clinic": "Test Clinic",
                "parsed": True,
                "ai_summary": "Prescription for medication X",
                "parse_status": "completed",
                "parse_error": None,
                "parse_attempts": 1,
                "visibility": "all_providers",
                "created_at": "2025-01-14T00:00:00Z",
            },
        ]

        mock_supabase_db.table().select().eq().order().execute.return_value = MagicMock(
            data=documents_data
        )

        response = client.get("/api/v1/documents/")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["file_name"] == "lab-results.pdf"

    def test_empty_list(self, client, override_auth, override_db, mock_supabase_db):
        """Handle empty document list."""
        mock_supabase_db.table().select().eq().order().execute.return_value = MagicMock(data=[])

        response = client.get("/api/v1/documents/")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0


class TestGetDocument:
    """GET /api/v1/documents/{document_id} - Get document detail."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully retrieve document detail."""
        document_id = uuid4()
        document_data = {
            "id": str(document_id),
            "patient_id": str(patient_id),
            "uploaded_by": str(patient_id),
            "uploaded_by_role": "patient",
            "file_name": "lab-results.pdf",
            "file_path": f"{patient_id}/lab-results.pdf",
            "file_url": "https://storage.example.com/signed-url",
            "file_size_bytes": 1024000,
            "mime_type": "application/pdf",
            "document_type": "lab_report",
            "source_clinic": None,
            "parsed": False,
            "ai_summary": None,
            "parse_status": "processing",
            "parse_error": None,
            "parse_attempts": 1,
            "visibility": "all_providers",
            "created_at": "2025-01-15T00:00:00Z",
        }

        mock_supabase_db.table().select().eq().eq().single().execute.return_value = MagicMock(
            data=document_data
        )

        response = client.get(f"/api/v1/documents/{document_id}")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["file_name"] == "lab-results.pdf"
        assert "file_url" in data

    def test_not_found(self, client, override_auth, override_db, mock_supabase_db):
        """Handle document not found."""
        document_id = uuid4()

        mock_supabase_db.table().select().eq().eq().single().execute.return_value = MagicMock(
            data=None
        )

        response = client.get(f"/api/v1/documents/{document_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_wrong_patient(self, client, override_auth, override_db, mock_supabase_db):
        """Reject access to another patient's document."""
        document_id = uuid4()

        mock_supabase_db.table().select().eq().eq().single().execute.return_value = MagicMock(
            data=None  # Query filters by patient_id, so returns None
        )

        response = client.get(f"/api/v1/documents/{document_id}")

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestDeleteDocument:
    """The owned-removal transaction is authoritative, including replay and refusal."""

    def test_success_cleans_storage_only_after_atomic_removal(
        self, client, override_auth, override_db, mock_supabase_db, patient_id
    ):
        document_id = uuid4()
        file_path = f"{patient_id}/synthetic.pdf"
        mock_supabase_db.rpc().execute.return_value = MagicMock(
            data={"removed": True, "file_path": file_path}
        )
        response = client.delete(f"/api/v1/documents/{document_id}")
        assert response.status_code == 204
        mock_supabase_db.rpc.assert_any_call(
            "remove_patient_document_upload",
            {
                "p_document_id": str(document_id),
                "p_patient_id": str(patient_id),
                "p_actor_id": str(patient_id),
            },
        )
        mock_supabase_db.storage.from_().remove.assert_called_once_with([file_path])
        mock_supabase_db.table().delete.assert_not_called()

    @pytest.mark.parametrize(
        "code,http_status", [("42501", 409), ("P0002", 404), ("PGRST202", 503), ("40001", 409)]
    )
    def test_refusal_or_missing_migration_never_falls_back_to_legacy_withdrawal(
        self, client, override_auth, override_db, mock_supabase_db, code, http_status
    ):
        from postgrest.exceptions import APIError

        mock_supabase_db.rpc().execute.side_effect = APIError(
            {"code": code, "message": "private database detail"}
        )
        response = client.delete(f"/api/v1/documents/{uuid4()}")
        assert response.status_code == http_status
        assert "private database detail" not in response.text
        mock_supabase_db.storage.from_().remove.assert_not_called()
        assert all(
            call.args[0] != "withdraw_unapplied_document_source"
            for call in mock_supabase_db.rpc.call_args_list
            if call.args
        )

    def test_successful_replay_does_not_repeat_storage_cleanup(
        self, client, override_auth, override_db, mock_supabase_db
    ):
        mock_supabase_db.rpc().execute.return_value = MagicMock(
            data={"removed": True, "replayed": True}
        )
        assert client.delete(f"/api/v1/documents/{uuid4()}").status_code == 204
        mock_supabase_db.storage.from_().remove.assert_not_called()

    def test_invalid_storage_path_never_deletes_another_patients_object(
        self, client, override_auth, override_db, mock_supabase_db
    ):
        mock_supabase_db.rpc().execute.return_value = MagicMock(
            data={"removed": True, "file_path": "another-patient/source.pdf"}
        )
        assert client.delete(f"/api/v1/documents/{uuid4()}").status_code == 204
        mock_supabase_db.storage.from_().remove.assert_not_called()

    def test_eligibility_comes_from_the_same_database_contract(
        self, client, override_auth, override_db, mock_supabase_db
    ):
        mock_supabase_db.rpc().execute.return_value = MagicMock(
            data={"can_remove": False, "reason": "reviewed"}
        )
        response = client.get(f"/api/v1/documents/{uuid4()}/removal")
        assert response.status_code == 200
        assert response.json() == {"can_remove": False, "reason": "reviewed"}

    def test_clinician_cannot_use_patient_removal_route(
        self, client, override_db, mock_supabase_db
    ):
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            id=uuid4(), email="c@example.test", role="clinician"
        )
        try:
            assert client.delete(f"/api/v1/documents/{uuid4()}").status_code == 403
            assert client.get(f"/api/v1/documents/{uuid4()}/removal").status_code == 403
            mock_supabase_db.rpc.assert_not_called()
        finally:
            app.dependency_overrides.clear()


class TestExplainDocument:
    """POST /api/v1/documents/{document_id}/explain - Explain a document."""

    @pytest.mark.parametrize("locale", ["en-US", "es-MX"])
    @pytest.mark.parametrize("reused", [False, True])
    def test_structured_presentation_uses_authorized_source(
        self, client, override_auth, locale, reused
    ):
        from app.services.explanation_service import StructuredExplanation

        document_id = uuid4()
        source = {"parse_status": "completed", "ai_summary": "Metformina 500 mg."}
        presentation = StructuredExplanation.model_validate(
            {
                "language": locale,
                "sections": [{"kind": "medicines", "items": ["Metformina 500 mg."]}],
            }
        )
        with (
            patch(
                "app.routers.documents.DocumentService.get_document",
                new=AsyncMock(return_value=source),
            ) as read,
            patch(
                "app.routers.documents.DocumentPresentationService.read_or_present",
                new=AsyncMock(return_value=(presentation, reused)),
            ) as present,
        ):
            response = client.post(
                f"/api/v1/documents/{document_id}/explain",
                json={"language": locale, "structured": True},
            )
        assert response.status_code == 200
        assert response.json()["sections"] == [
            {"kind": "medicines", "items": ["Metformina 500 mg."]}
        ]
        assert response.json()["language"] == locale
        assert response.json()["summary"] == presentation.plain_text()
        read.assert_awaited_once()
        present.assert_awaited_once_with(document_id, source["ai_summary"], locale)
        assert response.json()["cached"] is reused
        assert source == {"parse_status": "completed", "ai_summary": "Metformina 500 mg."}

    def test_failed_presentation_never_returns_wrong_language_cache(self, client, override_auth):
        with (
            patch(
                "app.routers.documents.DocumentService.get_document",
                new=AsyncMock(return_value={"ai_summary": "Resumen antiguo en español."}),
            ),
            patch(
                "app.routers.documents.DocumentPresentationService.read_or_present",
                new=AsyncMock(side_effect=ValueError("private source text")),
            ),
        ):
            response = client.post(
                f"/api/v1/documents/{uuid4()}/explain",
                json={"language": "en-US", "structured": True},
            )
        assert response.status_code == 200
        assert response.json()["available"] is False
        assert response.json()["summary"] is None
        assert "Resumen" not in response.text
        assert "private source" not in response.text

    @pytest.mark.parametrize(
        "document",
        [
            {"parse_status": "duplicate", "ai_summary": "stale"},
            {"summary_status": "pending", "ai_summary": None},
        ],
    )
    def test_unavailable_source_skips_structured_provider(self, client, override_auth, document):
        with (
            patch(
                "app.routers.documents.DocumentService.get_document",
                new=AsyncMock(return_value=document),
            ),
            patch(
                "app.routers.documents.DocumentPresentationService.read_or_present", new=AsyncMock()
            ) as present,
        ):
            response = client.post(
                f"/api/v1/documents/{uuid4()}/explain", json={"structured": True}
            )
        assert response.json()["available"] is False
        present.assert_not_awaited()

    def test_structured_explanation_does_not_call_provider_before_authorization(
        self, client, override_auth
    ):
        from app.core.exceptions import NotFoundError

        with (
            patch(
                "app.routers.documents.DocumentService.get_document",
                new=AsyncMock(side_effect=NotFoundError("Document", "synthetic")),
            ),
            patch(
                "app.routers.documents.DocumentPresentationService.read_or_present", new=AsyncMock()
            ) as present,
        ):
            response = client.post(
                f"/api/v1/documents/{uuid4()}/explain", json={"structured": True}
            )
        assert response.status_code == 404
        present.assert_not_awaited()

    @pytest.mark.parametrize(
        ("language", "message"),
        [("en-US", "These exact file contents"), ("es-MX", "Este mismo archivo")],
    )
    def test_duplicate_explanation_does_not_use_cache_or_model(
        self, client, override_auth, language, message
    ):
        document_id = uuid4()
        with (
            patch(
                "app.services.document_service.DocumentService.get_document",
                new=AsyncMock(return_value={"parse_status": "duplicate", "ai_summary": "stale"}),
            ),
            patch(
                "app.routers.documents.ExplanationService.translate", new=AsyncMock()
            ) as translate,
        ):
            response = client.post(
                f"/api/v1/documents/{document_id}/explain", json={"language": language}
            )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["summary_status"] == "duplicate"
        assert response.json()["available"] is False
        assert response.json()["summary"] is None
        assert message in response.json()["message"]
        translate.assert_not_awaited()

    def test_returns_cached_english_summary(
        self, client, override_auth, override_db, mock_supabase_db, patient_id
    ):
        """English explanation returns cached ai_summary without LLM call."""
        document_id = uuid4()
        mock_supabase_db.table().select().eq().eq().single().execute.return_value = MagicMock(
            data={
                "id": str(document_id),
                "patient_id": str(patient_id),
                "uploaded_by": str(patient_id),
                "uploaded_by_role": "patient",
                "file_name": "lab-results.pdf",
                "file_path": f"{patient_id}/lab-results.pdf",
                "file_url": "https://storage.example.com/signed-url",
                "file_size_bytes": 1024000,
                "mime_type": "application/pdf",
                "document_type": "lab_report",
                "source_clinic": None,
                "parsed": True,
                "ai_summary": "**Cached** summary",
                "parse_status": "completed",
                "parse_error": None,
                "parse_attempts": 1,
                "visibility": "all_providers",
                "created_at": "2025-01-15T00:00:00Z",
            }
        )

        response = client.post(
            f"/api/v1/documents/{document_id}/explain",
            json={"language": "en"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["summary"] == "Cached summary"
        assert data["cached"] is True

    def test_translates_summary(
        self, client, override_auth, override_db, mock_supabase_db, patient_id
    ):
        """Non-English explanation uses the explanation service."""
        document_id = uuid4()
        mock_supabase_db.table().select().eq().eq().single().execute.return_value = MagicMock(
            data={
                "id": str(document_id),
                "patient_id": str(patient_id),
                "uploaded_by": str(patient_id),
                "uploaded_by_role": "patient",
                "file_name": "lab-results.pdf",
                "file_path": f"{patient_id}/lab-results.pdf",
                "file_url": "https://storage.example.com/signed-url",
                "file_size_bytes": 1024000,
                "mime_type": "application/pdf",
                "document_type": "lab_report",
                "source_clinic": None,
                "parsed": True,
                "ai_summary": "English summary",
                "parse_status": "completed",
                "parse_error": None,
                "parse_attempts": 1,
                "visibility": "all_providers",
                "created_at": "2025-01-15T00:00:00Z",
            }
        )

        with patch(
            "app.routers.documents.ExplanationService.translate",
            new=AsyncMock(return_value="Resumen en español"),
        ) as mock_translate:
            response = client.post(
                f"/api/v1/documents/{document_id}/explain",
                json={"language": "es"},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["summary"] == "Resumen en español"
        assert data["available"] is True
        assert data["cached"] is False
        mock_translate.assert_awaited_once()

    def _document_without_summary(self, document_id, patient_id, **overrides):
        """A document whose clinical result is complete but whose explanation is not."""
        document = {
            "id": str(document_id),
            "patient_id": str(patient_id),
            "uploaded_by": str(patient_id),
            "uploaded_by_role": "patient",
            "file_name": "lab-results.pdf",
            "file_path": f"{patient_id}/lab-results.pdf",
            "file_url": "https://storage.example.com/signed-url",
            "file_size_bytes": 1024000,
            "mime_type": "application/pdf",
            "document_type": "lab_report",
            "source_clinic": None,
            "parsed": True,
            "ai_summary": None,
            "parse_status": "completed",
            "parse_error": None,
            "parse_attempts": 1,
            "visibility": "all_providers",
            "created_at": "2025-01-15T00:00:00Z",
        }
        document.update(overrides)
        return document

    def test_unavailable_explanation_reports_its_operational_reason(
        self, client, override_auth, override_db, mock_supabase_db, patient_id
    ):
        """A provider outage is named, not rendered as an empty card."""
        document_id = uuid4()
        mock_supabase_db.table().select().eq().eq().single().execute.return_value = MagicMock(
            data=self._document_without_summary(
                document_id,
                patient_id,
                summary_status="failed",
                summary_failure_code="provider_unavailable",
            )
        )

        with patch(
            "app.routers.documents.ExplanationService.translate", new=AsyncMock()
        ) as mock_translate:
            response = client.post(
                f"/api/v1/documents/{document_id}/explain",
                json={"language": "en"},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["available"] is False
        assert data["summary"] is None
        assert data["summary_status"] == "failed"
        assert data["failure_code"] == "provider_unavailable"
        assert "not available right now" in data["message"]
        # The request path never generates a replacement explanation.
        mock_translate.assert_not_awaited()

    def test_owed_explanation_says_it_is_still_being_prepared(
        self, client, override_auth, override_db, mock_supabase_db, patient_id
    ):
        document_id = uuid4()
        mock_supabase_db.table().select().eq().eq().single().execute.return_value = MagicMock(
            data=self._document_without_summary(document_id, patient_id, summary_status="pending")
        )

        response = client.post(
            f"/api/v1/documents/{document_id}/explain",
            json={"language": "es"},
        )

        data = response.json()
        assert data["available"] is False
        assert data["summary_status"] == "pending"
        assert data["language"] == "es-MX"
        # The reason reaches the patient in their own locale.
        assert "todavía se está preparando" in data["message"]

    def test_document_with_nothing_to_explain_is_not_reported_as_a_failure(
        self, client, override_auth, override_db, mock_supabase_db, patient_id
    ):
        document_id = uuid4()
        mock_supabase_db.table().select().eq().eq().single().execute.return_value = MagicMock(
            data=self._document_without_summary(
                document_id, patient_id, summary_status="not_required"
            )
        )

        response = client.post(f"/api/v1/documents/{document_id}/explain", json={"language": "en"})

        data = response.json()
        assert data["available"] is False
        assert data["summary_status"] == "not_required"
        assert data["failure_code"] is None
        assert "no extracted information" in data["message"]

    def test_pre_migration_document_falls_back_to_its_parse_state(
        self, client, override_auth, override_db, mock_supabase_db, patient_id
    ):
        """Migration 038 is applied after this image deploys; reads must still work."""
        document = self._document_without_summary(document_id := uuid4(), patient_id)
        document.pop("ai_summary")
        mock_supabase_db.table().select().eq().eq().single().execute.return_value = MagicMock(
            data=document
        )

        response = client.post(f"/api/v1/documents/{document_id}/explain", json={"language": "en"})

        assert response.status_code == status.HTTP_200_OK
        # A completed extraction still owes an explanation, so it reads as pending.
        assert response.json()["summary_status"] == "pending"

    def test_translation_outage_is_reported_rather_than_replaced_with_prose(
        self, client, override_auth, override_db, mock_supabase_db, patient_id
    ):
        document_id = uuid4()
        mock_supabase_db.table().select().eq().eq().single().execute.return_value = MagicMock(
            data=self._document_without_summary(
                document_id,
                patient_id,
                ai_summary="English summary",
                summary_status="ready",
            )
        )

        with patch(
            "app.routers.documents.ExplanationService.translate",
            new=AsyncMock(side_effect=RuntimeError("provider down")),
        ):
            response = client.post(
                f"/api/v1/documents/{document_id}/explain",
                json={"language": "es"},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["available"] is False
        assert data["summary"] is None
        assert data["failure_code"] == "provider_unavailable"


class TestAuthorization:
    """Test authorization requirements."""

    def test_no_auth_header(self, client):
        """Reject request without authorization header."""
        response = client.get("/api/v1/documents/")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_token(self, client):
        """Reject request with invalid token."""
        response = client.get(
            "/api/v1/documents/", headers={"Authorization": "Bearer invalid-token"}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
