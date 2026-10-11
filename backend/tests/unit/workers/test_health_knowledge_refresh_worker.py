"""The weekly refresh Job exits non-zero exactly when the run failed."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services.cron_service import CronJobAlreadyRunningError
from app.workers import health_knowledge_refresh as worker


def _run_returns(monkeypatch: pytest.MonkeyPatch, outcome: Any) -> None:
    async def run(_self: Any, *, limit: int) -> dict[str, Any]:
        assert limit == worker.REFRESH_LIMIT
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr(worker, "get_admin_client", MagicMock())
    monkeypatch.setattr(worker.CronService, "run_health_knowledge_refresh", run)


@pytest.mark.asyncio
async def test_a_successful_run_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    _run_returns(monkeypatch, {"status": "success", "summary": {}})
    assert await worker.main() == 0


@pytest.mark.asyncio
async def test_a_run_with_failed_subjects_exits_non_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    _run_returns(monkeypatch, {"status": "failed", "summary": {"subjects_failed": 1}})
    assert await worker.main() == 1


@pytest.mark.asyncio
async def test_an_exception_exits_non_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    _run_returns(monkeypatch, RuntimeError("database unavailable"))
    assert await worker.main() == 1


@pytest.mark.asyncio
async def test_a_run_already_in_progress_is_not_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _run_returns(monkeypatch, CronJobAlreadyRunningError(worker.JOB_NAME))
    assert await worker.main() == 0


@pytest.mark.asyncio
async def test_no_database_client_is_logged_and_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch, job_logs
) -> None:
    monkeypatch.setattr(
        worker, "get_admin_client", MagicMock(side_effect=RuntimeError("SUPABASE_URL=secret"))
    )
    assert await worker.main() == 1
    [line] = job_logs.lines
    assert line["job"] == worker.JOB_NAME and line["severity"] == "ERROR"
    assert line["reason"] == "run_not_recorded"
    assert "secret" not in json.dumps(line)
