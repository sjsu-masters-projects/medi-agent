"""Read-only proposed Today snapshots; publication remains a separate transaction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5
from zoneinfo import ZoneInfo

from supabase import Client

from app.core.exceptions import ValidationError
from app.services.care_plan_service import CarePlanService
from app.services.feed_service import FeedService, FeedSnapshot
from app.services.reminder_schedule_service import ReminderScheduleService


@dataclass
class PublicationRecords:
    medications: list[dict[str, Any]]
    obligations: list[dict[str, Any]]
    previous_items: list[dict[str, Any]]
    provider: dict[str, Any] | None = None


def obligation_type(category: str) -> str:
    return {"nutrition": "diet", "movement": "exercise"}.get(category, "custom")


def unchanged_activity(item: dict[str, Any], records: PublicationRecords) -> dict[str, Any] | None:
    """Mirror migration 045: retain identity only for one exact canonical match."""
    matches: list[dict[str, Any]] = []
    for old in records.previous_items:
        if old.get("is_removed") or old.get("projection_type") != "obligation":
            continue
        if not item.get("source_fact_id") or any(
            old.get(key) != item.get(key)
            for key in (
                "source_fact_id",
                "category",
                "title",
                "instructions",
                "frequency",
                "schedule",
            )
        ):
            continue
        matches.extend(
            row
            for row in records.obligations
            if (
                str(row["id"]) == str(old.get("projection_id"))
                and str(row.get("care_plan_item_id")) == str(old["id"])
                and row.get("description") == old["title"]
                and row.get("notes") == old["instructions"]
                and row.get("frequency") == old["frequency"]
                and row.get("obligation_type") == obligation_type(old["category"])
            )
        )
    return matches[0] if len(matches) == 1 else None


def proposed_records(
    items: list[dict[str, Any]], records: PublicationRecords
) -> PublicationRecords:
    """Project into copies only. New IDs are preview-only, not future record IDs."""
    previous_ids = {str(item["id"]) for item in records.previous_items}
    medications = [
        dict(row)
        for row in records.medications
        if str(row.get("care_plan_item_id")) not in previous_ids
    ]
    obligations = [
        dict(row)
        for row in records.obligations
        if str(row.get("care_plan_item_id")) not in previous_ids
    ]
    for item in items:
        if item.get("is_removed"):
            continue
        preview_id = str(uuid5(NAMESPACE_URL, f"care-plan-preview:{item['id']}"))
        if item["category"] == "medication":
            medication = item["medication"]
            target = next(
                (
                    row
                    for row in records.medications
                    if str(row["id"]) == str(medication.get("target_id"))
                ),
                None,
            )
            if medication["decision"] == "update" and target is None:
                raise ValidationError("Medication update target changed; refresh the review")
            row = (
                dict(target)
                if medication["decision"] == "update" and target
                else {"id": preview_id, "care_teams": records.provider}
            )
            row.update(
                name=medication["name"],
                dosage=medication["dosage"],
                frequency=medication["frequency"],
                instructions=item["instructions"],
                care_plan_item_id=item["id"],
            )
            medications = [
                existing for existing in medications if str(existing["id"]) != str(row["id"])
            ]
            medications.append(row)
        else:
            previous = unchanged_activity(item, records)
            row = dict(previous) if previous else {"id": preview_id, "care_teams": records.provider}
            row.update(
                description=item["title"],
                notes=item["instructions"],
                frequency=item["frequency"],
                obligation_type=obligation_type(item["category"]),
                care_plan_item_id=item["id"],
            )
            obligations.append(row)
    return PublicationRecords(medications, obligations, [])


class CarePlanPreviewService:
    def __init__(self, db: Client) -> None:
        self.db = db
        self.plans = CarePlanService(db)
        self.feed = FeedService(db)

    async def preview(self, clinician_id: UUID, patient_id: UUID, plan_id: UUID) -> dict[str, Any]:
        # Assignment and patient/plan binding precede every feed read.
        plan, items = self.plans.publication_snapshot(clinician_id, patient_id, plan_id)
        active = [item for item in items if not item.get("is_removed")]
        if not active or not any(item.get("source_fact_id") for item in active):
            raise ValidationError("Care plan needs evidence-backed items before preview")
        if any(item.get("blocker_reason") for item in active):
            raise ValidationError("Resolve all saved care-plan blockers before preview")
        for item in active:
            if not all(
                str(item.get(key) or "").strip() for key in ("title", "instructions", "frequency")
            ):
                raise ValidationError("Complete patient-facing instructions before preview")
            schedule = item.get("schedule") or {}
            try:
                start = (
                    date.fromisoformat(str(schedule["start_date"]))
                    if schedule.get("start_date")
                    else None
                )
                end = (
                    date.fromisoformat(str(schedule["end_date"]))
                    if schedule.get("end_date")
                    else None
                )
            except (ValueError, TypeError):
                raise ValidationError(
                    "Review the plan item's effective dates before preview"
                ) from None
            if start and end and start > end:
                raise ValidationError("The plan item's end date must not precede its start date")
            if item["category"] == "medication" and not all(
                str(item["medication"].get(key) or "").strip()
                for key in ("name", "dosage", "frequency")
            ):
                raise ValidationError("Complete medication instructions before preview")
            if item["category"] == "medication" and item["medication"].get("route") not in (
                "oral",
                "topical",
                "inhaled",
                "iv",
                "im",
                "subcutaneous",
            ):
                raise ValidationError("Choose a supported medication route before preview")
        patient = await self.feed._get_patient(patient_id, strict=True)
        timezone = str(patient["timezone"])
        target_date = datetime.now(ZoneInfo(timezone)).date()
        previous = next(
            (row for row in self.plans._plans(patient_id) if row["status"] == "approved"), None
        )
        previous_items = self.plans._items(UUID(str(previous["id"]))) if previous else []
        provider_result = (
            self.db.table("care_teams")
            .select("id, clinicians(id, first_name, last_name, specialty, clinic_name)")
            .eq("patient_id", str(patient_id))
            .eq("clinician_id", str(clinician_id))
            .eq("status", "active")
            .order("created_at")
            .limit(1)
            .execute()
        )
        providers = cast(list[dict[str, Any]], provider_result.data or [])
        current = PublicationRecords(
            await self.feed._get_medications(patient_id, strict=True),
            await self.feed._get_obligations(patient_id, strict=True),
            previous_items,
            providers[0] if providers else None,
        )
        for item in active:
            if item["category"] == "medication":
                self.plans._validate_medication_decision(item["medication"], current.medications)
        records = proposed_records(active, current)
        reminders = await ReminderScheduleService(self.db).get_schedule_map_for_patient(
            str(patient_id)
        )
        adherence = await self.feed._get_today_adherence(
            patient_id, target_date, timezone, strict=True
        )
        plan_items = {
            str(item["id"]): {
                "version_number": plan["version_number"],
                "category": item["category"],
                "schedule": item.get("schedule") or {},
            }
            for item in active
        }
        feed = self.feed.render_snapshot(
            FeedSnapshot(
                target_date,
                timezone,
                records.medications,
                records.obligations,
                plan_items,
                reminders,
                adherence,
            )
        )
        return {
            "plan_id": str(plan_id),
            "version_number": plan["version_number"],
            "generated_at": datetime.now(UTC).isoformat(),
            "feed": feed,
        }
