"""Integration tests for Patient API endpoints.

Uses FastAPI dependency overrides for proper authentication mocking.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import status

from app.core import exception_handlers
from app.core.exceptions import NotFoundError, ValidationError
from app.core.security import get_current_user
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser
from app.routers.patients import _get_service


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
    """Mock Supabase client with chainable methods."""
    db = MagicMock()
    table = MagicMock()
    db.table.return_value = table

    # Make all query methods chainable
    for method in ["select", "eq", "single", "update", "insert", "is_", "order", "gte"]:
        getattr(table, method).return_value = table

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


@pytest.fixture
def override_patient_service():
    """Override the patient service for focused route-contract tests."""
    service = MagicMock()
    app.dependency_overrides[_get_service] = lambda: service
    yield service
    app.dependency_overrides.pop(_get_service, None)


class TestGetMyProfile:
    """GET /api/v1/patients/me - Get patient profile."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully retrieve patient profile."""
        profile_data = {
            "id": str(patient_id),
            "email": "patient@test.com",
            "first_name": "John",
            "last_name": "Doe",
            "date_of_birth": "1990-01-15",
            "gender": "male",
            "preferred_language": "en",
            "phone": "+1234567890",
            "avatar_url": None,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": None,
        }

        mock_supabase_db.table().select().eq().single().execute.return_value = MagicMock(
            data=profile_data
        )

        response = client.get("/api/v1/patients/me")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["email"] == "patient@test.com"
        assert data["first_name"] == "John"
        assert data["last_name"] == "Doe"

    def test_not_found(self, client, override_auth, override_db, mock_supabase_db):
        """Handle patient not found."""
        mock_supabase_db.table().select().eq().single().execute.return_value = MagicMock(data=None)

        response = client.get("/api/v1/patients/me")

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TestUpdateMyProfile:
    """PUT /api/v1/patients/me - Update patient profile."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully update patient profile."""
        updated_data = {
            "id": str(patient_id),
            "email": "patient@test.com",
            "first_name": "Jane",
            "last_name": "Doe",
            "date_of_birth": "1990-01-15",
            "gender": "male",
            "preferred_language": "en",
            "phone": "+9876543210",
            "avatar_url": None,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-15T00:00:00Z",
        }

        mock_supabase_db.table().update().eq().execute.return_value = MagicMock(data=[updated_data])

        response = client.put(
            "/api/v1/patients/me", json={"first_name": "Jane", "phone": "+9876543210"}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["first_name"] == "Jane"
        assert data["phone"] == "+9876543210"

    def test_partial_update(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Update only specific fields."""
        updated_data = {
            "id": str(patient_id),
            "email": "patient@test.com",
            "first_name": "John",
            "last_name": "Doe",
            "date_of_birth": "1990-01-15",
            "gender": "male",
            "preferred_language": "es",
            "phone": None,
            "avatar_url": None,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-15T00:00:00Z",
        }

        mock_supabase_db.table().update().eq().execute.return_value = MagicMock(data=[updated_data])

        response = client.put("/api/v1/patients/me", json={"preferred_language": "es"})

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["preferred_language"] == "es-MX"

    def test_invalid_gender(self, client, override_auth, override_db):
        """Reject invalid gender value."""
        response = client.put("/api/v1/patients/me", json={"gender": "invalid_gender"})

        assert response.status_code == 422


def _profile_row(patient_id, **overrides):
    row = {
        "id": str(patient_id),
        "email": "patient@test.com",
        "first_name": "Morgan",
        "last_name": "Lee",
        "date_of_birth": "1958-03-02",
        "gender": "female",
        "preferred_language": "en-US",
        "phone": None,
        "avatar_url": None,
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-15T00:00:00Z",
    }
    row.update(overrides)
    return row


class TestUpdateMyProfileGender:
    """PUT /api/v1/patients/me - optional gender can be set and cleared."""

    @pytest.fixture
    def table(self, mock_supabase_db):
        table = MagicMock()
        mock_supabase_db.table.return_value = table
        for method in ["select", "eq", "single", "update"]:
            getattr(table, method).return_value = table
        return table

    def test_explicit_null_clears_gender(
        self, client, override_auth, override_db, table, patient_id
    ):
        table.execute.return_value = MagicMock(data=[_profile_row(patient_id, gender=None)])

        response = client.put(
            "/api/v1/patients/me",
            json={
                "first_name": "Morgan",
                "last_name": "Lee",
                "preferred_language": "en-US",
                "gender": None,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        table.update.assert_called_once_with(
            {
                "first_name": "Morgan",
                "last_name": "Lee",
                "preferred_language": "en-US",
                "gender": None,
            }
        )
        assert response.json()["gender"] is None

    def test_omitted_gender_is_left_unchanged(
        self, client, override_auth, override_db, table, patient_id
    ):
        table.execute.return_value = MagicMock(data=[_profile_row(patient_id)])

        response = client.put("/api/v1/patients/me", json={"first_name": "Morgan"})

        assert response.status_code == status.HTTP_200_OK
        table.update.assert_called_once_with({"first_name": "Morgan"})
        assert response.json()["gender"] == "female"

    def test_prefer_not_to_say_persists(
        self, client, override_auth, override_db, table, patient_id
    ):
        table.execute.return_value = MagicMock(
            data=[_profile_row(patient_id, gender="prefer_not_to_say")]
        )

        response = client.put("/api/v1/patients/me", json={"gender": "prefer_not_to_say"})

        assert response.status_code == status.HTTP_200_OK
        table.update.assert_called_once_with({"gender": "prefer_not_to_say"})
        assert response.json()["gender"] == "prefer_not_to_say"

    def test_null_required_fields_are_still_ignored(
        self, client, override_auth, override_db, table, patient_id
    ):
        table.execute.return_value = MagicMock(data=[_profile_row(patient_id, gender=None)])

        response = client.put(
            "/api/v1/patients/me",
            json={
                "first_name": None,
                "last_name": None,
                "preferred_language": None,
                "gender": None,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        table.update.assert_called_once_with({"gender": None})
        assert response.json()["first_name"] == "Morgan"

    def test_only_null_required_fields_is_a_no_op(
        self, client, override_auth, override_db, table, patient_id
    ):
        table.execute.return_value = MagicMock(data=_profile_row(patient_id))

        response = client.put("/api/v1/patients/me", json={"first_name": None})

        assert response.status_code == status.HTTP_200_OK
        table.update.assert_not_called()
        assert response.json()["first_name"] == "Morgan"


class TestGetMyCareTeam:
    """GET /api/v1/patients/me/care-team - List care team."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db):
        """Successfully retrieve care team."""
        care_team_data = [
            {
                "id": str(uuid4()),
                "patient_id": str(uuid4()),
                "clinician_id": str(uuid4()),
                "status": "active",
                "role": "provider",
                "created_at": "2025-01-01T00:00:00Z",
                "clinicians": {
                    "first_name": "Dr. Sarah",
                    "last_name": "Smith",
                    "specialty": "Cardiology",
                    "clinic_name": "Heart Health Clinic",
                },
            }
        ]

        mock_supabase_db.table().select().eq().eq().execute.return_value = MagicMock(
            data=care_team_data
        )

        response = client.get("/api/v1/patients/me/care-team")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1

    def test_empty_care_team(self, client, override_auth, override_db, mock_supabase_db):
        """Handle empty care team."""
        mock_supabase_db.table().select().eq().eq().execute.return_value = MagicMock(data=[])

        response = client.get("/api/v1/patients/me/care-team")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0


class TestJoinClinic:
    """POST /api/v1/patients/me/care-team/join - Join clinic via invite code."""

    def test_success(self, client, override_auth, override_db, mock_supabase_db, patient_id):
        """Successfully join clinic with valid invite code."""
        care_team_id = uuid4()
        clinician_id = uuid4()

        invite_data = {
            "id": str(care_team_id),
            "clinician_id": str(clinician_id),
            "invite_code": "ABC123",
            "status": "pending",
            "patient_id": None,
            "role": "provider",
            "created_at": "2025-01-01T00:00:00Z",
            "invite_expires_at": "2099-01-01T00:00:00+00:00",
        }

        updated_data = {
            "id": str(care_team_id),
            "patient_id": str(patient_id),
            "clinician_id": str(clinician_id),
            "role": "provider",
            "status": "active",
            "created_at": "2025-01-01T00:00:00Z",
            "invite_claimed_at": "2026-04-10T00:00:00+00:00",
        }

        joined_data = {
            "id": str(care_team_id),
            "patient_id": str(patient_id),
            "clinician_id": str(clinician_id),
            "role": "provider",
            "status": "active",
            "created_at": "2025-01-01T00:00:00Z",
            "clinicians": {
                "first_name": "Dr. Sarah",
                "last_name": "Smith",
                "specialty": "Cardiology",
                "clinic_name": "Heart Health Clinic",
            },
        }

        table_mock = MagicMock()
        mock_supabase_db.table.return_value = table_mock

        invite_select = MagicMock()
        invite_select.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=invite_data
        )

        existing_select = MagicMock()
        existing_select.eq.return_value.eq.return_value.eq.return_value.execute.return_value = (
            MagicMock(data=[])
        )

        joined_select = MagicMock()
        joined_select.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=joined_data
        )

        table_mock.select.side_effect = [invite_select, existing_select, joined_select]

        update_chain = MagicMock()
        update_chain.eq.return_value.execute.return_value = MagicMock(data=[updated_data])
        table_mock.update.return_value = update_chain

        response = client.post("/api/v1/patients/me/care-team/join?invite_code=ABC123")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "active"
        assert data["clinician_first_name"] == "Dr. Sarah"

    def test_invalid_code(self, client, override_auth, override_db, mock_supabase_db):
        """Reject invalid invite code."""
        mock_supabase_db.table().select().eq().single().execute.return_value = MagicMock(data=None)

        response = client.post("/api/v1/patients/me/care-team/join?invite_code=INVALID")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "invalid" in response.json()["error"]["message"].lower()

    def test_missing_invite_code_uses_validation_contract(self, client, override_auth, override_db):
        """Missing required query params should use unified error envelope."""
        response = client.post("/api/v1/patients/me/care-team/join")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        payload = response.json()
        assert "error" in payload
        assert payload["error"]["code"] == "VALIDATION_ERROR"
        assert "invite_code" in payload["error"]["message"]

    def test_expired_code(self, client, override_auth, override_db, mock_supabase_db):
        """Reject expired invite code with explicit message."""
        invite_data = {
            "id": str(uuid4()),
            "clinician_id": str(uuid4()),
            "invite_code": "EXPIRED1",
            "status": "pending",
            "patient_id": None,
            "invite_expires_at": "2000-01-01T00:00:00+00:00",
        }

        mock_supabase_db.table().select().eq().single().execute.return_value = MagicMock(
            data=invite_data
        )
        mock_supabase_db.table().update().eq().execute.return_value = MagicMock(data=[invite_data])

        response = client.post("/api/v1/patients/me/care-team/join?invite_code=EXPIRED1")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "expired" in response.json()["error"]["message"].lower()

    def test_already_active_code(self, client, override_auth, override_db, mock_supabase_db):
        """Reject invite code that has already been claimed/activated."""
        invite_data = {
            "id": str(uuid4()),
            "clinician_id": str(uuid4()),
            "invite_code": "CLAIMED1",
            "status": "active",
            "patient_id": str(uuid4()),
            "invite_expires_at": "2099-01-01T00:00:00+00:00",
        }

        mock_supabase_db.table().select().eq().single().execute.return_value = MagicMock(
            data=invite_data
        )

        response = client.post("/api/v1/patients/me/care-team/join?invite_code=CLAIMED1")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert "already active" in response.json()["error"]["message"].lower()


