"""Reminder schedule queries and occurrence helpers."""

from __future__ import annotations

import logging
import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from supabase import Client

from app.core.exceptions import NotFoundError, ValidationError
from app.db.supabase_execute import execute_async

logger = logging.getLogger(__name__)

DAY_ORDER = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]
DAY_SET = set(DAY_ORDER)
DEFAULT_TIME_SUGGESTIONS = ["08:00:00", "20:00:00", "12:00:00", "21:00:00"]


def validate_timezone_name(value: str) -> str:
    """Validate and normalize an IANA timezone identifier."""
    normalized = value.strip()
    if not normalized:
        raise ValidationError("Timezone is required")
    try:
        ZoneInfo(normalized)
    except ZoneInfoNotFoundError:
        raise ValidationError("Timezone must be a valid IANA timezone") from None
    return normalized


def normalize_time_of_day(value: str) -> str:
    """Normalize `HH:MM` / `HH:MM:SS` inputs to `HH:MM:SS`."""
    raw = value.strip()
    if not raw:
        raise ValidationError("Reminder times cannot be empty")
    if re.fullmatch(r"\d{2}:\d{2}", raw):
        raw = f"{raw}:00"
    if not re.fullmatch(r"\d{2}:\d{2}:\d{2}", raw):
        raise ValidationError("Reminder times must use HH:MM format")
    hours, minutes, seconds = (int(part) for part in raw.split(":"))
    try:
        time(hours, minutes, seconds)
    except ValueError:
        raise ValidationError("Reminder times must be valid clock values") from None
    return raw


def normalize_days_of_week(days: list[str]) -> list[str]:
    """Normalize stored days and preserve Monday..Sunday order."""
    normalized = []
    for day in days:
        value = day.strip().lower()
        if value not in DAY_SET:
            raise ValidationError("Reminder days must be valid weekday names")
        normalized.append(value)
    seen: set[str] = set()
    deduped = []
    for day in DAY_ORDER:
        if day in normalized and day not in seen:
            seen.add(day)
            deduped.append(day)
    return deduped


def infer_frequency_guidance(frequency: str) -> dict[str, Any]:
    """Infer scheduling guidance from a human-readable regimen frequency."""
    value = frequency.strip().lower()
    if not value:
        return {
            "supports_automatic_reminders": True,
            "recommended_times_per_day": None,
            "recommended_days_per_week": None,
            "guidance_text": "Add reminder times that match your care plan.",
        }
    if "as needed" in value or "prn" in value:
        return {
            "supports_automatic_reminders": False,
            "recommended_times_per_day": 0,
            "recommended_days_per_week": None,
            "guidance_text": "As-needed items should not create automatic reminders by default.",
        }
    if "every 8 hour" in value:
        return {
            "supports_automatic_reminders": True,
            "recommended_times_per_day": 3,
            "recommended_days_per_week": 7,
            "guidance_text": "Use three evenly spaced reminder times that fit the prescribed interval.",
        }
    if "3x per week" in value or "three times per week" in value:
        return {
            "supports_automatic_reminders": True,
            "recommended_times_per_day": 1,
            "recommended_days_per_week": 3,
            "guidance_text": "Choose which three days of the week to receive this reminder.",
        }
    if "weekly" in value:
        return {
            "supports_automatic_reminders": True,
            "recommended_times_per_day": 1,
            "recommended_days_per_week": 1,
            "guidance_text": "Choose the day of week and time that best fits the weekly plan.",
        }
    if "with each meal" in value or "with meals" in value:
        return {
            "supports_automatic_reminders": True,
            "recommended_times_per_day": 3,
            "recommended_days_per_week": 7,
            "guidance_text": "Set breakfast, lunch, and dinner reminder times that match your routine.",
        }
    if "three times daily" in value or "3x daily" in value:
        return {
            "supports_automatic_reminders": True,
            "recommended_times_per_day": 3,
            "recommended_days_per_week": 7,
            "guidance_text": "Set three reminder times across the day.",
        }
    if "twice daily" in value or "2x daily" in value or "two times daily" in value:
        return {
            "supports_automatic_reminders": True,
            "recommended_times_per_day": 2,
            "recommended_days_per_week": 7,
            "guidance_text": "Set two reminder times, usually one earlier and one later in the day.",
        }
    if "before bed" in value:
        return {
            "supports_automatic_reminders": True,
            "recommended_times_per_day": 1,
            "recommended_days_per_week": 7,
            "guidance_text": "Choose the time you usually wind down for the night.",
        }
    if "daily" in value:
        return {
            "supports_automatic_reminders": True,
            "recommended_times_per_day": 1,
            "recommended_days_per_week": 7,
            "guidance_text": "Choose one daily reminder time.",
        }
    return {
        "supports_automatic_reminders": True,
        "recommended_times_per_day": None,
        "recommended_days_per_week": None,
        "guidance_text": "Confirm the timing with your clinician, then choose reminder times that match your routine.",
    }


