"""Tests for MFAService — TOTP enrollment, verification, and management."""

from unittest.mock import MagicMock, Mock, patch

import jwt
import pytest

from app.core.exceptions import AuthenticationError, ValidationError
from app.services.mfa_service import MFAService


@pytest.fixture
def service():
    return MFAService()


@pytest.fixture
def mock_client():
    """A mock Supabase client with auth.mfa methods."""
    client = MagicMock()
    client.auth.mfa = MagicMock()
    return client


# ── enroll ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enroll_success(service, mock_client):
    mock_response = Mock()
    mock_response.id = "factor-123"
    mock_response.totp.qr_code = "data:image/png;base64,abc"
    mock_response.totp.secret = "JBSWY3DPEHPK3PXP"
    mock_response.totp.uri = "otpauth://totp/MediAgent?secret=JBSWY3DPEHPK3PXP"
    mock_client.auth.mfa.enroll.return_value = mock_response

    with patch.object(MFAService, "_user_client", return_value=mock_client):
        result = await service.enroll("token-abc", "refresh-abc", "My App")

    assert result["factor_id"] == "factor-123"
    assert result["totp"]["qr_code"] == "data:image/png;base64,abc"
    assert result["friendly_name"] == "My App"


@pytest.mark.asyncio
async def test_enroll_failure(service, mock_client):
    mock_client.auth.mfa.enroll.side_effect = Exception("enroll error")

    with (
        patch.object(MFAService, "_user_client", return_value=mock_client),
        pytest.raises(ValidationError, match="enrollment failed"),
    ):
        await service.enroll("token-abc", "refresh-abc")


# ── verify ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_success(service, mock_client):
    mock_challenge = Mock()
    mock_challenge.id = "challenge-1"
    mock_client.auth.mfa.challenge.return_value = mock_challenge

    mock_verify = Mock()
    mock_verify.access_token = "new-access"
    mock_verify.refresh_token = "new-refresh"
    mock_verify.expires_at = 1234567890
    mock_client.auth.mfa.verify.return_value = mock_verify

    with patch.object(MFAService, "_user_client", return_value=mock_client):
        result = await service.verify("token-abc", "refresh-abc", "factor-123", "123456")

    assert result["access_token"] == "new-access"
    assert result["expires_at"] == 1234567890
    assert result["token_type"] == "bearer"
    mock_client.auth.mfa.challenge.assert_called_once_with({"factor_id": "factor-123"})
    mock_client.auth.mfa.verify.assert_called_once_with(
        {"factor_id": "factor-123", "challenge_id": "challenge-1", "code": "123456"}
    )


@pytest.mark.asyncio
async def test_verify_invalid_code(service, mock_client):
    mock_client.auth.mfa.challenge.side_effect = Exception("bad code")

    with (
        patch.object(MFAService, "_user_client", return_value=mock_client),
        pytest.raises(AuthenticationError, match="Invalid verification code"),
    ):
        await service.verify("token-abc", "refresh-abc", "factor-123", "000000")


# ── list_factors ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_factors_success(service, mock_client):
    factor = Mock()
    factor.id = "factor-1"
    factor.friendly_name = "My Phone"
    factor.factor_type = "totp"
    factor.status = "verified"
    factor.created_at = "2025-01-01T00:00:00Z"

    mock_response = Mock()
    mock_response.totp = [factor]
    mock_client.auth.mfa.list_factors.return_value = mock_response

    with patch.object(MFAService, "_user_client", return_value=mock_client):
        result = await service.list_factors("token-abc", "refresh-abc")

    assert len(result) == 1
    assert result[0]["id"] == "factor-1"
    assert result[0]["status"] == "verified"


@pytest.mark.asyncio
async def test_list_factors_empty(service, mock_client):
    mock_response = Mock()
    mock_response.totp = []
    mock_client.auth.mfa.list_factors.return_value = mock_response

    with patch.object(MFAService, "_user_client", return_value=mock_client):
        result = await service.list_factors("token-abc", "refresh-abc")

    assert result == []


@pytest.mark.asyncio
async def test_list_factors_failure(service, mock_client):
    mock_client.auth.mfa.list_factors.side_effect = Exception("api error")

    with (
        patch.object(MFAService, "_user_client", return_value=mock_client),
        pytest.raises(ValidationError, match="Could not list"),
    ):
        await service.list_factors("token-abc", "refresh-abc")


# ── unenroll ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unenroll_success(service, mock_client):
    mock_client.auth.mfa.unenroll.return_value = None

    with patch.object(MFAService, "_user_client", return_value=mock_client):
        result = await service.unenroll("token-abc", "refresh-abc", "factor-123")

    assert result["status"] == "removed"
    assert result["factor_id"] == "factor-123"


@pytest.mark.asyncio
async def test_unenroll_failure(service, mock_client):
    mock_client.auth.mfa.unenroll.side_effect = Exception("not found")

    with (
        patch.object(MFAService, "_user_client", return_value=mock_client),
        pytest.raises(ValidationError, match="Could not remove"),
    ):
        await service.unenroll("token-abc", "refresh-abc", "factor-999")


def test_extract_expires_at_reads_jwt_claim():
    token = jwt.encode({"exp": 2234567890}, "test-secret-at-least-32-bytes-long", algorithm="HS256")
    assert MFAService._extract_expires_at(token) == 2234567890
