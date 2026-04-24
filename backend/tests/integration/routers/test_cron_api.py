"""Integration tests for internal cron API endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import status

from app.config import settings
from app.main import app
from app.routers.cron import _get_service


@pytest.fixture
def cron_auth_token():
    original = settings.cron_auth_token
    settings.cron_auth_token = "test-cron-token"
    yield "test-cron-token"
    settings.cron_auth_token = original


@pytest.fixture
def mock_cron_service():
    return AsyncMock()


@pytest.fixture
def override_cron_service(mock_cron_service):
    app.dependency_overrides[_get_service] = lambda: mock_cron_service
    yield
    app.dependency_overrides.clear()


def _sample_response(job_name: str) -> dict[str, object]:
    timestamp = datetime.now(timezone.utc).isoformat()
    return {
        "run_id": str(uuid4()),
        "job_name": job_name,
        "status": "success",
        "dry_run": False,
        "started_at": timestamp,
        "finished_at": timestamp,
        "summary": {"processed": 1},
    }


class TestReminderDispatchCron:
    def test_rejects_without_auth_header(self, client, cron_auth_token):
        response = client.post("/api/v1/cron/reminders/dispatch")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_dispatches_with_auth_header(
        self, client, cron_auth_token, mock_cron_service, override_cron_service
    ):
        mock_cron_service.dispatch_reminders.return_value = _sample_response(
            "reminders_dispatch"
        )

        response = client.post(
            "/api/v1/cron/reminders/dispatch",
            headers={"X-Cron-Auth": cron_auth_token},
            json={"dry_run": True, "window_minutes": 30},
        )

        assert response.status_code == status.HTTP_200_OK
        payload = response.json()
        assert payload["job_name"] == "reminders_dispatch"
        mock_cron_service.dispatch_reminders.assert_awaited_once_with(
            dry_run=True,
            window_minutes=30,
        )


class TestNightlyAdrCron:
    def test_runs_with_auth_header(
        self, client, cron_auth_token, mock_cron_service, override_cron_service
    ):
        mock_cron_service.run_nightly_adr_scan.return_value = _sample_response(
            "nightly_adr_scan"
        )

        response = client.post(
            "/api/v1/cron/adr/nightly-scan",
            headers={"X-Cron-Auth": cron_auth_token},
            json={"dry_run": True, "lookback_hours": 48, "limit": 250},
        )

        assert response.status_code == status.HTTP_200_OK
        payload = response.json()
        assert payload["job_name"] == "nightly_adr_scan"
        mock_cron_service.run_nightly_adr_scan.assert_awaited_once_with(
            dry_run=True,
            lookback_hours=48,
            limit=250,
        )
