from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ValidationError
from app.services.reminder_schedule_service import (
    DAY_ORDER,
    ReminderScheduleService,
    infer_frequency_guidance,
    schedule_matches_frequency,
)


@pytest.mark.parametrize(
    "frequency,times",
    [
        ("Each day before breakfast", ["08:00"]),
        ("with breakfast and dinner", ["08:00", "18:00"]),
    ],
)
def test_explicit_daily_routines_support_matching_reminders(frequency, times):
    assert schedule_matches_frequency({"times_of_day": times, "days_of_week": DAY_ORDER}, frequency)


def test_explicit_weekdays_cannot_be_replaced_with_other_three_days():
    frequency = "Monday, Wednesday, and Friday after dinner"
    schedule = {"times_of_day": ["18:00"], "days_of_week": ["monday", "wednesday", "friday"]}
    assert schedule_matches_frequency(schedule, frequency)
    schedule["days_of_week"] = ["tuesday", "thursday", "saturday"]
    assert not schedule_matches_frequency(schedule, frequency)


@pytest.mark.parametrize(
    "frequency,english",
    [
        ("todos los días", "daily"),
        ("Dos veces al día", "twice daily"),
        ("tres veces al día", "three times daily"),
        ("todos los días antes del desayuno", "each day before breakfast"),
        ("con el desayuno y la cena", "with breakfast and dinner"),
        ("los lunes, miércoles y viernes", "Monday, Wednesday, and Friday"),
        (
            "lunes / miércoles / viernes después de cenar",
            "Monday / Wednesday / Friday after dinner",
        ),
    ],
)
def test_supported_spanish_cadence_matches_english_semantics(frequency, english):
    assert infer_frequency_guidance(frequency) == infer_frequency_guidance(english)


@pytest.mark.parametrize(
    "frequency",
    [
        "diariamente si hay sintomas",
        "después de cada sesión de ejercicio",
        "cada dos semanas",
        "cuatro veces al día",
        "lunes o viernes",
        "según sea necesario",
    ],
)
def test_ambiguous_spanish_is_not_silently_scheduled(frequency):
    assert not infer_frequency_guidance(frequency)["supports_automatic_reminders"]


def test_spanish_interval_still_requires_even_spacing():
    assert schedule_matches_frequency(
        {"times_of_day": ["06:00", "14:00", "22:00"], "days_of_week": DAY_ORDER},
        "cada 8 horas",
    )
    assert not schedule_matches_frequency(
        {"times_of_day": ["08:00", "12:00", "20:00"], "days_of_week": DAY_ORDER},
        "cada 8 horas",
    )


@pytest.mark.parametrize(
    "frequency",
    [
        "biweekly",
        "twice weekly",
        "four times daily",
        "daily after each exercise session",
        "as-needed",
        "as recorded",
    ],
)
def test_unclear_or_event_frequency_is_not_a_routine(frequency):
    assert infer_frequency_guidance(frequency)["supports_automatic_reminders"] is False


@pytest.mark.parametrize(
    "times,valid", [(["06:00", "14:00", "22:00"], True), (["08:00", "12:00", "20:00"], False)]
)
def test_interval_reminders_preserve_the_eight_hour_interval(times, valid):
    assert (
        schedule_matches_frequency(
            {"times_of_day": times, "days_of_week": DAY_ORDER}, "every 8 hours"
        )
        is valid
    )


@pytest.mark.parametrize(
    "times,days",
    [
        (["08:00", "20:00"], DAY_ORDER),
        (["08:00", "08:00"], DAY_ORDER),
        (["08:00"], ["monday"]),
        (["bad"], DAY_ORDER),
    ],
)
def test_legacy_daily_schedule_with_wrong_cadence_is_not_effective(times, days):
    assert (
        schedule_matches_frequency({"times_of_day": times, "days_of_week": days}, "daily") is False
    )


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
        ("as-needed rescue use", ["monday"], ["08:00"]),
        ("as recorded", ["monday"], ["08:00"]),
        ("", ["monday"], ["08:00"]),
        ("once after each walking session", ["monday"], ["08:00"]),
        ("after walking daily", ["monday"], ["08:00"]),
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
