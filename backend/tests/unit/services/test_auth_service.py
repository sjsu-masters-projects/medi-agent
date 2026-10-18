"""Tests for Auth service."""

import time
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from app.core.exceptions import AuthenticationError, ExternalServiceError, ValidationError
from app.models.clinic_membership import ClinicMembership
from app.services.auth_service import AuthService

CLINIC_A = "00000000-0000-0000-0000-0000000000a1"
CLINIC_B = "00000000-0000-0000-0000-0000000000b2"


def _membership(clinic_id: str = CLINIC_A, role: str = "provider") -> ClinicMembership:
    return ClinicMembership(
        clinician_id="00000000-0000-0000-0000-0000000000aa",
        clinic_id=clinic_id,
        role=role,
        status="active",
    )


@pytest.fixture(autouse=True)
def _no_existing_clinician_account():
    """Signup looks for an existing clinician with the address; none unless a test says so."""
    with patch(
        "app.services.auth_service.ClinicianRepository.list_by_email_any_case", return_value=[]
    ):
        yield


@pytest.fixture
def mock_supabase_client():
    """Create a mock Supabase client."""
    client = MagicMock()
    client.auth = MagicMock()
    client.auth.admin = MagicMock()
    client.table = MagicMock()
    return client


@pytest.fixture
def mock_auth_client():
    client = MagicMock()
    client.auth = MagicMock()
    return client


@pytest.fixture
def auth_service(mock_supabase_client, mock_auth_client):
    """Create AuthService instance with mocked client."""
    with patch("app.services.auth_service.create_anon_client", return_value=mock_auth_client):
        return AuthService(db=mock_supabase_client)


# ── Patient Signup Tests ──────────────────────────────────────


@pytest.mark.asyncio
async def test_signup_patient_success(auth_service, mock_supabase_client, mock_auth_client):
    """Test successful patient signup."""
    signup_user = Mock()
    signup_user.id = "user-123"
    signup_response = Mock()
    signup_response.user = signup_user
    mock_auth_client.auth.sign_up.return_value = signup_response

    login_user = Mock()
    login_user.id = "user-123"
    login_user.email = "patient@example.com"
    login_user.created_at = "2024-01-01T00:00:00Z"
    login_user.app_metadata = {"user_role": "patient"}

    login_session = Mock()
    login_session.access_token = "access-token-123"
    login_session.refresh_token = "refresh-token-123"
    login_session.expires_at = 1234567890

    login_response = Mock()
    login_response.user = login_user
    login_response.session = login_session

    mock_auth_client.auth.sign_in_with_password.return_value = login_response

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
    mock_auth_client.auth.sign_up.assert_called_once_with(
        {"email": "patient@example.com", "password": "SecurePass123!"}
    )

    # Verify patient profile was created
    mock_supabase_client.table.assert_called_once_with("patients")
    mock_supabase_client.table.return_value.insert.assert_called_once()

    mock_auth_client.auth.sign_in_with_password.assert_called_once_with(
        {"email": "patient@example.com", "password": "SecurePass123!"}
    )

    assert result["tokens"]["access_token"] == "access-token-123"
    assert result["tokens"]["refresh_token"] == "refresh-token-123"
    assert result["user"]["id"] == "user-123"
    assert result["user"]["email"] == "patient@example.com"
    assert result["user"]["role"] == "patient"


@pytest.mark.asyncio
async def test_signup_patient_auth_failure(auth_service, mock_auth_client):
    """Test patient signup when auth creation fails."""
    # Mock auth.sign_up returning no user
    mock_auth_response = Mock()
    mock_auth_response.user = None

    mock_auth_client.auth.sign_up.return_value = mock_auth_response

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
async def test_signup_patient_auth_exception(auth_service, mock_auth_client):
    """Test patient signup when Supabase sign_up raises unexpectedly."""
    mock_auth_client.auth.sign_up.side_effect = Exception("User already registered")

    with pytest.raises(ValidationError, match="already registered"):
        await auth_service.signup_patient(
            email="patient@example.com",
            password="SecurePass123!",
            first_name="John",
            last_name="Doe",
            date_of_birth="1990-01-01",
        )


@pytest.mark.asyncio
async def test_signup_patient_auth_hook_exception(auth_service, mock_auth_client):
    """Return a clear error when Supabase custom access-token hook fails."""
    mock_auth_client.auth.sign_up.side_effect = Exception(
        "Error running hook URI: pg-functions://postgres/public/custom_access_token_hook"
    )

    with pytest.raises(ValidationError, match="access token hook"):
        await auth_service.signup_patient(
            email="patient@example.com",
            password="SecurePass123!",
            first_name="John",
            last_name="Doe",
            date_of_birth="1990-01-01",
        )


