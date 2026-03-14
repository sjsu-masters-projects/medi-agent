"""Tests for Auth service."""

from unittest.mock import MagicMock, Mock

import pytest

from app.core.exceptions import AuthenticationError, ValidationError
from app.services.auth_service import AuthService


@pytest.fixture
def mock_supabase_client():
    """Create a mock Supabase client."""
    client = MagicMock()
    client.auth = MagicMock()
    client.auth.admin = MagicMock()
    client.table = MagicMock()
    return client


@pytest.fixture
def auth_service(mock_supabase_client):
    """Create AuthService instance with mocked client."""
    return AuthService(db=mock_supabase_client)


# ── Patient Signup Tests ──────────────────────────────────────


@pytest.mark.asyncio
async def test_signup_patient_success(auth_service, mock_supabase_client):
    """Test successful patient signup."""
    # Mock auth.sign_up response
    mock_user = Mock()
    mock_user.id = "user-123"
    mock_user.email = "patient@example.com"
    mock_user.created_at = "2024-01-01T00:00:00Z"
    mock_user.app_metadata = {"user_role": "patient"}

    mock_session = Mock()
    mock_session.access_token = "access-token-123"
    mock_session.refresh_token = "refresh-token-123"
    mock_session.expires_at = 1234567890

    mock_auth_response = Mock()
    mock_auth_response.user = mock_user
    mock_auth_response.session = mock_session

    mock_supabase_client.auth.sign_up.return_value = mock_auth_response

    # Mock table insert
    mock_insert = MagicMock()
    mock_insert.execute.return_value = Mock()
    mock_supabase_client.table.return_value.insert.return_value = mock_insert

    # Call signup
    result = await auth_service.signup_patient(
        email="patient@example.com",
        password="SecurePass123!",
        first_name="John",
        last_name="Doe",
        date_of_birth="1990-01-01",
        preferred_language="en",
    )

    # Verify auth.sign_up was called
    mock_supabase_client.auth.sign_up.assert_called_once_with(
        {"email": "patient@example.com", "password": "SecurePass123!"}
    )

    # Verify patient profile was created
    mock_supabase_client.table.assert_called_once_with("patients")
    mock_supabase_client.table.return_value.insert.assert_called_once()

    # Verify response format
    assert result["tokens"]["access_token"] == "access-token-123"
    assert result["tokens"]["refresh_token"] == "refresh-token-123"
    assert result["user"]["id"] == "user-123"
    assert result["user"]["email"] == "patient@example.com"
    assert result["user"]["role"] == "patient"


@pytest.mark.asyncio
async def test_signup_patient_auth_failure(auth_service, mock_supabase_client):
    """Test patient signup when auth creation fails."""
    # Mock auth.sign_up returning no user
    mock_auth_response = Mock()
    mock_auth_response.user = None

    mock_supabase_client.auth.sign_up.return_value = mock_auth_response

    # Should raise ValidationError
    with pytest.raises(ValidationError, match="Signup failed"):
        await auth_service.signup_patient(
            email="invalid@example.com",
            password="pass",
            first_name="John",
            last_name="Doe",
            date_of_birth="1990-01-01",
        )


@pytest.mark.asyncio
async def test_signup_patient_profile_creation_failure(auth_service, mock_supabase_client):
    """Test patient signup when profile creation fails."""
    # Mock successful auth.sign_up
    mock_user = Mock()
    mock_user.id = "user-123"

    mock_auth_response = Mock()
    mock_auth_response.user = mock_user

    mock_supabase_client.auth.sign_up.return_value = mock_auth_response

    # Mock table insert failure
    mock_insert = MagicMock()
    mock_insert.execute.side_effect = Exception("Database error")
    mock_supabase_client.table.return_value.insert.return_value = mock_insert

    # Should raise ValidationError and clean up auth user
    with pytest.raises(ValidationError, match="Profile creation failed"):
        await auth_service.signup_patient(
            email="patient@example.com",
            password="SecurePass123!",
            first_name="John",
            last_name="Doe",
            date_of_birth="1990-01-01",
        )

    # Verify cleanup: auth user should be deleted
    mock_supabase_client.auth.admin.delete_user.assert_called_once_with("user-123")


# ── Clinician Signup Tests ────────────────────────────────────


