from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ValidationError
from app.services.reminder_schedule_service import ReminderScheduleService


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "frequency,days,times",
    [
        ("three times per week", ["monday", "wednesday"], ["08:00"]),
        ("three times per week", ["monday", "wednesday", "friday"], ["08:00", "20:00"]),
        ("twice daily", ["monday"], ["08:00", "20:00"]),
        (
            "twice daily",
            ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
            ["08:00"],
        ),
        ("as needed", ["monday"], ["08:00"]),
    ],
)
async def test_reminder_preferences_cannot_reduce_or_increase_known_cadence(frequency, days, times):
    db = MagicMock()
    service = ReminderScheduleService(db)
    service._assert_target_belongs_to_patient = AsyncMock(
        return_value={"id": "target", "frequency": frequency}
    )
    with pytest.raises(ValidationError):
        await service.upsert_schedule(
            "patient",
            "obligation",
            "target",
            {"timezone": "America/Los_Angeles", "days_of_week": days, "times_of_day": times},
        )
    db.table.assert_not_called()


@pytest.mark.asyncio
async def test_matching_three_day_schedule_is_saved(monkeypatch):
    service = ReminderScheduleService(MagicMock())
    service._assert_target_belongs_to_patient = AsyncMock(
        return_value={"id": "target", "frequency": "three times per week"}
    )
    service.get_schedule_map_for_patient = AsyncMock(return_value={})
    execute = AsyncMock(return_value=MagicMock(data=[{"id": "schedule"}]))
    monkeypatch.setattr("app.services.reminder_schedule_service.execute_async", execute)
    result = await service.upsert_schedule(
        "patient",
        "obligation",
        "target",
        {
            "timezone": "America/Los_Angeles",
            "days_of_week": ["monday", "wednesday", "friday"],
            "times_of_day": ["08:00"],
        },
    )
    assert result["id"] == "schedule"
    execute.assert_awaited_once()