@pytest.mark.asyncio
async def test_signup_patient_profile_creation_failure(
    auth_service, mock_supabase_client, mock_auth_client
):
    """Test patient signup when profile creation fails."""
    # Mock successful auth.sign_up
    mock_user = Mock()
    mock_user.id = "user-123"

    mock_auth_response = Mock()
    mock_auth_response.user = mock_user

    mock_auth_client.auth.sign_up.return_value = mock_auth_response

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
async def test_signup_clinician_success(auth_service, mock_supabase_client, mock_auth_client):
    """Test successful clinician signup."""
    signup_user = Mock()
    signup_user.id = "clinician-123"
    signup_response = Mock()
    signup_response.user = signup_user
    mock_auth_client.auth.sign_up.return_value = signup_response

    login_user = Mock()
    login_user.id = "clinician-123"
    login_user.email = "doctor@example.com"
    login_user.created_at = "2024-01-01T00:00:00Z"
    login_user.app_metadata = {"user_role": "clinician"}

    login_session = Mock()
    login_session.access_token = "access-token-456"
    login_session.refresh_token = "refresh-token-456"
    login_session.expires_at = 1234567890

    login_response = Mock()
    login_response.user = login_user
    login_response.session = login_session

    mock_auth_client.auth.sign_in_with_password.return_value = login_response

    clinic_query = MagicMock()
    clinic_query.select.return_value = clinic_query
    clinic_query.eq.return_value = clinic_query
    clinic_query.execute.return_value = Mock(
        data=[
            {
                "id": "clinic-1",
                "code": "ABC123",
                "display_name": "Heart Health Clinic",
                "status": "active",
            }
        ]
    )

    clinician_table = MagicMock()
    clinician_insert = MagicMock()
    clinician_table.insert.return_value = clinician_insert
    clinician_insert.execute.return_value = Mock()

    mock_supabase_client.table.side_effect = [clinic_query, clinician_table]

    # Call signup
    result = await auth_service.signup_clinician(
        email="doctor@example.com",
        password="SecurePass123!",
        first_name="Jane",
        last_name="Smith",
        specialty="Cardiology",
        clinic_code="abc123",
        type1_npi="1234567890",
    )

    # Verify auth.sign_up was called
    mock_auth_client.auth.sign_up.assert_called_once_with(
        {"email": "doctor@example.com", "password": "SecurePass123!"}
    )

    # Verify clinician profile was created
    mock_supabase_client.table.assert_any_call("clinics")
    mock_supabase_client.table.assert_any_call("clinicians")

    mock_auth_client.auth.sign_in_with_password.assert_called_once_with(
        {"email": "doctor@example.com", "password": "SecurePass123!"}
    )

    assert result["tokens"]["access_token"] == "access-token-456"
    assert result["user"]["id"] == "clinician-123"
    assert result["user"]["role"] == "clinician"


@pytest.mark.asyncio
async def test_signup_clinician_profile_creation_failure(
    auth_service, mock_supabase_client, mock_auth_client
):
    """Test clinician signup when profile creation fails."""
    # Mock successful auth.sign_up
    mock_user = Mock()
    mock_user.id = "clinician-123"

    mock_auth_response = Mock()
    mock_auth_response.user = mock_user

    mock_auth_client.auth.sign_up.return_value = mock_auth_response

    clinic_query = MagicMock()
    clinic_query.select.return_value = clinic_query
    clinic_query.eq.return_value = clinic_query
    clinic_query.execute.return_value = Mock(
        data=[
            {
                "id": "clinic-1",
                "code": "ABC123",
                "display_name": "Heart Health Clinic",
                "status": "active",
            }
        ]
    )

    clinician_table = MagicMock()
    clinician_insert = MagicMock()
    clinician_insert.execute.side_effect = Exception("Database constraint violation")
    clinician_table.insert.return_value = clinician_insert
    mock_supabase_client.table.side_effect = [clinic_query, clinician_table]

    # Should raise ValidationError and clean up auth user
    with pytest.raises(ValidationError, match="Profile creation failed"):
        await auth_service.signup_clinician(
            email="doctor@example.com",
            password="SecurePass123!",
            first_name="Jane",
            last_name="Smith",
            specialty="Cardiology",
            clinic_code="ABC123",
        )

    # Verify cleanup
    mock_supabase_client.auth.admin.delete_user.assert_called_once_with("clinician-123")


@pytest.mark.asyncio
async def test_signup_clinician_invalid_clinic_code(auth_service, mock_supabase_client):
    clinic_query = MagicMock()
    clinic_query.select.return_value = clinic_query
    clinic_query.eq.return_value = clinic_query
    clinic_query.execute.return_value = Mock(data=[])
    mock_supabase_client.table.return_value = clinic_query

    with pytest.raises(ValidationError, match="Clinic code is invalid"):
        await auth_service.signup_clinician(
            email="doctor@example.com",
            password="SecurePass123!",
            first_name="Jane",
            last_name="Smith",
            specialty="Cardiology",
            clinic_code="INVALID",
        )


@pytest.mark.asyncio
async def test_signup_clinician_inactive_clinic_code(auth_service, mock_supabase_client):
    clinic_query = MagicMock()
    clinic_query.select.return_value = clinic_query
    clinic_query.eq.return_value = clinic_query
    clinic_query.execute.return_value = Mock(
        data=[{"id": "clinic-1", "display_name": "Heart Health Clinic", "status": "suspended"}]
    )
    mock_supabase_client.table.return_value = clinic_query

    with pytest.raises(ValidationError, match="Clinic code is inactive"):
        await auth_service.signup_clinician(
            email="doctor@example.com",
            password="SecurePass123!",
            first_name="Jane",
            last_name="Smith",
            specialty="Cardiology",
            clinic_code="ABC123",
        )


