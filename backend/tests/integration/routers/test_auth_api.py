"""Integration tests for Auth API endpoints."""

from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest
from fastapi import status

from app.core.exceptions import AuthenticationError
from app.core.security import get_current_user
from app.db.connection import get_db
from app.main import app
from app.models.auth import CurrentUser
from app.routers.auth import _get_auth_service
from app.services.auth_service import AuthService


@pytest.fixture
def mock_supabase_db():
    """Mock Supabase client with auth and table access."""
    db = MagicMock()
    db.auth = MagicMock()
    db.auth.admin = MagicMock()
    table = MagicMock()
    db.table.return_value = table
    for method in ["select", "insert", "delete", "eq", "execute"]:
        getattr(table, method).return_value = table
    return db


@pytest.fixture
def override_db(mock_supabase_db):
    """Override database dependency."""

    def _get_db_override():
        return mock_supabase_db

    app.dependency_overrides[get_db] = _get_db_override
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def override_auth_service(mock_supabase_db):
    """Override AuthService so auth SDK calls use the mocked client."""

    def _get_auth_service_override():
        return AuthService(db=mock_supabase_db, auth_client=mock_supabase_db)

    app.dependency_overrides[_get_auth_service] = _get_auth_service_override
    yield
    app.dependency_overrides.clear()


def _make_auth_response(*, user_id: str, email: str, role: str) -> Mock:
    user = Mock()
    user.id = user_id
    user.email = email
    user.created_at = "2026-01-01T00:00:00Z"
    user.app_metadata = {"user_role": role}

    session = Mock()
    session.access_token = f"{role}-access-token"
    session.refresh_token = f"{role}-refresh-token"
    session.expires_at = 1234567890

    response = Mock()
    response.user = user
    response.session = session
    return response


