"""Unit tests for CronService orchestration."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.cron_service import CronService


@pytest.fixture
def cron_service():
    return CronService(db=None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_dispatch_reminders_summarizes_created_notifications(monkeypatch, cron_service):
    started_at = datetime.now(timezone.utc).isoformat()

    async def _noop(*args, **kwargs):
        return None

    async def _start_run(*args, **kwargs):
        return {"id": "run-123", "started_at": started_at}

    async def _finish_run(*args, **kwargs):
        return {"finished_at": started_at}

    async def _dispatch(*, reminder_kind, **kwargs):
        if reminder_kind == "24h":
            return {"candidates": 2, "created": 1, "existing": 1}
        return {"candidates": 1, "created": 1, "existing": 0}

    monkeypatch.setattr(cron_service, "_ensure_job_not_running", _noop)
    monkeypatch.setattr(cron_service, "_start_run", _start_run)
    monkeypatch.setattr(cron_service, "_finish_run", _finish_run)
    monkeypatch.setattr(cron_service, "_dispatch_appointment_reminders", _dispatch)

    result = await cron_service.dispatch_reminders(dry_run=False, window_minutes=15)

    assert result["job_name"] == "reminders_dispatch"
    assert result["summary"]["appointment_24h_created"] == 1
    assert result["summary"]["appointment_1h_created"] == 1
    assert result["summary"]["medication_candidates"] == 0


@pytest.mark.asyncio
async def test_run_nightly_adr_scan_flags_candidates(monkeypatch, cron_service):
    started_at = datetime.now(timezone.utc).isoformat()
    symptom_rows = [
        {
            "id": "symptom-1",
            "patient_id": "patient-1",
            "severity": 7,
            "related_medication_id": None,
            "created_at": started_at,
        },
        {
            "id": "symptom-2",
            "patient_id": "patient-2",
            "severity": 3,
            "related_medication_id": "med-9",
            "created_at": started_at,
        },
    ]
    flagged_ids: list[list[str]] = []

    async def _noop(*args, **kwargs):
        return None

    async def _start_run(*args, **kwargs):
        return {"id": "run-adr", "started_at": started_at}

    async def _finish_run(*args, **kwargs):
        return {"finished_at": started_at}

    async def _fetch_symptoms(*args, **kwargs):
        return symptom_rows

    async def _fetch_active_med_map(*args, **kwargs):
        return {"patient-1": [{"id": "med-1"}]}

    async def _flag(symptom_ids):
        flagged_ids.append(symptom_ids)

    async def _resolve_since(*args, **kwargs):
        return cron_service._utc_now()

    monkeypatch.setattr(cron_service, "_ensure_job_not_running", _noop)
    monkeypatch.setattr(cron_service, "_start_run", _start_run)
    monkeypatch.setattr(cron_service, "_finish_run", _finish_run)
    monkeypatch.setattr(cron_service, "_resolve_adr_scan_since", _resolve_since)
    monkeypatch.setattr(cron_service, "_fetch_symptom_reports_for_adr_scan", _fetch_symptoms)
    monkeypatch.setattr(cron_service, "_fetch_active_medication_map", _fetch_active_med_map)
    monkeypatch.setattr(cron_service, "_flag_symptom_reports_for_adr", _flag)

    result = await cron_service.run_nightly_adr_scan(
        dry_run=False,
        lookback_hours=24,
        limit=500,
    )

    assert result["job_name"] == "nightly_adr_scan"
    assert result["summary"]["candidate_flags_created"] == 2
    assert flagged_ids == [["symptom-1", "symptom-2"]]