@pytest.mark.asyncio
async def test_signup_clinician_supports_nurse_role(
    auth_service, mock_supabase_client, mock_auth_client
):
    signup_user = Mock()
    signup_user.id = "clinician-nurse-123"
    signup_response = Mock()
    signup_response.user = signup_user
    mock_auth_client.auth.sign_up.return_value = signup_response

    login_user = Mock()
    login_user.id = "clinician-nurse-123"
    login_user.email = "nurse@example.com"
    login_user.created_at = "2024-01-01T00:00:00Z"
    login_user.app_metadata = {"user_role": "clinician"}

    login_session = Mock()
    login_session.access_token = "access-token-nurse"
    login_session.refresh_token = "refresh-token-nurse"
    login_session.expires_at = 1234567890

    login_response = Mock()
    login_response.user = login_user
    login_response.session = login_session
    mock_auth_client.auth.sign_in_with_password.return_value = login_response

    clinic_query = MagicMock()
    clinic_query.select.return_value = clinic_query
    clinic_query.eq.return_value = clinic_query
    clinic_query.execute.return_value = Mock(
        data=[
            {
                "id": "clinic-1",
                "code": "ABC123",
                "display_name": "City Health",
                "status": "active",
            }
        ]
    )

    clinician_table = MagicMock()
    clinician_insert = MagicMock()
    clinician_insert.execute.return_value = Mock()
    clinician_table.insert.return_value = clinician_insert
    mock_supabase_client.table.side_effect = [clinic_query, clinician_table]

    await auth_service.signup_clinician(
        email="nurse@example.com",
        password="SecurePass123!",
        first_name="Nora",
        last_name="Lane",
        specialty="Care Coordination",
        clinic_code="ABC123",
        role="nurse",
    )

    inserted_payload = clinician_table.insert.call_args.args[0]
    assert inserted_payload["role"] == "nurse"


@pytest.mark.asyncio
async def test_signup_clinician_rejects_admin_role_by_default(auth_service, mock_supabase_client):
    with pytest.raises(ValidationError, match="Invalid clinician role"):
        await auth_service.signup_clinician(
            email="adminlike@example.com",
            password="SecurePass123!",
            first_name="Alex",
            last_name="Reed",
            specialty="Primary Care",
            clinic_code="ABC123",
            role="admin",
        )


@pytest.mark.asyncio
async def test_signup_clinic_admin_success(auth_service, mock_supabase_client, mock_auth_client):
    signup_user = Mock()
    signup_user.id = "admin-123"
    signup_response = Mock()
    signup_response.user = signup_user
    mock_auth_client.auth.sign_up.return_value = signup_response

    login_user = Mock()
    login_user.id = "admin-123"
    login_user.email = "admin@example.com"
    login_user.created_at = "2024-01-01T00:00:00Z"
    login_user.app_metadata = {"user_role": "clinician"}

    login_session = Mock()
    login_session.access_token = "access-token-admin"
    login_session.refresh_token = "refresh-token-admin"
    login_session.expires_at = 1234567890

    login_response = Mock()
    login_response.user = login_user
    login_response.session = login_session
    mock_auth_client.auth.sign_in_with_password.return_value = login_response

    clinics_lookup = MagicMock()
    clinics_lookup.select.return_value = clinics_lookup
    clinics_lookup.eq.return_value = clinics_lookup
    clinics_lookup.execute.side_effect = [
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
    ]
    clinics_insert = MagicMock()
    clinics_insert.insert.return_value = clinics_insert
    clinics_insert.select.return_value = clinics_insert
    clinics_insert.execute.return_value = Mock(
        data=[
            {
                "id": "clinic-1",
                "code": "ABC123",
                "display_name": "City Health",
                "status": "active",
            }
        ]
    )

    clinicians_table = MagicMock()
    clinicians_insert = MagicMock()
    clinicians_insert.execute.return_value = Mock(data=[])
    clinicians_table.insert.return_value = clinicians_insert

    clinic_calls = {"count": 0}

    def table_side_effect(name):
        if name == "clinics":
            clinic_calls["count"] += 1
            if clinic_calls["count"] in {1, 3}:
                return clinics_lookup
            return clinics_insert
        return clinicians_table

    mock_supabase_client.table.side_effect = table_side_effect

    result = await auth_service.signup_clinic_admin(
        clinic_name="City Health",
        email="admin@example.com",
        password="SecurePass123!",
        first_name="Amina",
        last_name="Khan",
        specialty="Primary Care",
        type1_npi="1234567890",
        type2_npi="0987654321",
    )

    assert result["user"]["id"] == "admin-123"
    clinicians_table.insert.assert_called_once()
    inserted_payload = clinicians_table.insert.call_args.args[0]
    assert inserted_payload["role"] == "admin"


# ── Login Tests ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_success(auth_service, mock_auth_client):
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

    mock_auth_client.auth.sign_in_with_password.return_value = mock_auth_response
    auth_service._list_verified_mfa_factors = MagicMock(return_value=[])  # type: ignore[method-assign]
    auth_service._has_active_care_team = MagicMock(return_value=True)  # type: ignore[method-assign]

    # Call login
    result = await auth_service.login(email="user@example.com", password="password123")

    # Verify sign_in_with_password was called
    mock_auth_client.auth.sign_in_with_password.assert_called_once_with(
        {"email": "user@example.com", "password": "password123"}
    )

    # Verify response format
    assert result["tokens"]["access_token"] == "login-access-token"
    assert result["user"]["id"] == "user-123"
    assert result["mfa_required"] is False
    assert result["requires_clinic_join"] is False