class TestADRInformationRequestRoutes:
    """Patient endpoints for safe ADR follow-up questions and responses."""

    def test_list_pending_requests(
        self,
        client,
        override_auth,
        override_patient_service,
        patient_id,
    ):
        request_id = uuid4()
        assessment_id = uuid4()
        override_patient_service.list_adr_information_requests = AsyncMock(
            return_value=[
                {
                    "id": str(request_id),
                    "adr_assessment_id": str(assessment_id),
                    "symptom": "dizziness",
                    "symptom_severity": 4,
                    "suspect_medication_name": "lisinopril",
                    "requested_information": ["dose_response"],
                    "patient_message": "Tell us about the prior dose change.",
                    "current_naranjo_score": 3,
                    "current_causality": "Possible",
                    "status": "pending",
                    "created_at": "2026-10-06T10:00:00Z",
                }
            ]
        )

        response = client.get("/api/v1/patients/me/adr-information-requests")

        assert response.status_code == status.HTTP_200_OK
        assert response.json()[0]["requested_information"] == ["dose_response"]
        for field in ("current_naranjo_score", "current_causality", "naranjo_score", "causality"):
            assert field not in response.json()[0]
        override_patient_service.list_adr_information_requests.assert_awaited_once_with(patient_id)

    def test_submit_confirmed_response(
        self,
        client,
        override_auth,
        override_patient_service,
        patient_id,
    ):
        request_id = uuid4()
        assessment_id = uuid4()
        override_patient_service.respond_to_adr_information_request = AsyncMock(
            return_value={
                "request_id": str(request_id),
                "adr_assessment_id": str(assessment_id),
                "status": "answered",
                "naranjo_score": 4,
                "causality": "Possible",
                "responded_at": "2026-10-06T10:05:00Z",
            }
        )

        response = client.post(
            f"/api/v1/patients/me/adr-information-requests/{request_id}/respond",
            json={
                "confirmed": True,
                "answers": [
                    {
                        "question": "similar_previous_reaction",
                        "answer": "yes",
                        "evidence": "The same symptom happened last year.",
                    }
                ],
            },
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "answered"
        assert "naranjo_score" not in response.json()
        assert "causality" not in response.json()
        args = override_patient_service.respond_to_adr_information_request.await_args.args
        assert args[0] == patient_id
        assert args[1] == request_id
        assert args[2].answers[0].evidence == "The same symptom happened last year."

    def test_rejects_unconfirmed_response_without_calling_service(
        self,
        client,
        override_auth,
        override_patient_service,
    ):
        response = client.post(
            f"/api/v1/patients/me/adr-information-requests/{uuid4()}/respond",
            json={
                "confirmed": False,
                "answers": [
                    {
                        "question": "dose_response",
                        "answer": "do_not_know",
                    }
                ],
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        override_patient_service.respond_to_adr_information_request.assert_not_called()

    def test_overview_route_is_not_parsed_as_request_id(
        self,
        client,
        override_auth,
        override_patient_service,
        patient_id,
    ):
        override_patient_service.get_adr_follow_up_overview = AsyncMock(
            return_value={"selected": None, "pending": [], "recent": []}
        )

        response = client.get("/api/v1/patients/me/adr-information-requests/overview")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"selected": None, "pending": [], "recent": []}
        override_patient_service.get_adr_follow_up_overview.assert_awaited_once_with(
            patient_id, request_id=None, assessment_id=None
        )

    @pytest.mark.parametrize("parameter", ["request_id", "assessment_id"])
    def test_overview_forwards_the_selector(
        self,
        client,
        override_auth,
        override_patient_service,
        patient_id,
        parameter,
    ):
        target = uuid4()
        override_patient_service.get_adr_follow_up_overview = AsyncMock(
            return_value={"selected": None, "pending": [], "recent": []}
        )

        response = client.get(
            f"/api/v1/patients/me/adr-information-requests/overview?{parameter}={target}"
        )

        assert response.status_code == status.HTTP_200_OK
        expected = {"request_id": None, "assessment_id": None, parameter: target}
        override_patient_service.get_adr_follow_up_overview.assert_awaited_once_with(
            patient_id, **expected
        )

    def test_overview_rejects_both_selectors(self, client, override_auth, override_patient_service):
        override_patient_service.get_adr_follow_up_overview = AsyncMock()

        response = client.get(
            "/api/v1/patients/me/adr-information-requests/overview"
            f"?request_id={uuid4()}&assessment_id={uuid4()}"
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        override_patient_service.get_adr_follow_up_overview.assert_not_called()

    def test_overview_rejects_invalid_uuid(self, client, override_auth, override_patient_service):
        override_patient_service.get_adr_follow_up_overview = AsyncMock()

        response = client.get(
            "/api/v1/patients/me/adr-information-requests/overview?request_id=not-a-uuid"
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"
        override_patient_service.get_adr_follow_up_overview.assert_not_called()

    def test_overview_not_found_uses_error_envelope(
        self, client, override_auth, override_patient_service
    ):
        request_id = uuid4()
        override_patient_service.get_adr_follow_up_overview = AsyncMock(
            side_effect=NotFoundError("ADR information request", str(request_id))
        )

        response = client.get(
            f"/api/v1/patients/me/adr-information-requests/overview?request_id={request_id}"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_respond_closed_request_returns_code_in_envelope(
        self, client, override_auth, override_patient_service
    ):
        override_patient_service.respond_to_adr_information_request = AsyncMock(
            side_effect=ValidationError(
                "This information request is no longer awaiting answers",
                code="ADR_REQUEST_CLOSED",
            )
        )

        response = client.post(
            f"/api/v1/patients/me/adr-information-requests/{uuid4()}/respond",
            json={
                "confirmed": True,
                "answers": [{"question": "dose_response", "answer": "do_not_know"}],
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert response.json()["error"]["code"] == "ADR_REQUEST_CLOSED"

    def test_overview_response_drops_score_and_causality(
        self, client, override_auth, override_patient_service
    ):
        def _item(item_status):
            return {
                "id": str(uuid4()),
                "adr_assessment_id": str(uuid4()),
                "status": item_status,
                "symptom": "dizziness",
                "suspect_medication_name": "lisinopril",
                "requested_information": ["dose_response"],
                "patient_message": "Tell us about the prior dose change.",
                "created_at": "2026-10-06T10:00:00Z",
                "current_naranjo_score": 3,
                "naranjo_score": 3,
                "causality": "Possible",
                "current_causality": "Possible",
            }

        override_patient_service.get_adr_follow_up_overview = AsyncMock(
            return_value={
                "selected": _item("answered"),
                "pending": [_item("pending")],
                "recent": [_item("cancelled")],
                "naranjo_score": 3,
                "causality": "Possible",
            }
        )

        response = client.get("/api/v1/patients/me/adr-information-requests/overview")

        assert response.status_code == status.HTTP_200_OK
        payload = response.json()
        items = [payload["selected"], *payload["pending"], *payload["recent"]]
        for container in [payload, *items]:
            for key in ("current_naranjo_score", "naranjo_score", "causality"):
                assert key not in container
        assert "Possible" not in response.text

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/api/v1/patients/me/adr-information-requests/overview"),
            ("post", "/api/v1/patients/me/adr-information-requests/{id}/respond"),
        ],
    )
    def test_non_patient_role_is_forbidden(
        self, client, override_patient_service, monkeypatch, method, path
    ):
        monkeypatch.setattr(exception_handlers, "record_denial", AsyncMock(return_value=True))
        clinician = CurrentUser(id=uuid4(), email="clinician@test.com", role="clinician")
        app.dependency_overrides[get_current_user] = lambda: clinician
        override_patient_service.get_adr_follow_up_overview = AsyncMock()
        override_patient_service.respond_to_adr_information_request = AsyncMock()
        try:
            response = client.request(
                method,
                path.format(id=uuid4()),
                json=(
                    {
                        "confirmed": True,
                        "answers": [{"question": "dose_response", "answer": "do_not_know"}],
                    }
                    if method == "post"
                    else None
                ),
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["error"]["code"] == "AUTHORIZATION_ERROR"
        override_patient_service.get_adr_follow_up_overview.assert_not_called()
        override_patient_service.respond_to_adr_information_request.assert_not_called()


class TestAuthorization:
    """Test authorization requirements."""

    def test_no_auth_header(self, client):
        """Reject request without authorization header."""
        response = client.get("/api/v1/patients/me")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_token(self, client):
        """Reject request with invalid token."""
        response = client.get(
            "/api/v1/patients/me", headers={"Authorization": "Bearer invalid-token"}
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
