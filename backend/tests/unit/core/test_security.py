"""Tests for JWT role enforcement and MFA gating."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi.security import HTTPAuthorizationCredentials

from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import _has_verified_mfa_factor, require_role
from app.models.auth import CurrentUser


@pytest.mark.asyncio
async def test_has_verified_mfa_factor_returns_true_when_factor_exists():
    response = MagicMock()
    response.json.return_value = [{"id": "factor-1"}]
    response.raise_for_status.return_value = None

    client = AsyncMock()
    client.get.return_value = response

    with patch("app.core.security.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value = client
        assert await _has_verified_mfa_factor("access-token") is True


@pytest.mark.asyncio
async def test_has_verified_mfa_factor_maps_http_errors_to_authentication_error():
    client = AsyncMock()
    client.get.side_effect = httpx.ConnectError("boom")

    with patch("app.core.security.httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value = client
        with pytest.raises(AuthenticationError, match="Unable to determine MFA status"):
            await _has_verified_mfa_factor("access-token")


@pytest.mark.asyncio
async def test_require_role_blocks_clinician_with_verified_factor_and_aal1():
    dependency = require_role("clinician")
    user = CurrentUser(id=uuid4(), email="doc@test.com", role="clinician", aal="aal1")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="access-token")

    with patch("app.core.security._has_verified_mfa_factor", AsyncMock(return_value=True)):
        with pytest.raises(
            AuthorizationError,
            match="MFA verification required before accessing clinician resources",
        ):
            await dependency(user=user, credentials=credentials)


@pytest.mark.asyncio
async def test_require_role_allows_clinician_without_verified_factor_and_aal1():
    dependency = require_role("clinician")
    user = CurrentUser(id=uuid4(), email="doc@test.com", role="clinician", aal="aal1")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="access-token")

    with patch("app.core.security._has_verified_mfa_factor", AsyncMock(return_value=False)):
        result = await dependency(user=user, credentials=credentials)

    assert result == user


@pytest.mark.asyncio
async def test_require_role_allows_mfa_routes_to_accept_unverified_session():
    dependency = require_role("clinician", allow_unverified_mfa=True)
    user = CurrentUser(id=uuid4(), email="doc@test.com", role="clinician", aal="aal1")
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="access-token")

    with patch("app.core.security._has_verified_mfa_factor", AsyncMock()) as has_factor:
        result = await dependency(user=user, credentials=credentials)

    has_factor.assert_not_awaited()
    assert result == user