@pytest.mark.asyncio
async def test_login_requires_mfa_for_clinician_with_verified_factor(
    auth_service, mock_auth_client
):
    mock_user = Mock()
    mock_user.id = "clinician-123"
    mock_user.email = "doctor@example.com"
    mock_user.created_at = "2024-01-01T00:00:00Z"
    mock_user.app_metadata = {"user_role": "clinician"}

    mock_session = Mock()
    mock_session.access_token = "login-access-token"
    mock_session.refresh_token = "login-refresh-token"
    mock_session.expires_at = 1234567890

    mock_auth_response = Mock()
    mock_auth_response.user = mock_user
    mock_auth_response.session = mock_session

    mock_auth_client.auth.sign_in_with_password.return_value = mock_auth_response
    auth_service._assert_clinician_can_sign_in = MagicMock(return_value=None)  # type: ignore[method-assign]
    auth_service._extract_aal = MagicMock(return_value="aal1")  # type: ignore[method-assign]
    auth_service._list_verified_mfa_factors = MagicMock(  # type: ignore[method-assign]
        return_value=[
            {
                "id": "factor-1",
                "friendly_name": "Authenticator",
                "factor_type": "totp",
                "status": "verified",
                "created_at": "2026-01-01T00:00:00Z",
            }
        ]
    )

    result = await auth_service.login(email="doctor@example.com", password="password123")

    assert result["mfa_required"] is True
    assert result["mfa_factors"][0]["id"] == "factor-1"


@pytest.mark.asyncio
async def test_login_without_clinic_code_needs_an_active_membership(auth_service, mock_auth_client):
    mock_user = Mock()
    mock_user.id = "clinician-123"
    mock_user.email = "doctor@example.com"
    mock_user.created_at = "2024-01-01T00:00:00Z"
    mock_user.app_metadata = {"user_role": "clinician"}

    mock_session = Mock()
    mock_session.access_token = "login-access-token"
    mock_session.refresh_token = "login-refresh-token"
    mock_session.expires_at = 1234567890

    mock_auth_response = Mock()
    mock_auth_response.user = mock_user
    mock_auth_response.session = mock_session

    mock_auth_client.auth.sign_in_with_password.return_value = mock_auth_response

    auth_service.clinician_repo.get_context = MagicMock(  # type: ignore[method-assign]
        return_value={"clinic_id": CLINIC_A, "clinic_name": "Heart Health Clinic"}
    )
    auth_service.memberships.active_memberships_sync = MagicMock(return_value=[])  # type: ignore[method-assign]

    with pytest.raises(AuthenticationError) as exc_info:
        await auth_service.login(email="doctor@example.com", password="password123")

    assert exc_info.value.code == "NO_ACTIVE_CLINIC"


@pytest.mark.asyncio
async def test_clinician_signs_in_once_without_a_clinic_code(auth_service, mock_auth_client):
    user = Mock(id="clinician-123", email="doctor@example.com", created_at="2024-01-01T00:00:00Z")
    user.app_metadata = {"user_role": "clinician"}
    session = Mock(access_token="a", refresh_token="r", expires_at=1234567890)
    mock_auth_client.auth.sign_in_with_password.return_value = Mock(user=user, session=session)
    auth_service.clinician_repo.get_context = MagicMock(  # type: ignore[method-assign]
        return_value={"clinic_id": CLINIC_A, "clinic_name": "Heart Health Clinic"}
    )
    auth_service.memberships.active_memberships_sync = MagicMock(  # type: ignore[method-assign]
        return_value=[_membership(CLINIC_A), _membership(CLINIC_B)]
    )
    auth_service._list_verified_mfa_factors = MagicMock(return_value=[])  # type: ignore[method-assign]
    auth_service._extract_aal = MagicMock(return_value="aal1")  # type: ignore[method-assign]

    result = await auth_service.login(email="doctor@example.com", password="password123")

    assert result["user"]["id"] == "clinician-123"
    assert result["mfa_required"] is False


@pytest.mark.asyncio
async def test_assert_clinician_matches_clinic_rejects_different_clinic(
    auth_service, mock_supabase_client
):
    clinic_query = MagicMock()
    clinic_query.select.return_value = clinic_query
    clinic_query.eq.return_value = clinic_query
    clinic_query.execute.return_value = Mock(
        data=[
            {
                "id": CLINIC_A,
                "code": "ABC123",
                "display_name": "Heart Health Clinic",
                "status": "active",
            }
        ]
    )
    mock_supabase_client.table.side_effect = [clinic_query]
    auth_service.clinician_repo.get_context = MagicMock(  # type: ignore[method-assign]
        return_value={"clinic_id": CLINIC_B, "clinic_name": "Heart Health Clinic"}
    )
    # A membership at another clinic with the same display name grants nothing here.
    auth_service.memberships.active_memberships_sync = MagicMock(  # type: ignore[method-assign]
        return_value=[_membership(CLINIC_B)]
    )

    with pytest.raises(AuthenticationError) as exc_info:
        auth_service._assert_clinician_matches_clinic("clinician-123", "ABC123")

    assert exc_info.value.message == "Clinician account does not belong to the selected clinic"
    assert exc_info.value.code == "CLINIC_CONTEXT_INVALID"