def generate_default_times(count: int | None) -> list[str]:
    """Return simple starter times for the patient UI."""
    if not count or count <= 0:
        return []
    if count <= len(DEFAULT_TIME_SUGGESTIONS):
        return DEFAULT_TIME_SUGGESTIONS[:count]
    return DEFAULT_TIME_SUGGESTIONS + ["23:00:00"] * (count - len(DEFAULT_TIME_SUGGESTIONS))


def occurrence_datetimes_for_day(
    schedule: dict[str, Any],
    target_date: date,
) -> list[tuple[str, str]]:
    """Return `(utc_iso, local_time_str)` occurrences for a local calendar day."""
    if not schedule.get("is_enabled", True):
        return []

    times = [normalize_time_of_day(str(value)) for value in schedule.get("times_of_day") or []]
    if not times:
        return []

    days = normalize_days_of_week(list(schedule.get("days_of_week") or DAY_ORDER))
    current_day = DAY_ORDER[target_date.weekday()]
    if current_day not in days:
        return []

    timezone_name = validate_timezone_name(str(schedule.get("timezone") or "UTC"))
    tz = ZoneInfo(timezone_name)
    occurrences: list[tuple[str, str]] = []
    for value in times:
        local_time = time.fromisoformat(value)
        local_dt = datetime.combine(target_date, local_time, tzinfo=tz)
        occurrences.append((local_dt.astimezone(UTC).isoformat(), value))
    return occurrences


def count_occurrences_in_period(
    schedule: dict[str, Any],
    start_date: date,
    end_date: date,
) -> int:
    """Count occurrences between two local dates inclusive."""
    total = 0
    current = start_date
    while current <= end_date:
        total += len(occurrence_datetimes_for_day(schedule, current))
        current += timedelta(days=1)
    return total


