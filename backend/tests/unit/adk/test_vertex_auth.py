"""Credentials that stay current for longer than one token's lifetime."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.clients.vertex_auth import google_adc_bearer


def _credentials(*, valid: bool = True, token: str = "token-0") -> MagicMock:
    credentials = MagicMock()
    credentials.valid = valid
    credentials.token = token
    return credentials


def test_a_valid_credential_is_not_refreshed() -> None:
    credentials = _credentials()

    with patch("google.auth.default", return_value=(credentials, "p")):
        bearer = google_adc_bearer()

    assert bearer() == "token-0"
    credentials.refresh.assert_not_called()


def test_an_expired_credential_is_refreshed_before_use() -> None:
    """The failure this exists to prevent: an hour-old token ending a long run."""
    credentials = _credentials(valid=False, token="stale")

    def refresh(_request: object) -> None:
        credentials.valid = True
        credentials.token = "fresh"

    credentials.refresh.side_effect = refresh

    with patch("google.auth.default", return_value=(credentials, "p")):
        bearer = google_adc_bearer()

    # The startup check already found it expired and refreshed it.
    assert credentials.refresh.call_count == 1
    # The refreshed token is the one handed out, not the stale one it was built with.
    assert bearer() == "fresh"
    # And a credential that is now valid is not refreshed again on every call.
    assert credentials.refresh.call_count == 1


def test_credentials_are_resolved_at_construction_not_first_use() -> None:
    """A provider that builds fine and fails every call reads as a model outage."""
    with (
        patch("google.auth.default", side_effect=RuntimeError("no ADC on this machine")),
        pytest.raises(RuntimeError, match="no ADC"),
    ):
        google_adc_bearer()


def test_the_cloud_platform_scope_is_requested() -> None:
    credentials = _credentials()

    with patch("google.auth.default", return_value=(credentials, "p")) as default:
        google_adc_bearer()

    assert default.call_args.kwargs["scopes"] == ["https://www.googleapis.com/auth/cloud-platform"]