@pytest.mark.asyncio
async def test_resolve_active_clinic_uses_explicit_invalid_code(auth_service, mock_supabase_client):
    clinic_query = MagicMock()
    clinic_query.select.return_value = clinic_query
    clinic_query.eq.return_value = clinic_query
    clinic_query.execute.return_value = Mock(data=[])

    mock_supabase_client.table.return_value = clinic_query

    with pytest.raises(ValidationError) as exc_info:
        auth_service._resolve_active_clinic("INVALID")

    assert exc_info.value.message == "Clinic code is invalid"
    assert exc_info.value.code == "CLINIC_CODE_INVALID"


@pytest.mark.asyncio
async def test_resolve_active_clinic_uses_explicit_inactive_code(
    auth_service, mock_supabase_client
):
    clinic_query = MagicMock()
    clinic_query.select.return_value = clinic_query
    clinic_query.eq.return_value = clinic_query
    clinic_query.execute.return_value = Mock(
        data=[
            {
                "id": "clinic-1",
                "code": "ABC123",
                "display_name": "Heart Health Clinic",
                "status": "inactive",
            }
        ]
    )

    mock_supabase_client.table.return_value = clinic_query

    with pytest.raises(ValidationError) as exc_info:
        auth_service._resolve_active_clinic("ABC123")

    assert exc_info.value.message == "Clinic code is inactive"
    assert exc_info.value.code == "CLINIC_CODE_INACTIVE"


@pytest.mark.asyncio
async def test_assert_clinician_matches_clinic_transient_failure(
    auth_service, mock_supabase_client
):
    clinic_query = MagicMock()
    clinic_query.select.return_value = clinic_query
    clinic_query.eq.return_value = clinic_query
    clinic_query.execute.side_effect = Exception("Resource temporarily unavailable")

    mock_supabase_client.table.return_value = clinic_query

    with pytest.raises(ExternalServiceError, match="clinic lookup is temporarily unavailable"):
        auth_service._assert_clinician_matches_clinic("clinician-123", "ABC123")


@pytest.mark.asyncio
async def test_login_invalid_credentials(auth_service, mock_auth_client):
    """Test login with invalid credentials."""
    # Mock sign_in_with_password raising exception
    mock_auth_client.auth.sign_in_with_password.side_effect = Exception("Invalid login credentials")

    # Should raise AuthenticationError
    with pytest.raises(AuthenticationError, match="Invalid email or password"):
        await auth_service.login(email="wrong@example.com", password="wrongpass")


@pytest.mark.asyncio
async def test_login_rejects_unknown_role(auth_service, mock_auth_client):
    """Reject sessions that do not include a supported user_role claim."""
    mock_user = Mock()
    mock_user.id = "user-123"
    mock_user.email = "user@example.com"
    mock_user.created_at = "2024-01-01T00:00:00Z"
    mock_user.app_metadata = {}

    mock_session = Mock()
    mock_session.access_token = "login-access-token"
    mock_session.refresh_token = "login-refresh-token"
    mock_session.expires_at = 1234567890

    mock_auth_response = Mock()
    mock_auth_response.user = mock_user
    mock_auth_response.session = mock_session

    mock_auth_client.auth.sign_in_with_password.return_value = mock_auth_response

    with pytest.raises(AuthenticationError, match="invalid user role"):
        await auth_service.login(email="user@example.com", password="password123")


# ── Token Refresh Tests ───────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_token_success(auth_service, mock_auth_client):
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

    mock_auth_client.auth.refresh_session.return_value = mock_auth_response

    # Call refresh_token
    result = await auth_service.refresh_token(
        refresh_token="old-refresh-token",
        expected_role="patient",
    )

    # Verify refresh_session was called
    mock_auth_client.auth.refresh_session.assert_called_once_with("old-refresh-token")

    # Verify response format
    assert result["tokens"]["access_token"] == "new-access-token"
    assert result["tokens"]["refresh_token"] == "new-refresh-token"


@pytest.mark.asyncio
async def test_refresh_token_rejects_mismatched_role(auth_service, mock_auth_client):
    """Reject refresh responses that do not match the expected role."""
    mock_user = Mock()
    mock_user.id = "user-123"
    mock_user.email = "user@example.com"
    mock_user.created_at = "2024-01-01T00:00:00Z"
    mock_user.app_metadata = {"user_role": "clinician"}

    mock_session = Mock()
    mock_session.access_token = "new-access-token"
    mock_session.refresh_token = "new-refresh-token"
    mock_session.expires_at = 1234567890

    mock_auth_response = Mock()
    mock_auth_response.user = mock_user
    mock_auth_response.session = mock_session

    mock_auth_client.auth.refresh_session.return_value = mock_auth_response

    with pytest.raises(AuthenticationError, match="expected 'patient' role"):
        await auth_service.refresh_token(
            refresh_token="old-refresh-token",
            expected_role="patient",
        )


@pytest.mark.asyncio
async def test_refresh_token_invalid(auth_service, mock_auth_client):
    """Test token refresh with invalid token."""
    # Mock refresh_session raising exception
    mock_auth_client.auth.refresh_session.side_effect = Exception("Invalid refresh token")

    # Should raise AuthenticationError
    with pytest.raises(AuthenticationError, match="Invalid or expired refresh token"):
        await auth_service.refresh_token(refresh_token="invalid-token")


