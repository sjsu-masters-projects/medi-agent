"""RFC 5545 boundaries independent of portal/browser timezone."""

from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from app.core.exceptions import ValidationError
from app.models.appointment import AppointmentRead
from app.services.appointment_calendar import render_appointment_calendar


def appointment(**values):
    return AppointmentRead.model_validate(
        {
            "id": str(uuid4()),
            "patient_id": str(uuid4()),
            "care_team_id": str(uuid4()),
            "scheduled_at": "2026-10-06T16:00:00Z",
            "duration_minutes": 30,
            "appointment_type": "follow_up",
            "status": "confirmed",
            "created_at": "2026-10-03T00:00:00Z",
            **values,
        }
    )


@pytest.mark.parametrize("locale", ["en-US", "es-MX"])
@pytest.mark.parametrize(
    "value,expected,local",
    [
        ("2026-01-15T18:00:00Z", "20260115T180000Z", "2026-01-15T10:00:00-08:00"),
        ("2026-07-15T17:00:00Z", "20260715T170000Z", "2026-07-15T10:00:00-07:00"),
        ("2026-07-16T01:00:00Z", "20260716T010000Z", "2026-07-15T18:00:00-07:00"),
        ("2026-07-15T10:00:00-07:00", "20260715T170000Z", "2026-07-15T10:00:00-07:00"),
    ],
)
def test_exact_instant_and_local_date(value, expected, local, locale):
    content = render_appointment_calendar(appointment(scheduled_at=value), locale).content
    assert f"DTSTART:{expected}\r\n" in content
    parsed = datetime.strptime(expected, "%Y%m%dT%H%M%SZ").replace(tzinfo=ZoneInfo("UTC"))
    assert parsed.astimezone(ZoneInfo("America/Los_Angeles")).isoformat() == local
    assert "TZID" not in content  # UTC instants cannot depend on the exporting browser's zone.


@pytest.mark.parametrize(
    "start,end",
    [
        ("2026-03-08T01:45:00-08:00", "20260308T101500Z"),
        ("2026-11-01T01:45:00-07:00", "20261101T091500Z"),
        ("2026-10-06T23:45:00Z", "20261007T001500Z"),
    ],
)
def test_elapsed_duration_across_dst_and_midnight(start, end):
    content = render_appointment_calendar(appointment(scheduled_at=start), "en-US").content
    assert f"DTEND:{end}\r\n" in content


def test_text_injection_utf8_folding_and_stable_identity():
    row = appointment(
        location="Clínica 🩺; sala, 2\\3\r\nBEGIN:VALARM\rACTION:DISPLAY\x00 " + "México 🩺" * 30
    )
    first = render_appointment_calendar(row, "es-MX").content
    second = render_appointment_calendar(row, "en-US").content
    for line in first.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75
    unfolded = first.replace("\r\n ", "")
    assert "LOCATION:Clínica 🩺\\; sala\\, 2\\\\3\\nBEGIN:VALARM\\nACTION:DISPLAY " in unfolded
    assert "\r\nBEGIN:VALARM" not in unfolded and "\x00" not in first
    assert first.startswith("BEGIN:VCALENDAR\r\n") and first.endswith("END:VCALENDAR\r\n")
    assert f"UID:appointment-{row.id}@mediagent.live\r\n" in first
    assert f"UID:appointment-{row.id}@mediagent.live\r\n" in second


@pytest.mark.parametrize(
    "values",
    [{"scheduled_at": "2026-10-06T09:00:00"}, {"duration_minutes": 0}, {"duration_minutes": 481}],
)
def test_invalid_times_not_exported(values):
    with pytest.raises(ValidationError):
        render_appointment_calendar(appointment(**values), "en-US")
