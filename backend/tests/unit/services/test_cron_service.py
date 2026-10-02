"""Unit tests for CronService orchestration."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.services.cron_service import CronService


@pytest.fixture
def cron_service():
    return CronService(db=None)  # type: ignore[arg-type]


@pytest.mark.parametrize("kind", ["medication", "obligation"])
@pytest.mark.parametrize(
    "frequency", ["as-needed", "as recorded", "once after each walking session", ""]
)
def test_legacy_unsafe_schedule_cannot_create_a_notification(cron_service, kind, frequency):
    schedule = {
        "target_type": kind,
        "target_id": "synthetic",
        "timezone": "UTC",
        "times_of_day": ["08:00"],
        "days_of_week": ["monday"],
    }
    targets = {"synthetic": {"frequency": frequency}}
    result = cron_service._build_schedule_notification_candidates(
        schedule=schedule,
        medication_map=targets if kind == "medication" else {},
        obligation_map=targets if kind == "obligation" else {},
        window_start=datetime(2026, 9, 28, 8, tzinfo=UTC),
        window_end=datetime(2026, 9, 28, 9, tzinfo=UTC),
    )
    assert result == []


@pytest.mark.parametrize("kind", ["medication", "obligation"])
def test_matching_daily_schedule_still_creates_one_candidate(cron_service, kind):
    from app.services.reminder_schedule_service import DAY_ORDER

    schedule = {
        "patient_id": "synthetic-patient",
        "target_type": kind,
        "target_id": "synthetic",
        "timezone": "UTC",
        "times_of_day": ["08:00"],
        "days_of_week": DAY_ORDER,
    }
    targets = {
        "synthetic": {
            "frequency": "daily",
            "name": "Synthetic medication",
            "description": "Synthetic activity",
        }
    }
    result = cron_service._build_schedule_notification_candidates(
        schedule=schedule,
        medication_map=targets if kind == "medication" else {},
        obligation_map=targets if kind == "obligation" else {},
        window_start=datetime(2026, 9, 28, 8, tzinfo=UTC),
        window_end=datetime(2026, 9, 28, 9, tzinfo=UTC),
    )
    assert len(result) == 1
    assert result[0]["metadata"]["target_id"] == "synthetic"
    assert result[0]["metadata"]["scheduled_at"] == "2026-09-28T08:00:00+00:00"


@pytest.mark.asyncio
async def test_dispatch_reminders_summarizes_created_notifications(monkeypatch, cron_service):
    started_at = datetime.now(UTC).isoformat()

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
    started_at = datetime.now(UTC).isoformat()
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