# ── Password Reset Tests ──────────────────────────────────────


@pytest.mark.asyncio
async def test_request_password_reset_success(auth_service, mock_auth_client):
    """Test successful password reset request."""
    # Mock reset_password_email
    mock_auth_client.auth.reset_password_email.return_value = None

    # Call request_password_reset (should not raise)
    await auth_service.request_password_reset(email="user@example.com")

    # Verify reset_password_email was called
    mock_auth_client.auth.reset_password_email.assert_called_once_with(
        "user@example.com", {"redirect_to": "http://localhost:3000/reset-password?lang=en-US"}
    )


@pytest.mark.asyncio
async def test_request_password_reset_email_not_found(auth_service, mock_auth_client):
    """Test password reset request for non-existent email (should not reveal)."""
    # Mock reset_password_email raising exception
    mock_auth_client.auth.reset_password_email.side_effect = Exception("User not found")

    # Should NOT raise (security: don't reveal if email exists)
    await auth_service.request_password_reset(email="nonexistent@example.com")

    # Verify reset_password_email was called
    mock_auth_client.auth.reset_password_email.assert_called_once_with(
        "nonexistent@example.com",
        {"redirect_to": "http://localhost:3000/reset-password?lang=en-US"},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("portal", "locale", "expected_url"),
    [
        ("patient", "es-MX", "https://app.example/reset-password?lang=es-MX"),
        ("clinician", "es-MX", "https://clinic.example/reset-password?lang=en-US"),
    ],
)
async def test_recovery_uses_fixed_portal_destination(
    auth_service, mock_auth_client, portal, locale, expected_url
):
    with patch("app.services.auth_service.settings") as config:
        config.patient_portal_url = "https://app.example/"
        config.clinician_portal_url = "https://clinic.example/"
        await auth_service.request_password_reset("test@example.com", portal=portal, locale=locale)
    mock_auth_client.auth.reset_password_email.assert_called_once_with(
        "test@example.com", {"redirect_to": expected_url}
    )


@pytest.mark.asyncio
async def test_recovery_failure_logs_no_identity_or_provider_payload(
    auth_service, mock_auth_client, caplog
):
    mock_auth_client.auth.reset_password_email.side_effect = Exception(
        "recipient@example.com secret-recovery-token"
    )
    await auth_service.request_password_reset("recipient@example.com")
    assert "recipient@example.com" not in caplog.text
    assert "secret-recovery-token" not in caplog.text
    assert "Password recovery delivery request failed" in caplog.text


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
    """Reject sessions with missing role metadata."""
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

    with pytest.raises(AuthenticationError, match="invalid user role"):
        auth_service._format_session(mock_response)


@pytest.mark.asyncio
async def test_format_session_uses_jwt_claim_role_when_metadata_missing(auth_service, monkeypatch):
    """Accept sessions where role exists in JWT claims but not app metadata."""
    mock_user = Mock()
    mock_user.id = "user-123"
    mock_user.email = "user@example.com"
    mock_user.created_at = "2024-01-01T00:00:00Z"
    mock_user.app_metadata = None

    mock_session = Mock()
    mock_session.access_token = "valid-jwt-token"
    mock_session.refresh_token = "refresh"
    mock_session.expires_at = 1234567890

    mock_response = Mock()
    mock_response.user = mock_user
    mock_response.session = mock_session

    monkeypatch.setattr(
        "app.services.auth_service.decode_unverified_claims",
        lambda _: {"user_role": "clinician"},
    )

    result = auth_service._format_session(mock_response, expected_role="clinician")

    assert result["user"]["role"] == "clinician"


@pytest.mark.asyncio
async def test_format_session_rejects_unsupported_jwt_claim_role(auth_service, monkeypatch):
    """Keep role validation strict even when role comes from JWT claims fallback."""
    mock_user = Mock()
    mock_user.id = "user-123"
    mock_user.email = "user@example.com"
    mock_user.created_at = "2024-01-01T00:00:00Z"
    mock_user.app_metadata = None

    mock_session = Mock()
    mock_session.access_token = "valid-jwt-token"
    mock_session.refresh_token = "refresh"
    mock_session.expires_at = 1234567890

    mock_response = Mock()
    mock_response.user = mock_user
    mock_response.session = mock_session

    monkeypatch.setattr(
        "app.services.auth_service.decode_unverified_claims",
        lambda _: {"user_role": "admin"},
    )

    with pytest.raises(AuthenticationError, match="invalid user role"):
        auth_service._format_session(mock_response)


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
    mock_session.expires_in = 3600

    mock_response = Mock()
    mock_response.user = mock_user
    mock_response.session = mock_session

    before = int(time.time())
    result = auth_service._format_session(mock_response)

    # Never 0: derived from expires_in when the provider omits expires_at
    assert before + 3600 <= result["tokens"]["expires_at"] <= int(time.time()) + 3600

    # With no expiry source at all the session is refused rather than given expiry 0
    mock_session.expires_in = None
    with pytest.raises(AuthenticationError):
        auth_service._format_session(mock_response)


# ── Invitation signup, invitation sign-in and recovery limits ─────────────────

INVITE_TOKEN = "t" * 43


