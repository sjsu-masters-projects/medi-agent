"""Every CronService run writes the same two lines as the run it records."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import pytest

from app.services import cron_service as module
from app.services.cron_service import CronJobAlreadyRunningError
from tests.unit.services.cron_store import DAY, Store, add_medication, service_for


@pytest.fixture
def store() -> Store:
    return Store()


@pytest.mark.asyncio
async def test_a_dispatch_logs_the_same_summary_and_window_it_records(
    store: Store, job_logs
) -> None:
    add_medication(store, "med-1")
    store.now = DAY + timedelta(hours=7, minutes=50)
    result = await service_for(store).dispatch_reminders(window_minutes=15)

    started, finished = job_logs.lines
    [run] = store.tables["cron_job_runs"]
    assert started["event"] == "scheduled_job.started"
    assert started["job"] == finished["job"] == "reminders_dispatch"
    assert started["run_id"] == finished["run_id"] == run["id"] == result["run_id"]
    assert started["parameters"] == {"dry_run": False, "window_minutes": 15}
    assert finished["status"] == "success" and finished["severity"] == "INFO"
    assert finished["dry_run"] is False
    assert finished["summary"] == run["summary"] == result["summary"]
    assert finished["summary"]["window_start"] == (DAY + timedelta(hours=7, minutes=50)).isoformat()
    assert finished["summary"]["medication_created"] == 1


@pytest.mark.asyncio
async def test_a_failed_dispatch_is_recorded_and_logged_without_its_message(
    store: Store, job_logs, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = service_for(store)

    async def explode(**_: Any) -> dict[str, int]:
        raise RuntimeError("Synthetic Patient missed metformin at 08:00")

    monkeypatch.setattr(service, "_dispatch_schedule_reminders", explode)
    with pytest.raises(RuntimeError):
        await service.dispatch_reminders()

    [run] = store.tables["cron_job_runs"]
    assert run["status"] == "failed"
    started, finished = job_logs.lines
    assert finished["status"] == "failed" and finished["severity"] == "ERROR"
    assert finished["run_id"] == run["id"]
    assert finished["error_type"] == "RuntimeError"
    assert "metformin" not in json.dumps(finished)
    assert finished["summary"] == run["summary"]


@pytest.mark.asyncio
async def test_a_run_already_in_progress_is_logged_as_skipped(store: Store, job_logs) -> None:
    store.tables["cron_job_runs"] = [
        {
            "id": "running",
            "job_name": "reminders_dispatch",
            "status": "running",
            "started_at": DAY.isoformat(),
        }
    ]
    store.now = DAY + timedelta(minutes=5)
    with pytest.raises(CronJobAlreadyRunningError):
        await service_for(store).dispatch_reminders()

    [line] = job_logs.lines
    assert line["status"] == "skipped" and line["severity"] == "WARNING"
    assert line["reason"] == "already_running" and line["run_id"] is None
    assert len(store.tables["cron_job_runs"]) == 1


@pytest.mark.asyncio
async def test_a_refresh_with_failed_subjects_is_a_failed_run(
    store: Store, job_logs, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def refresh_due(_self: Any, *, limit: int) -> dict[str, Any]:
        return {"subjects_total": 4, "subjects_checked": 3, "subjects_failed": 2}

    monkeypatch.setattr(module.HealthKnowledgeService, "refresh_due", refresh_due)
    result = await service_for(store).run_health_knowledge_refresh(limit=10)

    assert result["status"] == "failed"
    [run] = store.tables["cron_job_runs"]
    assert run["status"] == "failed" and run["error"] == "2 reference subjects failed"
    started, finished = job_logs.lines
    assert started["parameters"] == {"limit": 10}
    assert finished["status"] == "failed" and finished["severity"] == "ERROR"
    assert finished["reason"] == "2 reference subjects failed"
    assert finished["summary"] == run["summary"] == result["summary"]


@pytest.mark.asyncio
async def test_a_refresh_that_checks_nothing_is_a_success(
    store: Store, job_logs, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def refresh_due(_self: Any, *, limit: int) -> dict[str, Any]:
        return {
            "subjects_total": 21,
            "subjects_due": 0,
            "subjects_checked": 0,
            "subjects_failed": 0,
            "next_due_at": "2026-10-17T08:00:31+00:00",
        }

    monkeypatch.setattr(module.HealthKnowledgeService, "refresh_due", refresh_due)
    result = await service_for(store).run_health_knowledge_refresh(limit=10)

    assert result["status"] == "success"
    finished = job_logs.lines[-1]
    assert finished["status"] == "success"
    assert finished["summary"]["next_due_at"] == "2026-10-17T08:00:31+00:00"


class _Delivery:
    """Stands in for EmailDeliveryService so no provider or database is touched."""

    calls: list[str] = []
    result: dict[str, int] | Exception = {}

    def __init__(self, _db: Any) -> None:
        pass

    async def dispatch(self) -> dict[str, int]:
        _Delivery.calls.append("dispatch")
        if isinstance(_Delivery.result, Exception):
            raise _Delivery.result
        return dict(_Delivery.result)

    async def pending(self) -> dict[str, int]:
        _Delivery.calls.append("pending")
        return {"due": 2, "awaiting_status": 1}


@pytest.fixture
def delivery(monkeypatch: pytest.MonkeyPatch) -> type[_Delivery]:
    _Delivery.calls, _Delivery.result = [], {"claimed": 1, "accepted": 1, "errors": 0}
    monkeypatch.setattr(module, "EmailDeliveryService", _Delivery)
    return _Delivery


@pytest.mark.asyncio
async def test_email_dispatch_has_its_own_run_record_and_log(
    store: Store, job_logs, delivery
) -> None:
    result = await service_for(store).dispatch_emails()
    [run] = store.tables["cron_job_runs"]
    started, finished = job_logs.lines
    assert started["job"] == finished["job"] == run["job_name"] == "email_dispatch"
    assert finished["status"] == "success" and finished["summary"]["accepted"] == 1
    assert result["summary"] == run["summary"]


@pytest.mark.asyncio
async def test_email_dry_run_only_counts(store: Store, job_logs, delivery) -> None:
    result = await service_for(store).dispatch_emails(dry_run=True)
    assert delivery.calls == ["pending"]
    assert result["dry_run"] is True and result["summary"] == {"due": 2, "awaiting_status": 1}


@pytest.mark.asyncio
async def test_deferred_rows_mark_the_email_run_failed(store: Store, job_logs, delivery) -> None:
    delivery.result = {"claimed": 2, "accepted": 1, "errors": 1}
    result = await service_for(store).dispatch_emails()
    assert result["status"] == "failed"
    assert job_logs.lines[-1]["reason"] == "1 email rows deferred"


@pytest.mark.asyncio
async def test_email_failure_after_reminders_is_isolated(
    store: Store, job_logs, delivery, caplog
) -> None:
    delivery.result = TimeoutError("owner@example.com provider timeout")
    service = service_for(store)
    await service.dispatch_emails_isolated()
    [run] = store.tables["cron_job_runs"]
    assert run["job_name"] == "email_dispatch" and run["status"] == "failed"
    finished = job_logs.lines[-1]
    assert finished["error_type"] == "TimeoutError"
    assert "owner@example.com" not in json.dumps(finished)
    assert "owner@example.com" not in caplog.text
