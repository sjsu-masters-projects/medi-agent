"""Read-only publication snapshots share Today rendering and fail closed."""

from copy import deepcopy
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from app.core.exceptions import AuthorizationError, ValidationError
from app.models.care_plan import CarePlanTodayPreviewRead
from app.services.care_plan_preview_service import (
    CarePlanPreviewService,
    PublicationRecords,
    proposed_records,
)
from app.services.feed_service import FeedService, FeedSnapshot

PATIENT = UUID("00000000-0000-0000-0000-000000000201")
CLINICIAN = UUID("00000000-0000-0000-0000-000000000202")
PLAN = UUID("00000000-0000-0000-0000-000000000203")


def activity(**changes):
    return {
        "id": "new-item",
        "source_fact_id": "fact",
        "category": "movement",
        "title": "Walk",
        "instructions": "Walk 20 minutes",
        "frequency": "daily",
        "schedule": {},
        "reviewed_locale": "en-US",
        **changes,
    }


def records():
    old = activity(id="old-item", projection_type="obligation", projection_id="activity")
    canonical = {
        "id": "activity",
        "care_plan_item_id": "old-item",
        "description": "Walk",
        "notes": "Walk 20 minutes",
        "frequency": "daily",
        "obligation_type": "exercise",
    }
    return PublicationRecords([], [canonical], [old])


def test_exact_activity_keeps_identity_and_does_not_mutate_inputs():
    original = records()
    before = deepcopy(original)
    result = proposed_records([activity()], original)
    assert result.obligations[0]["id"] == "activity"
    assert result.obligations[0]["care_plan_item_id"] == "new-item"
    assert original == before


@pytest.mark.parametrize(
    "change",
    [
        {"source_fact_id": "different"},
        {"title": "Changed"},
        {"instructions": "Changed"},
        {"frequency": "twice daily"},
        {"schedule": {"start_date": "2026-11-01"}},
        {"category": "other"},
        {"source_fact_id": None},
    ],
)
def test_changed_activity_gets_no_previous_reminder_or_completion_identity(change):
    result = proposed_records([activity(**change)], records())
    assert result.obligations[0]["id"] != "activity"
    UUID(result.obligations[0]["id"])


@pytest.mark.parametrize("drift", ["notes", "obligation_type", "care_plan_item_id"])
def test_canonical_drift_prevents_continuity(drift):
    snapshot = records()
    snapshot.obligations[0][drift] = "Changed"
    proposed = proposed_records([activity()], snapshot)
    new = next(row for row in proposed.obligations if row["care_plan_item_id"] == "new-item")
    assert new["id"] != "activity"


def test_ambiguous_previous_matches_do_not_inherit_activity():
    snapshot = records()
    snapshot.previous_items.append(dict(snapshot.previous_items[0]))
    assert proposed_records([activity()], snapshot).obligations[0]["id"] != "activity"


def test_removed_items_and_superseded_records_disappear_but_legacy_records_remain():
    snapshot = records()
    snapshot.obligations.append({"id": "legacy", "care_plan_item_id": None})
    result = proposed_records([activity(is_removed=True)], snapshot)
    assert [row["id"] for row in result.obligations] == ["legacy"]


def test_medication_update_retains_identity_and_provider_without_duplicates():
    snapshot = PublicationRecords(
        [
            {
                "id": "med",
                "name": "Metformin",
                "dosage": "500 mg",
                "care_plan_item_id": "old",
                "care_teams": {"id": "provider"},
            },
            {"id": "legacy", "name": "Other", "care_plan_item_id": None},
        ],
        [],
        [{"id": "old"}],
    )
    item = activity(
        category="medication",
        medication={
            "decision": "update",
            "target_id": "med",
            "name": "Metformin",
            "dosage": "1000 mg",
            "frequency": "daily",
        },
    )
    result = proposed_records([item], snapshot)
    assert [row["id"] for row in result.medications] == ["legacy", "med"]
    assert result.medications[1]["dosage"] == "1000 mg"
    assert result.medications[1]["care_teams"] == {"id": "provider"}


def test_new_medication_has_preview_only_identity():
    item = activity(
        category="medication",
        medication={
            "decision": "create",
            "name": "Synthetic med",
            "dosage": "1 mg",
            "frequency": "daily",
        },
    )
    result = proposed_records([item], PublicationRecords([], [], []))
    UUID(result.medications[0]["id"])
    assert result.medications[0]["care_plan_item_id"] == "new-item"