def _clinician_session(user_id: str = "00000000-0000-0000-0000-0000000000aa"):
    user = Mock()
    user.id = user_id
    user.email = "invitee@example.com"
    user.created_at = "2024-01-01T00:00:00Z"
    user.app_metadata = {"user_role": "clinician"}
    session = Mock()
    session.access_token = "access"
    session.refresh_token = "refresh"
    session.expires_at = 1234567890
    response = Mock()
    response.user = user
    response.session = session
    return response


def _invitation_service(preview: dict | None = None, accept: Exception | dict | None = None):
    service = MagicMock()
    service.preview = AsyncMock(
        return_value=preview or {"email": "Invitee@Example.com", "role": "nurse"}
    )
    if isinstance(accept, Exception):
        service.accept = AsyncMock(side_effect=accept)
    else:
        service.accept = AsyncMock(
            return_value=accept
            or {
                "status": "accepted",
                "clinic": {
                    "clinic_id": "00000000-0000-0000-0000-0000000000c1",
                    "clinic_code": "ABC123",
                    "clinic_name": "Synthetic Clinic",
                    "status": "active",
                },
            }
        )
    return service


async def _invited_signup(auth_service, *, role="provider", email="invitee@example.com"):
    return await auth_service.signup_clinician(
        email=email,
        password="SecurePass123!",
        first_name="Demo",
        last_name="Invitee",
        specialty="Synthetic",
        clinic_code=None,
        role=role,
        invitation_token=INVITE_TOKEN,
    )


@pytest.mark.asyncio
async def test_invitation_signup_forces_role_and_claims_membership(
    auth_service, mock_supabase_client, mock_auth_client
):
    mock_auth_client.auth.sign_up.return_value = Mock(
        user=Mock(id="00000000-0000-0000-0000-0000000000aa")
    )
    mock_auth_client.auth.sign_in_with_password.return_value = _clinician_session()
    invitations = _invitation_service()
    with patch("app.services.auth_service.EmailInvitationService", return_value=invitations):
        result = await _invited_signup(auth_service, role="admin")
    row = mock_supabase_client.table.return_value.insert.call_args.args[0]
    # The requested role is ignored; membership comes only from the claimed invitation.
    assert row["clinic_id"] is None and row["role"] == "provider"
    mock_supabase_client.table.assert_called_once_with("clinicians")
    invitations.accept.assert_awaited_once()
    assert invitations.accept.await_args.kwargs["address"] == "invitee@example.com"
    assert result["invitation_status"] == "accepted"
    assert result["clinic"]["clinic_code"] == "ABC123"


@pytest.mark.asyncio
async def test_invitation_signup_rejects_other_address(auth_service, mock_auth_client):
    invitations = _invitation_service(preview={"email": "someone@example.com", "role": "nurse"})
    with (
        patch("app.services.auth_service.EmailInvitationService", return_value=invitations),
        pytest.raises(ValidationError, match="this invitation was sent to"),
    ):
        await _invited_signup(auth_service)
    mock_auth_client.auth.sign_up.assert_not_called()


@pytest.mark.asyncio
async def test_invitation_signup_admin_role_comes_from_invitation(
    auth_service, mock_supabase_client, mock_auth_client
):
    mock_auth_client.auth.sign_up.return_value = Mock(
        user=Mock(id="00000000-0000-0000-0000-0000000000aa")
    )
    mock_auth_client.auth.sign_in_with_password.return_value = _clinician_session()
    invitations = _invitation_service(preview={"email": "invitee@example.com", "role": "admin"})
    with patch("app.services.auth_service.EmailInvitationService", return_value=invitations):
        result = await _invited_signup(auth_service)
    assert result["invitation_status"] == "accepted"


@pytest.mark.asyncio
async def test_invitation_claim_failure_keeps_account(
    auth_service, mock_supabase_client, mock_auth_client
):
    mock_auth_client.auth.sign_up.return_value = Mock(
        user=Mock(id="00000000-0000-0000-0000-0000000000aa")
    )
    mock_auth_client.auth.sign_in_with_password.return_value = _clinician_session()
    invitations = _invitation_service(accept=ExternalServiceError("Email", "down"))
    with patch("app.services.auth_service.EmailInvitationService", return_value=invitations):
        result = await _invited_signup(auth_service)
    assert result["invitation_status"] == "pending"
    assert result["tokens"]["access_token"] == "access"
    mock_supabase_client.auth.admin.delete_user.assert_not_called()


@pytest.mark.asyncio
async def test_invitation_sign_in_accepts_and_ends_temporary_session(
    auth_service, mock_auth_client
):
    mock_auth_client.auth.sign_in_with_password.return_value = _clinician_session()
    auth_service._list_verified_mfa_factors = MagicMock(return_value=[])  # type: ignore[method-assign]
    invitations = _invitation_service()
    with patch("app.services.auth_service.EmailInvitationService", return_value=invitations):
        result = await auth_service.accept_invitation_with_password(
            email="invitee@example.com", password="pw", invitation_token=INVITE_TOKEN
        )
    assert result["clinic"]["clinic_name"] == "Synthetic Clinic"
    # The address is read from Auth by the service, not taken from the request.
    assert "address" not in invitations.accept.await_args.kwargs
    mock_auth_client.auth.sign_out.assert_called_once_with({"scope": "local"})


