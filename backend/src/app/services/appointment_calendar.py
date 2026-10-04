"""One-time RFC 5545 exports; no clinical notes, invitations, or calendar sync."""

import re
from datetime import UTC, datetime, timedelta
from typing import Literal

from app.core.exceptions import ValidationError
from app.models.appointment import AppointmentCalendarExport, AppointmentRead

CalendarLocale = Literal["en-US", "es-MX"]

_COPY = {
    "en-US": (
        "MediAgent appointment",
        "This is a one-time calendar copy. Changes and cancellations do not sync. "
        "Check MediAgent for the latest appointment details.",
    ),
    "es-MX": (
        "Cita de MediAgent",
        "Esta es una copia del calendario. Los cambios y las cancelaciones no se sincronizan. "
        "Consulta MediAgent para ver los datos actuales de la cita.",
    ),
}


def _escape(value: str) -> str:
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
    return (
        value.replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def _fold(line: str) -> str:
    """Fold at 75 UTF-8 octets without splitting a code point (RFC 5545 §3.1)."""
    lines: list[str] = []
    current = ""
    size = 0
    for char in line:
        width = len(char.encode("utf-8"))
        if size + width > 75:
            lines.append(current)
            current, size = " ", 1
        current += char
        size += width
    return "\r\n".join([*lines, current])


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def render_appointment_calendar(
    appointment: AppointmentRead, locale: CalendarLocale
) -> AppointmentCalendarExport:
    start = appointment.scheduled_at
    if start.tzinfo is None or not 5 <= appointment.duration_minutes <= 480:
        raise ValidationError("Appointment time is unavailable", code="APPOINTMENT_UNAVAILABLE")
    title, notice = _COPY[locale]
    end = start.astimezone(UTC) + timedelta(minutes=appointment.duration_minutes)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MediAgent//Appointments//EN",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:appointment-{appointment.id}@mediagent.live",
        f"DTSTAMP:{_utc(datetime.now(UTC))}",
        f"DTSTART:{_utc(start)}",
        f"DTEND:{_utc(end)}",
        "STATUS:CONFIRMED",
        "CLASS:PRIVATE",
        f"SUMMARY;LANGUAGE={locale}:{_escape(title)}",
        f"DESCRIPTION;LANGUAGE={locale}:{_escape(notice)}",
    ]
    if appointment.location:
        lines.append(f"LOCATION:{_escape(appointment.location)}")
    lines.extend(["END:VEVENT", "END:VCALENDAR"])
    return AppointmentCalendarExport(
        filename=f"appointment-{appointment.id}.ics",
        content="\r\n".join(_fold(line) for line in lines) + "\r\n",
    )