class TestPatientSignup:
    def test_success(self, client, override_db, override_auth_service, mock_supabase_db):
        user_id = str(uuid4())
        signup_response = Mock()
        signup_response.user = Mock(id=user_id)
        mock_supabase_db.auth.sign_up.return_value = signup_response
        mock_supabase_db.auth.sign_in_with_password.return_value = _make_auth_response(
            user_id=user_id,
            email="patient@example.com",
            role="patient",
        )

        response = client.post(
            "/api/v1/auth/signup/patient",
            json={
                "email": "patient@example.com",
                "password": "SecurePass123!",
                "first_name": "Sarah",
                "last_name": "Jones",
                "date_of_birth": "1990-01-01",
                "preferred_language": "en",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert set(data.keys()) == {"tokens", "user"}
        assert data["user"]["role"] == "patient"
        assert data["tokens"]["refresh_token"] == "patient-refresh-token"

    def test_duplicate_email(self, client, override_db, override_auth_service, mock_supabase_db):
        signup_response = Mock()
        signup_response.user = None
        mock_supabase_db.auth.sign_up.return_value = signup_response

        response = client.post(
            "/api/v1/auth/signup/patient",
            json={
                "email": "patient@example.com",
                "password": "SecurePass123!",
                "first_name": "Sarah",
                "last_name": "Jones",
                "date_of_birth": "1990-01-01",
                "preferred_language": "en",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        payload = response.json()
        assert "error" in payload
        assert payload["error"]["code"] == "VALIDATION_ERROR"
        assert isinstance(payload["error"]["message"], str)

    def test_request_validation_error_shape(self, client, override_db):
        response = client.post(
            "/api/v1/auth/signup/patient",
            json={
                "email": "patient@example.com",
                "password": "SecurePass123!",
                "last_name": "Jones",
                "date_of_birth": "1990-01-01",
                "preferred_language": "en",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        payload = response.json()
        assert "error" in payload
        assert payload["error"]["code"] == "VALIDATION_ERROR"
        assert "first_name" in payload["error"]["message"]


class TestClinicianSignup:
    def test_success(self, client, override_db, override_auth_service, mock_supabase_db):
        user_id = str(uuid4())
        table = mock_supabase_db.table.return_value
        table.execute.side_effect = [
            Mock(
                data=[
                    {
                        "id": "clinic-1",
                        "code": "ABC123",
                        "display_name": "City Health",
                        "status": "active",
                    }
                ]
            ),
            Mock(data=[]),
        ]

        signup_response = Mock()
        signup_response.user = Mock(id=user_id)
        mock_supabase_db.auth.sign_up.return_value = signup_response
        mock_supabase_db.auth.sign_in_with_password.return_value = _make_auth_response(
            user_id=user_id,
            email="doctor@example.com",
            role="clinician",
        )

        response = client.post(
            "/api/v1/auth/signup/clinician",
            json={
                "email": "doctor@example.com",
                "password": "SecurePass123!",
                "first_name": "Amir",
                "last_name": "Khan",
                "clinic_code": "ABC123",
                "specialty": "Primary Care",
                "type1_npi": "1234567890",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["user"]["role"] == "clinician"

    def test_signup_exception_returns_validation_error(
        self, client, override_db, override_auth_service, mock_supabase_db
    ):
        table = mock_supabase_db.table.return_value
        table.execute.return_value = Mock(
            data=[
                {
                    "id": "clinic-1",
                    "code": "ABC123",
                    "display_name": "City Health",
                    "status": "active",
                }
            ]
        )
        mock_supabase_db.auth.sign_up.side_effect = Exception("User already registered")

        response = client.post(
            "/api/v1/auth/signup/clinician",
            json={
                "email": "doctor@example.com",
                "password": "SecurePass123!",
                "first_name": "Amir",
                "last_name": "Khan",
                "clinic_code": "ABC123",
                "specialty": "Primary Care",
                "type1_npi": "1234567890",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        payload = response.json()
        assert "error" in payload
        assert payload["error"]["code"] == "VALIDATION_ERROR"

    def test_signup_rejects_invalid_clinic_code(
        self, client, override_db, override_auth_service, mock_supabase_db
    ):
        table = mock_supabase_db.table.return_value
        table.execute.return_value = Mock(data=[])

        response = client.post(
            "/api/v1/auth/signup/clinician",
            json={
                "email": "doctor@example.com",
                "password": "SecurePass123!",
                "first_name": "Amir",
                "last_name": "Khan",
                "clinic_code": "INVALID",
                "specialty": "Primary Care",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    def test_signup_supports_nurse_role(
        self, client, override_db, override_auth_service, mock_supabase_db
    ):
        user_id = str(uuid4())
        table = mock_supabase_db.table.return_value
        table.execute.side_effect = [
            Mock(
                data=[
                    {
                        "id": "clinic-1",
                        "code": "ABC123",
                        "display_name": "City Health",
                        "status": "active",
                    }
                ]
            ),
            Mock(data=[]),
        ]

        signup_response = Mock()
        signup_response.user = Mock(id=user_id)
        mock_supabase_db.auth.sign_up.return_value = signup_response
        mock_supabase_db.auth.sign_in_with_password.return_value = _make_auth_response(
            user_id=user_id,
            email="nurse@example.com",
            role="clinician",
        )

        response = client.post(
            "/api/v1/auth/signup/clinician",
            json={
                "email": "nurse@example.com",
                "password": "SecurePass123!",
                "first_name": "Nora",
                "last_name": "Lane",
                "clinic_code": "ABC123",
                "specialty": "Care Coordination",
                "role": "nurse",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["user"]["role"] == "clinician"

    def test_signup_rejects_admin_role_in_public_clinician_signup(
        self, client, override_db, override_auth_service, mock_supabase_db
    ):
        response = client.post(
            "/api/v1/auth/signup/clinician",
            json={
                "email": "adminlike@example.com",
                "password": "SecurePass123!",
                "first_name": "Alex",
                "last_name": "Reed",
                "clinic_code": "ABC123",
                "specialty": "Primary Care",
                "role": "admin",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


class TestClinicAdminSignup:
    def test_success(self, client, override_db, override_auth_service, mock_supabase_db):
        user_id = str(uuid4())
        table = mock_supabase_db.table.return_value
        table.execute.side_effect = [
            Mock(data=[]),
            Mock(
                data=[
                    {
                        "id": "clinic-1",
                        "code": "ABC123",
                        "display_name": "City Health",
                        "status": "active",
                    }
                ]
            ),
            Mock(
                data=[
                    {
                        "id": "clinic-1",
                        "code": "ABC123",
                        "display_name": "City Health",
                        "status": "active",
                    }
                ]
            ),
            Mock(data=[]),
        ]

        signup_response = Mock()
        signup_response.user = Mock(id=user_id)
        mock_supabase_db.auth.sign_up.return_value = signup_response
        mock_supabase_db.auth.sign_in_with_password.return_value = _make_auth_response(
            user_id=user_id,
            email="admin@example.com",
            role="clinician",
        )

        response = client.post(
            "/api/v1/auth/signup/clinic-admin",
            json={
                "clinic_name": "City Health",
                "email": "admin@example.com",
                "password": "SecurePass123!",
                "first_name": "Amina",
                "last_name": "Khan",
                "specialty": "Primary Care",
                "type1_npi": "1234567890",
                "type2_npi": "0987654321",
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["user"]["role"] == "clinician"

    def test_signup_exception_returns_validation_error(
        self, client, override_db, override_auth_service, mock_supabase_db
    ):
        mock_supabase_db.auth.sign_up.side_effect = Exception("User already registered")

        response = client.post(
            "/api/v1/auth/signup/clinician",
            json={
                "email": "doctor@example.com",
                "password": "SecurePass123!",
                "first_name": "Amir",
                "last_name": "Khan",
                "clinic_name": "City Health",
                "specialty": "Primary Care",
                "npi_number": "1234567890",
            },
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


class TestLogin:
    def test_success_for_both_roles(self, client, override_db, override_auth_service, mock_supabase_db):
        mock_supabase_db.auth.sign_in_with_password.side_effect = [
            _make_auth_response(
                user_id=str(uuid4()),
                email="patient@example.com",
                role="patient",
            ),
            _make_auth_response(
                user_id=str(uuid4()),
                email="doctor@example.com",
                role="clinician",
            ),
        ]

        original = AuthService._list_verified_mfa_factors
        original_clinic_check = AuthService._assert_clinician_matches_clinic
        AuthService._list_verified_mfa_factors = staticmethod(lambda _access, _refresh: [])
        AuthService._assert_clinician_matches_clinic = lambda self, _id, _code: None
        try:
            patient_response = client.post(
                "/api/v1/auth/login",
                json={"email": "patient@example.com", "password": "SecurePass123!"},
            )
            clinician_response = client.post(
                "/api/v1/auth/login",
                json={
                    "clinic_code": "ABC123",
                    "email": "doctor@example.com",
                    "password": "SecurePass123!",
                },
            )
        finally:
            AuthService._list_verified_mfa_factors = original
            AuthService._assert_clinician_matches_clinic = original_clinic_check

        assert patient_response.status_code == status.HTTP_200_OK
        assert patient_response.json()["user"]["role"] == "patient"
        assert patient_response.json()["mfa_required"] is False
        assert clinician_response.status_code == status.HTTP_200_OK
        assert clinician_response.json()["user"]["role"] == "clinician"
        assert clinician_response.json()["mfa_required"] is False

    def test_clinician_login_can_require_mfa(
        self, client, override_db, override_auth_service, mock_supabase_db
    ):
        response = _make_auth_response(
            user_id=str(uuid4()),
            email="doctor@example.com",
            role="clinician",
        )
        mock_supabase_db.auth.sign_in_with_password.return_value = response

        original = AuthService._list_verified_mfa_factors
        original_clinic_check = AuthService._assert_clinician_matches_clinic
        AuthService._list_verified_mfa_factors = staticmethod(
            lambda _access, _refresh: [
                {
                    "id": "factor-1",
                    "friendly_name": "Authenticator",
                    "factor_type": "totp",
                    "status": "verified",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            ]
        )
        AuthService._assert_clinician_matches_clinic = lambda self, _id, _code: None
        try:
            result = client.post(
                "/api/v1/auth/login",
                json={
                    "clinic_code": "ABC123",
                    "email": "doctor@example.com",
                    "password": "SecurePass123!",
                },
            )
        finally:
            AuthService._list_verified_mfa_factors = original
            AuthService._assert_clinician_matches_clinic = original_clinic_check

        assert result.status_code == status.HTTP_200_OK
        assert result.json()["mfa_required"] is True
        assert result.json()["mfa_factors"][0]["id"] == "factor-1"

    def test_clinician_login_requires_clinic_code(
        self, client, override_db, override_auth_service, mock_supabase_db
    ):
        response = _make_auth_response(
            user_id=str(uuid4()),
            email="doctor@example.com",
            role="clinician",
        )
        mock_supabase_db.auth.sign_in_with_password.return_value = response

        result = client.post(
            "/api/v1/auth/login",
            json={"email": "doctor@example.com", "password": "SecurePass123!"},
        )

        assert result.status_code == status.HTTP_401_UNAUTHORIZED
        assert result.json()["error"]["code"] == "CLINIC_CONTEXT_INVALID"
        assert "Clinic code is required" in result.json()["error"]["message"]

    def test_invalid_credentials(self, client, override_db, override_auth_service, mock_supabase_db):
        mock_supabase_db.auth.sign_in_with_password.side_effect = Exception("Invalid login")

        response = client.post(
            "/api/v1/auth/login",
            json={"email": "patient@example.com", "password": "wrong"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_clinician_login_returns_explicit_clinic_context_code(
        self, client, override_db, override_auth_service, mock_supabase_db
    ):
        response = _make_auth_response(
            user_id=str(uuid4()),
            email="doctor@example.com",
            role="clinician",
        )
        mock_supabase_db.auth.sign_in_with_password.return_value = response

        original_clinic_check = AuthService._assert_clinician_matches_clinic
        AuthService._assert_clinician_matches_clinic = lambda self, _id, _code: (_ for _ in ()).throw(
            AuthenticationError(
                "Clinician account does not belong to the selected clinic",
                code="CLINIC_CONTEXT_INVALID",
            )
        )
        try:
            result = client.post(
                "/api/v1/auth/login",
                json={
                    "clinic_code": "ABC123",
                    "email": "doctor@example.com",
                    "password": "SecurePass123!",
                },
            )
        finally:
            AuthService._assert_clinician_matches_clinic = original_clinic_check

        assert result.status_code == status.HTTP_401_UNAUTHORIZED
        assert result.json()["error"]["code"] == "CLINIC_CONTEXT_INVALID"


class TestRefresh:
    def test_success(self, client, override_db, override_auth_service, mock_supabase_db):
        mock_supabase_db.auth.refresh_session.return_value = _make_auth_response(
            user_id=str(uuid4()),
            email="patient@example.com",
            role="patient",
        )

        response = client.post(
            "/api/v1/auth/refresh",
            json={"expected_role": "patient", "refresh_token": "refresh-token-123"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["tokens"]["access_token"] == "patient-access-token"

    def test_rejects_mismatched_expected_role(
        self, client, override_db, override_auth_service, mock_supabase_db
    ):
        mock_supabase_db.auth.refresh_session.return_value = _make_auth_response(
            user_id=str(uuid4()),
            email="doctor@example.com",
            role="clinician",
        )

        response = client.post(
            "/api/v1/auth/refresh",
            json={"expected_role": "patient", "refresh_token": "refresh-token-123"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_invalid_token(self, client, override_db, override_auth_service, mock_supabase_db):
        mock_supabase_db.auth.refresh_session.side_effect = Exception("Invalid refresh")

        response = client.post(
            "/api/v1/auth/refresh",
            json={"expected_role": "patient", "refresh_token": "bad-token"},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestPasswordReset:
    def test_success(self, client, override_db, override_auth_service, mock_supabase_db):
        response = client.post(
            "/api/v1/auth/password-reset",
            json={"email": "patient@example.com"},
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        mock_supabase_db.auth.reset_password_email.assert_called_once_with("patient@example.com")


class TestGetMe:
    def test_patient_success(self, client):
        current_user = CurrentUser(
            id=uuid4(),
            email="patient@example.com",
            role="patient",
        )

        def _get_current_user_override():
            return current_user

        app.dependency_overrides[get_current_user] = _get_current_user_override
        try:
            response = client.get("/api/v1/auth/me")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["role"] == "patient"

    def test_clinician_success(self, client):
        current_user = CurrentUser(
            id=uuid4(),
            email="doctor@example.com",
            role="clinician",
        )

        def _get_current_user_override():
            return current_user

        app.dependency_overrides[get_current_user] = _get_current_user_override
        try:
            response = client.get("/api/v1/auth/me")
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["role"] == "clinician"

    def test_missing_auth(self, client):
        response = client.get("/api/v1/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