@pytest.mark.asyncio
async def test_invitation_sign_in_rejects_patient_accounts(auth_service, mock_auth_client):
    session = _clinician_session()
    session.user.app_metadata = {"user_role": "patient"}
    mock_auth_client.auth.sign_in_with_password.return_value = session
    with pytest.raises(AuthenticationError):
        await auth_service.accept_invitation_with_password(
            email="invitee@example.com", password="pw", invitation_token=INVITE_TOKEN
        )


def test_unassigned_clinician_login_points_to_invitation(auth_service, mock_supabase_client):
    clinic_query = MagicMock()
    clinic_query.select.return_value = clinic_query
    clinic_query.eq.return_value = clinic_query
    clinic_query.execute.return_value = Mock(
        data=[{"id": "clinic-1", "code": "ABC123", "display_name": "Clinic", "status": "active"}]
    )
    clinician_query = MagicMock()
    clinician_query.select.return_value = clinician_query
    clinician_query.eq.return_value = clinician_query
    clinician_query.single.return_value = clinician_query
    clinician_query.execute.return_value = Mock(data={"clinic_id": None, "clinic_name": None})
    mock_supabase_client.table.side_effect = [clinic_query, clinician_query]
    auth_service.memberships.active_memberships_sync = MagicMock(return_value=[])  # type: ignore[method-assign]
    with pytest.raises(AuthenticationError) as raised:
        auth_service._assert_clinician_matches_clinic("clinician-123", "ABC123")
    assert raised.value.code == "INVITATION_ACCEPTANCE_REQUIRED"


@pytest.mark.asyncio
async def test_clinician_signup_refuses_an_address_that_already_has_an_account(
    auth_service, mock_supabase_client, mock_auth_client
):
    clinic_query = MagicMock()
    clinic_query.select.return_value = clinic_query
    clinic_query.eq.return_value = clinic_query
    clinic_query.execute.return_value = Mock(
        data=[{"id": CLINIC_A, "code": "ABC123", "display_name": "Clinic", "status": "active"}]
    )
    mock_supabase_client.table.side_effect = [clinic_query]
    with (
        patch(
            "app.services.auth_service.ClinicianRepository.list_by_email_any_case",
            return_value=[{"id": "existing"}],
        ),
        pytest.raises(ValidationError) as raised,
    ):
        await auth_service.signup_clinician(
            email="doctor@example.com",
            password="SecurePass123!",
            first_name="Dana",
            last_name="Doe",
            specialty="Cardiology",
            clinic_code="ABC123",
        )
    assert raised.value.code == "ACCOUNT_EXISTS"
    mock_auth_client.auth.sign_up.assert_not_called()


@pytest.mark.asyncio
async def test_invitation_password_accept_needs_sign_in_for_mfa_account_with_a_clinic(
    auth_service, mock_auth_client
):
    mock_auth_client.auth.sign_in_with_password.return_value = _clinician_session()
    auth_service._list_verified_mfa_factors = MagicMock(return_value=[{"id": "factor-1"}])  # type: ignore[method-assign]
    auth_service.memberships.active_memberships_sync = MagicMock(  # type: ignore[method-assign]
        return_value=[_membership(CLINIC_A)]
    )
    invitations = _invitation_service()
    with (
        patch("app.services.auth_service.EmailInvitationService", return_value=invitations),
        pytest.raises(AuthenticationError) as raised,
    ):
        await auth_service.accept_invitation_with_password(
            email="invitee@example.com", password="pw", invitation_token=INVITE_TOKEN
        )
    assert raised.value.code == "SIGN_IN_TO_ACCEPT"
    invitations.accept.assert_not_awaited()
    mock_auth_client.auth.sign_out.assert_called_once_with({"scope": "local"})


@pytest.mark.asyncio
async def test_invitation_password_accept_still_needs_the_code_for_mfa_without_a_clinic(
    auth_service, mock_auth_client
):
    mock_auth_client.auth.sign_in_with_password.return_value = _clinician_session()
    auth_service._list_verified_mfa_factors = MagicMock(return_value=[{"id": "factor-1"}])  # type: ignore[method-assign]
    auth_service.memberships.active_memberships_sync = MagicMock(return_value=[])  # type: ignore[method-assign]
    invitations = _invitation_service()
    with (
        patch("app.services.auth_service.EmailInvitationService", return_value=invitations),
        pytest.raises(AuthenticationError) as raised,
    ):
        await auth_service.accept_invitation_with_password(
            email="invitee@example.com", password="pw", invitation_token=INVITE_TOKEN
        )
    assert raised.value.code == "MFA_CODE_REQUIRED"
    invitations.accept.assert_not_awaited()


@pytest.mark.asyncio
async def test_password_reset_limits_stay_neutral(auth_service, mock_auth_client, caplog):
    for _ in range(5):
        await auth_service.request_password_reset("Repeat@Example.com", client="203.0.113.5")
    assert mock_auth_client.auth.reset_password_email.call_count == 3
    assert "Repeat@Example.com".lower() not in caplog.text.lower()
    assert "rate limited (address)" in caplog.text


@pytest.mark.asyncio
async def test_password_reset_limits_per_client(auth_service, mock_auth_client):
    for index in range(25):
        await auth_service.request_password_reset(f"user{index}@example.com", client="203.0.113.9")
    assert mock_auth_client.auth.reset_password_email.call_count == 20