@pytest.mark.asyncio
async def test_signup_clinician_success(auth_service, mock_supabase_client):
    """Test successful clinician signup."""
    # Mock auth.sign_up response
    mock_user = Mock()
    mock_user.id = "clinician-123"
    mock_user.email = "doctor@example.com"
    mock_user.created_at = "2024-01-01T00:00:00Z"
    mock_user.app_metadata = {"user_role": "clinician"}

    mock_session = Mock()
    mock_session.access_token = "access-token-456"
    mock_session.refresh_token = "refresh-token-456"
    mock_session.expires_at = 1234567890

    mock_auth_response = Mock()
    mock_auth_response.user = mock_user
    mock_auth_response.session = mock_session

    mock_supabase_client.auth.sign_up.return_value = mock_auth_response

    # Mock table insert
    mock_insert = MagicMock()
    mock_insert.execute.return_value = Mock()
    mock_supabase_client.table.return_value.insert.return_value = mock_insert

    # Call signup
    result = await auth_service.signup_clinician(
        email="doctor@example.com",
        password="SecurePass123!",
        first_name="Jane",
        last_name="Smith",
        specialty="Cardiology",
        clinic_name="Heart Health Clinic",
        npi_number="1234567890",
    )

    # Verify auth.sign_up was called
    mock_supabase_client.auth.sign_up.assert_called_once_with(
        {"email": "doctor@example.com", "password": "SecurePass123!"}
    )

    # Verify clinician profile was created
    mock_supabase_client.table.assert_called_once_with("clinicians")

    # Verify response format
    assert result["tokens"]["access_token"] == "access-token-456"
    assert result["user"]["id"] == "clinician-123"
    assert result["user"]["role"] == "clinician"


@pytest.mark.asyncio
async def test_signup_clinician_profile_creation_failure(auth_service, mock_supabase_client):
    """Test clinician signup when profile creation fails."""
    # Mock successful auth.sign_up
    mock_user = Mock()
    mock_user.id = "clinician-123"

    mock_auth_response = Mock()
    mock_auth_response.user = mock_user

    mock_supabase_client.auth.sign_up.return_value = mock_auth_response

    # Mock table insert failure
    mock_insert = MagicMock()
    mock_insert.execute.side_effect = Exception("Database constraint violation")
    mock_supabase_client.table.return_value.insert.return_value = mock_insert

    # Should raise ValidationError and clean up auth user
    with pytest.raises(ValidationError, match="Profile creation failed"):
        await auth_service.signup_clinician(
            email="doctor@example.com",
            password="SecurePass123!",
            first_name="Jane",
            last_name="Smith",
            specialty="Cardiology",
            clinic_name="Heart Health Clinic",
        )

    # Verify cleanup
    mock_supabase_client.auth.admin.delete_user.assert_called_once_with("clinician-123")


# ── Login Tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_success(auth_service, mock_supabase_client):
    """Test successful login."""
    # Mock sign_in_with_password response
    mock_user = Mock()
    mock_user.id = "user-123"
    mock_user.email = "user@example.com"
    mock_user.created_at = "2024-01-01T00:00:00Z"
    mock_user.app_metadata = {"user_role": "patient"}

    mock_session = Mock()
    mock_session.access_token = "login-access-token"
    mock_session.refresh_token = "login-refresh-token"
    mock_session.expires_at = 1234567890

    mock_auth_response = Mock()
    mock_auth_response.user = mock_user
    mock_auth_response.session = mock_session

    mock_supabase_client.auth.sign_in_with_password.return_value = mock_auth_response

    # Call login
    result = await auth_service.login(email="user@example.com", password="password123")

    # Verify sign_in_with_password was called
    mock_supabase_client.auth.sign_in_with_password.assert_called_once_with(
        {"email": "user@example.com", "password": "password123"}
    )

    # Verify response format
    assert result["tokens"]["access_token"] == "login-access-token"
    assert result["user"]["id"] == "user-123"


@pytest.mark.asyncio
async def test_login_invalid_credentials(auth_service, mock_supabase_client):
    """Test login with invalid credentials."""
    # Mock sign_in_with_password raising exception
    mock_supabase_client.auth.sign_in_with_password.side_effect = Exception(
        "Invalid login credentials"
    )

    # Should raise AuthenticationError
    with pytest.raises(AuthenticationError, match="Invalid email or password"):
        await auth_service.login(email="wrong@example.com", password="wrongpass")


# ── Token Refresh Tests ───────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_token_success(auth_service, mock_supabase_client):
    """Test successful token refresh."""
    # Mock refresh_session response
    mock_user = Mock()
    mock_user.id = "user-123"
    mock_user.email = "user@example.com"
    mock_user.created_at = "2024-01-01T00:00:00Z"
    mock_user.app_metadata = {"user_role": "patient"}

    mock_session = Mock()
    mock_session.access_token = "new-access-token"
    mock_session.refresh_token = "new-refresh-token"
    mock_session.expires_at = 1234567890

    mock_auth_response = Mock()
    mock_auth_response.user = mock_user
    mock_auth_response.session = mock_session

    mock_supabase_client.auth.refresh_session.return_value = mock_auth_response

    # Call refresh_token
    result = await auth_service.refresh_token(refresh_token="old-refresh-token")

    # Verify refresh_session was called
    mock_supabase_client.auth.refresh_session.assert_called_once_with("old-refresh-token")

    # Verify response format
    assert result["tokens"]["access_token"] == "new-access-token"
    assert result["tokens"]["refresh_token"] == "new-refresh-token"