def test_preview_uses_today_dates_reminders_adherence_and_effective_dates():
    rows = proposed_records([activity()], records())
    reminder = {
        "target_type": "obligation",
        "target_id": "activity",
        "timezone": "America/Los_Angeles",
        "times_of_day": ["08:00"],
        "days_of_week": [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ],
        "is_enabled": True,
    }
    feed = FeedService(MagicMock())
    metadata = {
        "new-item": {
            "version_number": 2,
            "category": "movement",
            "schedule": {"start_date": "2026-10-03"},
        }
    }
    snapshot = FeedSnapshot(
        date(2026, 10, 2),
        "America/Los_Angeles",
        [],
        rows.obligations,
        metadata,
        {("obligation", "activity"): reminder},
    )
    assert feed.render_snapshot(snapshot)["tasks"] == []
    metadata["new-item"]["schedule"] = {}
    result = feed.render_snapshot(snapshot)
    assert result["date"] == "2026-10-02"
    assert result["timezone"] == "America/Los_Angeles"
    assert result["tasks"][0]["care_plan"]["version_number"] == 2
    assert result["tasks"][0]["scheduled_at"] == "2026-10-02T15:00:00+00:00"
    snapshot.adherence = [
        {
            "target_type": "obligation",
            "target_id": "activity",
            "status": "completed",
            "logged_at": "2026-10-02T15:00:00+00:00",
            "scheduled_time": "2026-10-02T15:00:00+00:00",
        }
    ]
    assert feed.render_snapshot(snapshot)["tasks"][0]["status"] == "completed"


def preview_service():
    service = CarePlanPreviewService(MagicMock())
    item = activity(id=str(PATIENT))
    service.plans.publication_snapshot = MagicMock(return_value=({"version_number": 2}, [item]))
    service.plans._plans = MagicMock(return_value=[])
    service.db.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value.data = []
    service.feed._get_patient = AsyncMock(return_value={"timezone": "America/Los_Angeles"})
    service.feed._get_medications = AsyncMock(return_value=[])
    service.feed._get_obligations = AsyncMock(return_value=[])
    service.feed._get_today_adherence = AsyncMock(return_value=[])
    return service


@pytest.mark.asyncio
async def test_denied_assignment_precedes_all_feed_reads():
    service = preview_service()
    service.plans.publication_snapshot.side_effect = AuthorizationError("Not assigned")
    with pytest.raises(AuthorizationError):
        await service.preview(CLINICIAN, PATIENT, PLAN)
    service.feed._get_patient.assert_not_called()
    service.db.table.assert_not_called()
    service.db.rpc.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"blocker_reason": "Needs review"},
        {"instructions": ""},
        {"is_removed": True},
        {"schedule": {"start_date": "not-a-date"}},
        {"schedule": {"start_date": "2026-10-03", "end_date": "2026-10-02"}},
    ],
)
async def test_incomplete_saved_review_cannot_preview(change):
    service = preview_service()
    service.plans.publication_snapshot.return_value[1][0].update(change)
    with pytest.raises(ValidationError):
        await service.preview(CLINICIAN, PATIENT, PLAN)
    service.feed._get_patient.assert_not_called()
    service.db.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_read_failure_is_not_presented_as_an_empty_preview():
    service = preview_service()
    service.feed._get_medications.side_effect = RuntimeError("Read unavailable")
    with pytest.raises(RuntimeError, match="Read unavailable"):
        await service.preview(CLINICIAN, PATIENT, PLAN)
    service.db.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_newly_present_matching_medication_blocks_create_preview():
    service = preview_service()
    item = service.plans.publication_snapshot.return_value[1][0]
    item.update(
        category="medication",
        medication={
            "decision": "create",
            "name": "Metformin",
            "dosage": "500 mg",
            "frequency": "daily",
            "route": "oral",
        },
    )
    service.feed._get_medications.return_value = [{"id": "med", "name": "Metformin"}]
    with pytest.raises(ValidationError, match="already exists"):
        await service.preview(CLINICIAN, PATIENT, PLAN)
    service.db.rpc.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("getter", ["_get_medications", "_get_obligations", "_get_today_adherence"])
async def test_strict_feed_reads_propagate_failures(getter):
    db = MagicMock()
    db.table.side_effect = RuntimeError("Read unavailable")
    service = FeedService(db)
    args = (PATIENT, date(2026, 10, 2), "UTC") if getter == "_get_today_adherence" else (PATIENT,)
    with pytest.raises(RuntimeError, match="Read unavailable"):
        await getattr(service, getter)(*args, strict=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("patient", [None, {"timezone": None}, {"timezone": "invalid-zone"}])
async def test_preview_never_substitutes_utc_for_missing_patient_timezone(patient):
    db = MagicMock()
    db.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value.data = patient
    with pytest.raises(ValidationError):
        await FeedService(db)._get_patient(PATIENT, strict=True)


@pytest.mark.asyncio
async def test_valid_preview_performs_no_publication_or_writes():
    service = preview_service()
    with patch("app.services.care_plan_preview_service.ReminderScheduleService") as reminders:
        reminders.return_value.get_schedule_map_for_patient = AsyncMock(return_value={})
        result = await service.preview(CLINICIAN, PATIENT, PLAN)
    CarePlanTodayPreviewRead.model_validate(result)
    assert result["feed"]["tasks"][0]["requires_schedule_configuration"]
    service.db.rpc.assert_not_called()
    assert not any(
        call[0].endswith(("update", "insert", "delete", "upsert")) for call in service.db.mock_calls
    )
    service.feed._get_medications.assert_awaited_once_with(PATIENT, strict=True)