class ReminderScheduleService:
    """Patient-owned reminder schedules for medications and obligations."""

    def __init__(self, db: Client) -> None:
        self.db = db

    async def list_targets_for_patient(self, patient_id: str) -> list[dict[str, Any]]:
        patient = await self._get_patient(patient_id)
        schedule_map = await self.get_schedule_map_for_patient(patient_id)
        provider_by_team = await self._get_provider_name_map(patient_id)
        medications, obligations = await self._get_active_targets(patient_id)

        targets: list[dict[str, Any]] = []
        for medication in medications:
            schedule = schedule_map.get(("medication", str(medication["id"])))
            guidance = infer_frequency_guidance(str(medication.get("frequency") or ""))
            targets.append(
                {
                    "target_type": "medication",
                    "target_id": medication["id"],
                    "name": medication.get("name", ""),
                    "description": medication.get("instructions"),
                    "frequency": medication.get("frequency", ""),
                    "provider_name": provider_by_team.get(
                        str(medication.get("prescribed_by_care_team_id") or "")
                    ),
                    "reminder_schedule": schedule,
                    "guidance": guidance,
                }
            )

        for obligation in obligations:
            schedule = schedule_map.get(("obligation", str(obligation["id"])))
            guidance = infer_frequency_guidance(str(obligation.get("frequency") or ""))
            targets.append(
                {
                    "target_type": "obligation",
                    "target_id": obligation["id"],
                    "name": obligation.get("description", ""),
                    "description": obligation.get("notes"),
                    "frequency": obligation.get("frequency", ""),
                    "provider_name": provider_by_team.get(
                        str(obligation.get("set_by_care_team_id") or "")
                    ),
                    "reminder_schedule": schedule,
                    "guidance": guidance,
                }
            )

        for target in targets:
            schedule = target.get("reminder_schedule")
            if schedule is None and patient.get("timezone"):
                target["guidance"]["default_timezone"] = patient["timezone"]
        return targets

    async def upsert_schedule(
        self,
        patient_id: str,
        target_type: str,
        target_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        await self._assert_target_belongs_to_patient(patient_id, target_type, target_id)
        timezone_name = validate_timezone_name(str(payload.get("timezone") or "UTC"))
        times_of_day = sorted(
            {normalize_time_of_day(str(value)) for value in list(payload.get("times_of_day") or [])}
        )
        if not times_of_day:
            raise ValidationError("Add at least one reminder time")
        days_of_week = normalize_days_of_week(list(payload.get("days_of_week") or DAY_ORDER))

        schedule_map = await self.get_schedule_map_for_patient(patient_id)
        existing = schedule_map.get((target_type, target_id))
        row = {
            "patient_id": patient_id,
            "target_type": target_type,
            "target_id": target_id,
            "timezone": timezone_name,
            "times_of_day": times_of_day,
            "days_of_week": days_of_week,
            "is_enabled": bool(payload.get("is_enabled", True)),
        }

        if existing:
            response = await execute_async(
                self,
                lambda db: (
                    db.table("reminder_schedules")
                    .update(cast(Any, row))
                    .eq("id", str(existing["id"]))
                ),
                operation="update reminder schedule",
                retry_transient=True,
            )
        else:
            response = await execute_async(
                self,
                lambda db: db.table("reminder_schedules").insert(cast(Any, row)),
                operation="create reminder schedule",
                retry_transient=True,
            )
        updated = (response.data or [None])[0]
        if updated is None:
            raise ValidationError("Failed to save reminder schedule")
        return cast(dict[str, Any], updated)

    async def delete_schedule(self, patient_id: str, target_type: str, target_id: str) -> None:
        await self._assert_target_belongs_to_patient(patient_id, target_type, target_id)
        await execute_async(
            self,
            lambda db: (
                db.table("reminder_schedules")
                .delete()
                .eq("patient_id", patient_id)
                .eq("target_type", target_type)
                .eq("target_id", target_id)
            ),
            operation="delete reminder schedule",
            retry_transient=True,
        )

    async def get_schedule_map_for_patient(
        self, patient_id: str
    ) -> dict[tuple[str, str], dict[str, Any]]:
        response = await execute_async(
            self,
            lambda db: (
                db.table("reminder_schedules")
                .select("*")
                .eq("patient_id", patient_id)
                .eq("is_enabled", True)
            ),
            operation="fetch patient reminder schedules",
            retry_transient=True,
        )
        return {
            (str(row["target_type"]), str(row["target_id"])): row
            for row in list(response.data or [])
        }

    async def _get_patient(self, patient_id: str) -> dict[str, Any]:
        response = await execute_async(
            self,
            lambda db: db.table("patients").select("id, timezone").eq("id", patient_id).single(),
            operation="fetch patient timezone",
            retry_transient=True,
        )
        if not response.data:
            raise NotFoundError("Patient", patient_id)
        return cast(dict[str, Any], response.data)

    async def _get_provider_name_map(self, patient_id: str) -> dict[str, str]:
        response = await execute_async(
            self,
            lambda db: (
                db.table("care_teams")
                .select("id, clinicians(first_name, last_name)")
                .eq("patient_id", patient_id)
                .eq("status", "active")
            ),
            operation="fetch reminder providers",
            retry_transient=True,
        )
        provider_by_team: dict[str, str] = {}
        for team in list(response.data or []):
            clinician = team.get("clinicians") or {}
            first = str(clinician.get("first_name") or "").strip()
            last = str(clinician.get("last_name") or "").strip()
            name = " ".join(part for part in [first, last] if part).strip()
            if team.get("id") and name:
                provider_by_team[str(team["id"])] = f"Dr. {name}"
        return provider_by_team

    async def _get_active_targets(
        self, patient_id: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        meds_response = await execute_async(
            self,
            lambda db: (
                db.table("medications")
                .select("id, name, frequency, instructions, prescribed_by_care_team_id, is_active")
                .eq("patient_id", patient_id)
                .eq("is_active", True)
                .order("created_at", desc=True)
            ),
            operation="fetch active medications for reminders",
            retry_transient=True,
        )
        obligations_response = await execute_async(
            self,
            lambda db: (
                db.table("obligations")
                .select("id, description, notes, frequency, set_by_care_team_id, is_active")
                .eq("patient_id", patient_id)
                .eq("is_active", True)
                .order("created_at", desc=True)
            ),
            operation="fetch active obligations for reminders",
            retry_transient=True,
        )
        return list(meds_response.data or []), list(obligations_response.data or [])

    async def _assert_target_belongs_to_patient(
        self, patient_id: str, target_type: str, target_id: str
    ) -> None:
        if target_type not in {"medication", "obligation"}:
            raise ValidationError("Target type must be medication or obligation")
        table = "medications" if target_type == "medication" else "obligations"
        response = await execute_async(
            self,
            lambda db: (
                db.table(table)
                .select("id")
                .eq("id", target_id)
                .eq("patient_id", patient_id)
                .eq("is_active", True)
                .limit(1)
            ),
            operation=f"validate {target_type} reminder target",
            retry_transient=True,
        )
        if not response.data:
            raise ValidationError(f"{target_type.capitalize()} not found for this patient")