@pytest.mark.asyncio
async def test_refresh_token_invalid(auth_service, mock_supabase_client):
    """Test token refresh with invalid token."""
    # Mock refresh_session raising exception
    mock_supabase_client.auth.refresh_session.side_effect = Exception("Invalid refresh token")

    # Should raise AuthenticationError
    with pytest.raises(AuthenticationError, match="Invalid or expired refresh token"):
        await auth_service.refresh_token(refresh_token="invalid-token")


# ── Password Reset Tests ──────────────────────────────────────


@pytest.mark.asyncio
async def test_request_password_reset_success(auth_service, mock_supabase_client):
    """Test successful password reset request."""
    # Mock reset_password_email
    mock_supabase_client.auth.reset_password_email.return_value = None

    # Call request_password_reset (should not raise)
    await auth_service.request_password_reset(email="user@example.com")

    # Verify reset_password_email was called
    mock_supabase_client.auth.reset_password_email.assert_called_once_with("user@example.com")


@pytest.mark.asyncio
async def test_request_password_reset_email_not_found(auth_service, mock_supabase_client):
    """Test password reset request for non-existent email (should not reveal)."""
    # Mock reset_password_email raising exception
    mock_supabase_client.auth.reset_password_email.side_effect = Exception("User not found")

    # Should NOT raise (security: don't reveal if email exists)
    await auth_service.request_password_reset(email="nonexistent@example.com")

    # Verify reset_password_email was called
    mock_supabase_client.auth.reset_password_email.assert_called_once_with(
        "nonexistent@example.com"
    )


# ── Session Formatting Tests ──────────────────────────────────


@pytest.mark.asyncio
async def test_format_session_no_session(auth_service):
    """Test _format_session with missing session."""
    mock_response = Mock()
    mock_response.session = None
    mock_response.user = Mock()

    with pytest.raises(AuthenticationError, match="Authentication failed"):
        auth_service._format_session(mock_response)


@pytest.mark.asyncio
async def test_format_session_no_user(auth_service):
    """Test _format_session with missing user."""
    mock_response = Mock()
    mock_response.session = Mock()
    mock_response.user = None

    with pytest.raises(AuthenticationError, match="Authentication failed"):
        auth_service._format_session(mock_response)


@pytest.mark.asyncio
async def test_format_session_missing_email(auth_service):
    """Test _format_session with missing email."""
    mock_user = Mock()
    mock_user.id = "user-123"
    mock_user.email = None  # Missing email
    mock_user.created_at = "2024-01-01T00:00:00Z"
    mock_user.app_metadata = {"user_role": "patient"}

    mock_session = Mock()
    mock_session.access_token = "token"
    mock_session.refresh_token = "refresh"
    mock_session.expires_at = 1234567890

    mock_response = Mock()
    mock_response.user = mock_user
    mock_response.session = mock_session

    result = auth_service._format_session(mock_response)

    # Should default to empty string
    assert result["user"]["email"] == ""


@pytest.mark.asyncio
async def test_format_session_missing_app_metadata(auth_service):
    """Test _format_session with missing app_metadata."""
    mock_user = Mock()
    mock_user.id = "user-123"
    mock_user.email = "user@example.com"
    mock_user.created_at = "2024-01-01T00:00:00Z"
    mock_user.app_metadata = None  # Missing metadata

    mock_session = Mock()
    mock_session.access_token = "token"
    mock_session.refresh_token = "refresh"
    mock_session.expires_at = 1234567890

    mock_response = Mock()
    mock_response.user = mock_user
    mock_response.session = mock_session

    result = auth_service._format_session(mock_response)

    # Should default to "unknown"
    assert result["user"]["role"] == "unknown"


@pytest.mark.asyncio
async def test_format_session_missing_expires_at(auth_service):
    """Test _format_session with missing expires_at."""
    mock_user = Mock()
    mock_user.id = "user-123"
    mock_user.email = "user@example.com"
    mock_user.created_at = "2024-01-01T00:00:00Z"
    mock_user.app_metadata = {"user_role": "patient"}

    mock_session = Mock()
    mock_session.access_token = "token"
    mock_session.refresh_token = "refresh"
    mock_session.expires_at = None  # Missing expires_at

    mock_response = Mock()
    mock_response.user = mock_user
    mock_response.session = mock_session

    result = auth_service._format_session(mock_response)

    # Should default to 0
    assert result["tokens"]["expires_at"] == 0
