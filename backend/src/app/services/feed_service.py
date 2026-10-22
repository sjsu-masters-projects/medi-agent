"""Today Feed — aggregates meds + obligations across all providers."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from supabase import Client

from app.core.exceptions import ValidationError
from app.services.activity_grouping import group_identical_activities
from app.services.patient_wording import patient_text
from app.services.reminder_schedule_service import (
    ReminderScheduleService,
    infer_frequency_guidance,
    occurrence_datetimes_for_day,
    schedule_matches_frequency,
    validate_timezone_name,
)

logger = logging.getLogger(__name__)


@dataclass
class FeedSnapshot:
    """Read-only inputs shared by live Today and publication previews."""

    target_date: date
    timezone: str
    medications: list[dict[str, Any]]
    obligations: list[dict[str, Any]]
    plan_items: dict[str, dict[str, Any]]
    reminders: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    adherence: list[dict[str, Any]] = field(default_factory=list)
    # The patient's saved language picks approved wording; switching needs no re-review.
    locale: str = "en-US"
    # care_plan_id -> plan_owner payload (PLAN-002). Empty for previews and legacy data.
    plan_owners: dict[str, dict[str, Any]] = field(default_factory=dict)
    # False only when the patient has no active care team (drives "contact your clinic").
    has_active_care_team: bool = True


UNOWNED_FILTER = "unowned"


def _first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


class FeedService:
    """Patient-scoped feed operations."""

    def __init__(self, db: Client) -> None:
        self.db = db

    async def get_today(
        self,
        patient_id: UUID,
        target_date: date | None = None,
        timezone: str | None = None,
        care_team_filter: str | None = None,
    ) -> dict[str, Any]:
        """Get today's feed for a patient, merged across every approved care plan.

        ``care_team_filter`` is a care-team id or ``"unowned"``; an unknown value yields an
        empty list rather than an error, so it never reveals whether an id exists.
        """
        reminder_map: dict[tuple[str, str], dict[str, Any]] = {}
        patient_row = await self._get_patient(patient_id)
        locale = str(patient_row.get("preferred_language") or "en-US")
        if timezone is not None:
            # Keep explicit query timezone override behavior lightweight/legacy-friendly.
            effective_timezone = validate_timezone_name(timezone)
        else:
            effective_timezone = validate_timezone_name(str(patient_row.get("timezone") or "UTC"))
            reminder_map = await self._get_reminder_schedule_map(patient_id)
        timezone_info = ZoneInfo(effective_timezone)
        if target_date is None:
            target_date = datetime.now(timezone_info).date()

        # Fetch data concurrently for performance
        medications, obligations, adherence_logs, plan_items = await asyncio.gather(
            self._get_medications(patient_id),
            self._get_obligations(patient_id),
            self._get_today_adherence(patient_id, target_date, effective_timezone),
            self._get_approved_plan_items(patient_id),
        )
        # Owners are only needed when some approved plan item is in play.
        plan_owners = await self._get_plan_owners(patient_id) if plan_items else {}
        has_active_care_team = await self._has_active_care_team(patient_id) if plan_owners else True
        return self.render_snapshot(
            FeedSnapshot(
                target_date,
                effective_timezone,
                medications,
                obligations,
                plan_items,
                reminder_map,
                adherence_logs,
                locale,
                plan_owners,
                has_active_care_team,
            ),
            care_team_filter=care_team_filter,
        )

    def render_snapshot(
        self, snapshot: FeedSnapshot, *, care_team_filter: str | None = None
    ) -> dict[str, Any]:
        """Render without database reads or writes; never invent reminder times."""
        target_date = snapshot.target_date
        effective_timezone = snapshot.timezone
        timezone_info = ZoneInfo(effective_timezone)
        reminder_map = snapshot.reminders
        medications = self._current_plan_projections(
            snapshot.medications, snapshot.plan_items, target_date
        )
        obligations = self._current_plan_projections(
            snapshot.obligations, snapshot.plan_items, target_date
        )

        # Identical activities of different plans show as one entry (the oldest). The
        # records themselves stay separate; this only shapes what the patient sees.
        group_of, medications, obligations, reminder_map, adherence = self._combine_identical(
            medications, obligations, snapshot.plan_items, reminder_map, snapshot.adherence
        )

        adherence_occurrence_map, adherence_unscheduled_map = self._build_adherence_maps(adherence)

        # Transform to tasks
        tasks: list[dict[str, Any]] = []
        tasks.extend(
            self._medications_to_tasks(
                medications,
                target_date,
                reminder_map,
                adherence_occurrence_map,
                adherence_unscheduled_map,
            )
        )
        tasks.extend(
            self._obligations_to_tasks(
                obligations,
                target_date,
                reminder_map,
                adherence_occurrence_map,
                adherence_unscheduled_map,
            )
        )

        targets = {("medication", str(row["id"])): row for row in medications} | {
            ("obligation", str(row["id"])): row for row in obligations
        }
        for index, task in enumerate(tasks):
            task["_order"] = index
            target = targets.get((str(task["type"]), str(task["target_id"])))
            if target is not None:
                task.update(patient_text(str(task["type"]), target, snapshot.locale))
            members = group_of.get((str(task["type"]), str(task["target_id"])))
            owners = [
                owner
                for member in (members if members else [target] if target is not None else [])
                if (owner := self._plan_owner_for(member, snapshot)) is not None
            ]
            unique_owners = list({o["care_plan_id"]: o for o in owners}.values())
            task["plan_owner"] = unique_owners[0] if unique_owners else None
            task["plan_owners"] = unique_owners
            task["combined_item_ids"] = (
                [str(m["id"]) for m in members] if members else [str(task["target_id"])]
            )

        # Sort by scheduled time
        tasks.sort(
            key=lambda t: (
                t.get("scheduled_at") or "9999-99-99T99:99:99+00:00",
                int(t.get("_order", 0)),
            )
        )
        for task in tasks:
            task.pop("_order", None)
            if (
                target_date == datetime.now(timezone_info).date()
                and task.get("status") == "pending"
                and task.get("scheduled_at")
                and datetime.fromisoformat(str(task["scheduled_at"]).replace("Z", "+00:00"))
                < datetime.now(UTC)
            ):
                task["status"] = "missed"

        # Filters and the contact-clinic flag describe the whole merged list, so the
        # patient can always switch owner; only the visible tasks are narrowed.
        care_team_filters = self._care_team_filters(tasks)
        contact_clinic = not snapshot.has_active_care_team and any(
            owner.get("unowned_notice") for task in tasks for owner in task["plan_owners"]
        )
        if care_team_filter is not None:
            tasks = [t for t in tasks if self._matches_owner(t["plan_owners"], care_team_filter)]

        # Calculate summary
        summary = self._calculate_summary(tasks)

        return {
            "date": target_date.isoformat(),
            "timezone": effective_timezone,
            "tasks": tasks,
            "summary": summary,
            "care_team_filters": care_team_filters,
            "contact_clinic": contact_clinic,
        }

    @staticmethod
    def _combine_identical(
        medications: list[dict[str, Any]],
        obligations: list[dict[str, Any]],
        plan_items: dict[str, dict[str, Any]],
        reminders: dict[tuple[str, str], dict[str, Any]],
        adherence: list[dict[str, Any]],
    ) -> tuple[
        dict[tuple[str, str], list[dict[str, Any]]],
        list[dict[str, Any]],
        list[dict[str, Any]],
        dict[tuple[str, str], dict[str, Any]],
        list[dict[str, Any]],
    ]:
        """Collapse groups of identical activities onto their oldest member.

        Returns the groups keyed by the entry's (type, id) with every member (entry first),
        the lists without the other members, one reminder schedule per entry (the entry's
        own, else the first member's), and logs of any member re-keyed to the entry.
        """
        activities = [("medication", m) for m in medications] + [
            ("obligation", o) for o in obligations
        ]
        groups = group_identical_activities(activities, plan_items)  # type: ignore[arg-type]
        if not groups:
            return {}, medications, obligations, reminders, adherence
        group_of: dict[tuple[str, str], list[dict[str, Any]]] = {}
        hidden: set[tuple[str, str]] = set()
        entry_of: dict[tuple[str, str], tuple[str, str]] = {}
        new_reminders = dict(reminders)
        for group in groups:
            entry_kind, entry = group[0]
            entry_key = (entry_kind, str(entry["id"]))
            group_of[entry_key] = [row for _kind, row in group]
            for kind, row in group:
                member_key = (kind, str(row["id"]))
                entry_of[member_key] = entry_key
                if member_key != entry_key:
                    hidden.add(member_key)
                    if entry_key not in new_reminders and member_key in reminders:
                        new_reminders[entry_key] = reminders[member_key]
        for key in hidden:
            new_reminders.pop(key, None)
        rekeyed = [
            {**log, "target_id": entry_of[key][1]}
            if (key := (str(log["target_type"]), str(log["target_id"]))) in entry_of
            else log
            for log in adherence
        ]
        return (
            group_of,
            [m for m in medications if ("medication", str(m["id"])) not in hidden],
            [o for o in obligations if ("obligation", str(o["id"])) not in hidden],
            new_reminders,
            rekeyed,
        )

    async def combined_member_ids(
        self, patient_id: UUID, target_type: str, target_id: str, target_date: date
    ) -> list[str]:
        """Ids of every activity that shares one entry with this one (itself first).

        A single id when it is not part of a group; used to fan a check-off out to each
        underlying activity so every owning team gets its own record.
        """
        medications, obligations, plan_items = await asyncio.gather(
            self._get_medications(patient_id, strict=True),
            self._get_obligations(patient_id, strict=True),
            self._get_approved_plan_items(patient_id),
        )
        live_meds = self._current_plan_projections(medications, plan_items, target_date)
        live_obls = self._current_plan_projections(obligations, plan_items, target_date)
        activities = [("medication", m) for m in live_meds] + [("obligation", o) for o in live_obls]
        for group in group_identical_activities(activities, plan_items):  # type: ignore[arg-type]
            ids = [str(row["id"]) for kind, row in group if kind == target_type]
            if target_id in ids:
                return [target_id, *[i for i in ids if i != target_id]]
        return [target_id]

    @staticmethod
    def _plan_owner_for(target: dict[str, Any], snapshot: FeedSnapshot) -> dict[str, Any] | None:
        """The owner of the approved plan an activity came from; None for legacy records."""
        item_id = target.get("care_plan_item_id")
        if item_id is None:
            return None
        plan_item = snapshot.plan_items.get(str(item_id))
        plan_id = plan_item.get("care_plan_id") if plan_item else None
        return snapshot.plan_owners.get(str(plan_id)) if plan_id else None

    @staticmethod
    def _matches_owner(owners: list[dict[str, Any]], care_team_filter: str) -> bool:
        """A combined entry stays when any of its owners matches."""
        for owner in owners:
            if care_team_filter == UNOWNED_FILTER:
                if owner.get("care_team_id") is None:
                    return True
                continue
            team_id = owner.get("care_team_id")
            if team_id is not None and str(team_id).lower() == care_team_filter.strip().lower():
                return True
        return False

    @staticmethod
    def _care_team_filters(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """One entry per distinct owner present; all ownerless plans share one entry."""
        buckets: dict[str | None, dict[str, Any]] = {}
        activities: dict[str | None, set[tuple[str, str]]] = {}
        for task in tasks:
            for owner in task["plan_owners"]:
                key = str(owner["care_team_id"]) if owner.get("care_team_id") else None
                activities.setdefault(key, set()).add((str(task["type"]), str(task["target_id"])))
                bucket = buckets.get(key)
                if bucket is None:
                    buckets[key] = {
                        "care_team_id": key,
                        "ownership_state": owner["ownership_state"],
                        "specialty": owner.get("specialty"),
                        "clinician_name": owner.get("clinician_name"),
                        "clinic_name": owner.get("clinic_name"),
                    }
                elif key is None:
                    # Several previous owners behind one "unowned" filter: show no single name.
                    if owner["ownership_state"] == "unowned":
                        bucket["ownership_state"] = "unowned"
                    for field_name in ("specialty", "clinician_name", "clinic_name"):
                        if bucket[field_name] != owner.get(field_name):
                            bucket[field_name] = None
        result = [{**bucket, "count": len(activities[key])} for key, bucket in buckets.items()]
        result.sort(key=lambda row: (row["care_team_id"] is None, str(row["clinician_name"])))
        return result

    async def _get_patient(self, patient_id: UUID, *, strict: bool = False) -> dict[str, Any]:
        result = (
            self.db.table("patients")
            .select("id, timezone, preferred_language")
            .eq("id", str(patient_id))
            .single()
            .execute()
        )
        if not isinstance(result.data, dict):
            if strict:
                raise ValidationError("Patient timezone is unavailable; refresh the review")
            return {"id": str(patient_id), "timezone": "UTC"}
        timezone = result.data.get("timezone")
        if not isinstance(timezone, str):
            if strict:
                raise ValidationError("Patient timezone is unavailable; refresh the review")
            return {"id": str(patient_id), "timezone": "UTC"}
        try:
            validate_timezone_name(timezone)
        except Exception:
            if strict:
                raise
            return {"id": str(patient_id), "timezone": "UTC"}
        return cast(dict[str, Any], result.data)

    async def _get_medications(
        self, patient_id: UUID, *, strict: bool = False
    ) -> list[dict[str, Any]]:
        """Fetch active medications with provider info."""
        try:
            result = (
                self.db.table("medications")
                .select(
                    """
                    id,
                    name,
                    dosage,
                    frequency,
                    instructions,
                    care_plan_item_id,
                    route,
                    created_at,
                    patient_wording,
                    prescribed_by_care_team_id,
                    care_teams!prescribed_by_care_team_id(
                        id,
                        clinics(display_name),
                        clinicians(
                            id,
                            first_name,
                            last_name,
                            specialty
                        )
                    )
                """
                )
                .eq("patient_id", str(patient_id))
                .eq("is_active", True)
                .execute()
            )
            return result.data or []  # type: ignore[return-value]
        except Exception as e:
            if strict:
                raise
            logger.error(f"Failed to fetch medications: {e}")
            return []

    async def _get_obligations(
        self, patient_id: UUID, *, strict: bool = False
    ) -> list[dict[str, Any]]:
        """Fetch active obligations with provider info."""
        try:
            result = (
                self.db.table("obligations")
                .select(
                    """
                    id,
                    description,
                    notes,
                    frequency,
                    obligation_type,
                    care_plan_item_id,
                    created_at,
                    patient_wording,
                    set_by_care_team_id,
                    care_teams!set_by_care_team_id(
                        id,
                        clinics(display_name),
                        clinicians(
                            id,
                            first_name,
                            last_name,
                            specialty
                        )
                    )
                """
                )
                .eq("patient_id", str(patient_id))
                .eq("is_active", True)
                .execute()
            )
            return result.data or []  # type: ignore[return-value]
        except Exception as e:
            if strict:
                raise
            logger.error(f"Failed to fetch obligations: {e}")
            return []

    async def _get_approved_plan_items(self, patient_id: UUID) -> dict[str, dict[str, Any]]:
        """Load only current approved plan items for feed projection validation."""
        try:
            versions = cast(
                list[dict[str, Any]],
                self.db.table("care_plan_versions")
                .select("id, version_number, care_plan_id")
                .eq("patient_id", str(patient_id))
                .eq("status", "approved")
                .execute()
                .data
                or [],
            )
            version_numbers = {str(row["id"]): int(row["version_number"]) for row in versions}
            version_plans = {str(row["id"]): row.get("care_plan_id") for row in versions}
            if not version_numbers:
                return {}
            items = cast(
                list[dict[str, Any]],
                self.db.table("care_plan_items")
                .select(
                    "id, plan_version_id, category, schedule, is_removed, "
                    "instructions, frequency, medication"
                )
                .in_("plan_version_id", list(version_numbers))
                .eq("is_removed", False)
                .execute()
                .data
                or [],
            )
        except Exception:
            logger.warning("Failed to load approved care-plan projections")
            return {}
        retired = self._retired_item_ids([str(item["id"]) for item in items])
        items = [item for item in items if str(item["id"]) not in retired]
        return {
            str(item["id"]): {
                "care_plan_id": version_plans.get(str(item["plan_version_id"])),
                "version_number": version_numbers[str(item["plan_version_id"])],
                "category": str(item["category"]),
                "schedule": item.get("schedule") or {},
                "instructions": item.get("instructions"),
                "frequency": item.get("frequency"),
                "medication": item.get("medication"),
            }
            for item in items
            if str(item["plan_version_id"]) in version_numbers
        }

    def _retired_item_ids(self, item_ids: list[str]) -> set[str]:
        """Items a clinician retired. The projection is also deactivated; this is a backstop."""
        if not item_ids:
            return set()
        try:
            rows = cast(
                list[dict[str, Any]],
                self.db.table("care_plan_item_retirements")
                .select("item_id")
                .in_("item_id", item_ids)
                .execute()
                .data
                or [],
            )
        except Exception:
            logger.warning("Failed to load care-plan item retirements")
            return set()
        return {str(row["item_id"]) for row in rows}

    async def _has_active_care_team(self, patient_id: UUID) -> bool:
        try:
            rows = (
                self.db.table("care_teams")
                .select("id")
                .eq("patient_id", str(patient_id))
                .eq("status", "active")
                .limit(1)
                .execute()
                .data
            )
        except Exception:
            logger.warning("Failed to read active care teams for feed")
            return True  # unknown: do not tell the patient to contact a clinic by mistake
        return bool(rows)

    async def _get_plan_owners(self, patient_id: UUID) -> dict[str, dict[str, Any]]:
        """care_plan_id -> owner display for every plan of the patient.

        Owned plans show the live care-team, clinician and clinic rows; unowned plans show
        the owner_snapshot kept when the team ended. Names only, no label text.
        """
        try:
            plans = cast(
                list[dict[str, Any]],
                self.db.table("care_plans")
                .select("id, care_team_id, ownership_state, owner_snapshot")
                .eq("patient_id", str(patient_id))
                .execute()
                .data
                or [],
            )
            team_ids = [str(p["care_team_id"]) for p in plans if p.get("care_team_id")]
            teams: dict[str, dict[str, Any]] = {}
            clinicians: dict[str, dict[str, Any]] = {}
            clinics: dict[str, dict[str, Any]] = {}
            if team_ids:
                team_rows = cast(
                    list[dict[str, Any]],
                    self.db.table("care_teams")
                    .select("id, clinician_id, clinic_id, role, specialty_context")
                    .eq("patient_id", str(patient_id))
                    .in_("id", team_ids)
                    .execute()
                    .data
                    or [],
                )
                teams = {str(t["id"]): t for t in team_rows}
                clinician_ids = sorted(
                    {str(t["clinician_id"]) for t in team_rows if t.get("clinician_id")}
                )
                clinic_ids = sorted({str(t["clinic_id"]) for t in team_rows if t.get("clinic_id")})
                if clinician_ids:
                    clinicians = {
                        str(c["id"]): c
                        for c in cast(
                            list[dict[str, Any]],
                            self.db.table("clinicians")
                            .select("id, first_name, last_name, specialty")
                            .in_("id", clinician_ids)
                            .execute()
                            .data
                            or [],
                        )
                    }
                if clinic_ids:
                    clinics = {
                        str(c["id"]): c
                        for c in cast(
                            list[dict[str, Any]],
                            self.db.table("clinics")
                            .select("id, display_name")
                            .in_("id", clinic_ids)
                            .execute()
                            .data
                            or [],
                        )
                    }
        except Exception:
            logger.warning("Failed to load care-plan owners for feed")
            return {}
        owners: dict[str, dict[str, Any]] = {}
        for plan in plans:
            state = str(plan.get("ownership_state") or "unassigned_legacy")
            snapshot = plan.get("owner_snapshot")
            snapshot = snapshot if isinstance(snapshot, dict) else {}
            team = teams.get(str(plan.get("care_team_id"))) if plan.get("care_team_id") else None
            if state == "owned" and team is not None:
                clinician = clinicians.get(str(team.get("clinician_id"))) or {}
                clinic = clinics.get(str(team.get("clinic_id"))) or {}
                name = " ".join(
                    str(part).strip()
                    for part in (clinician.get("first_name"), clinician.get("last_name"))
                    if part and str(part).strip()
                )
                display = {
                    "specialty": _first_text(
                        team.get("specialty_context"), clinician.get("specialty"), team.get("role")
                    ),
                    "clinician_name": name or None,
                    "clinic_id": team.get("clinic_id"),
                    "clinic_name": clinic.get("display_name"),
                }
                care_team_id: Any = team["id"]
            else:
                display = {
                    "specialty": _first_text(snapshot.get("specialty")),
                    "clinician_name": _first_text(snapshot.get("clinician_name")),
                    "clinic_id": snapshot.get("clinic_id"),
                    "clinic_name": _first_text(snapshot.get("clinic_name")),
                }
                care_team_id = None
                if state == "owned":
                    state = "unassigned_legacy"  # owner row unreadable: never show as owned
            owners[str(plan["id"])] = {
                "care_plan_id": str(plan["id"]),
                "care_team_id": str(care_team_id) if care_team_id else None,
                "ownership_state": state,
                **{k: (str(v) if k == "clinic_id" and v else v) for k, v in display.items()},
                "unowned_notice": state in ("unowned", "unassigned_legacy"),
            }
        return owners

    async def _get_today_adherence(
        self, patient_id: UUID, target_date: date, timezone_name: str, *, strict: bool = False
    ) -> list[dict[str, Any]]:
        """Fetch today's adherence logs."""
        try:
            timezone_info = ZoneInfo(timezone_name)
            local_start = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone_info)
            local_end = local_start + timedelta(days=1)
            today_start = local_start.astimezone(UTC)
            today_end = local_end.astimezone(UTC)

            result = (
                self.db.table("adherence_logs")
                .select("target_id, target_type, status, logged_at, scheduled_time")
                .eq("patient_id", str(patient_id))
                .gte("logged_at", today_start.isoformat())
                .lt("logged_at", today_end.isoformat())
                .execute()
            )
            return result.data or []  # type: ignore[return-value]
        except Exception as e:
            if strict:
                raise
            logger.error(f"Failed to fetch adherence logs: {e}")
            return []

    async def _get_reminder_schedule_map(
        self, patient_id: UUID
    ) -> dict[tuple[str, str], dict[str, Any]]:
        try:
            service = ReminderScheduleService(self.db)
            return await service.get_schedule_map_for_patient(str(patient_id))
        except Exception:
            logger.warning("Failed to load reminder schedules for feed", exc_info=True)
            return {}

    def _build_adherence_map(
        self, logs: list[dict[str, Any]]
    ) -> dict[tuple[str, str], dict[str, Any]]:
        """Backward-compatible map: (target_type, target_id) -> latest log."""
        occurrence_map, unscheduled_map = self._build_adherence_maps(logs)
        combined = dict(unscheduled_map)
        for (target_type, target_id, _scheduled_at), log in occurrence_map.items():
            key = (target_type, target_id)
            if key not in combined or log["logged_at"] > combined[key]["logged_at"]:
                combined[key] = log
        return combined

    def _build_adherence_maps(
        self, logs: list[dict[str, Any]]
    ) -> tuple[dict[tuple[str, str, str], dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
        """Build exact-occurrence and unscheduled adherence lookups."""
        occurrence_map: dict[tuple[str, str, str], dict[str, Any]] = {}
        unscheduled_map: dict[tuple[str, str], dict[str, Any]] = {}
        for log in logs:
            target_type = str(log["target_type"])
            target_id = str(log["target_id"])
            scheduled_time = log.get("scheduled_time")
            if scheduled_time:
                occurrence_key = (target_type, target_id, self._occurrence_key(str(scheduled_time)))
                if (
                    occurrence_key not in occurrence_map
                    or log["logged_at"] > occurrence_map[occurrence_key]["logged_at"]
                ):
                    occurrence_map[occurrence_key] = log
            else:
                key = (target_type, target_id)
                if (
                    key not in unscheduled_map
                    or log["logged_at"] > unscheduled_map[key]["logged_at"]
                ):
                    unscheduled_map[key] = log
        return occurrence_map, unscheduled_map

    @staticmethod
    def _occurrence_key(value: str) -> str:
        """Match equivalent persisted timestamp formats, never a time-only legacy value."""
        try:
            instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if instant.tzinfo is not None:
                return instant.astimezone(UTC).isoformat()
        except ValueError:
            # Legacy time-only keys are intentionally exact matches; parsing
            # failure must not turn them into a different dated occurrence.
            return value
        return value

    @classmethod
    def _current_plan_projections(
        cls,
        projections: list[dict[str, Any]],
        approved_items: dict[str, dict[str, Any]],
        target_date: date,
    ) -> list[dict[str, Any]]:
        """Keep legacy projections plus approved care-plan items effective on this date."""
        visible: list[dict[str, Any]] = []
        for projection in projections:
            item_id = projection.get("care_plan_item_id")
            if item_id is None:
                visible.append(projection)
                continue
            plan_item = approved_items.get(str(item_id))
            if plan_item is not None and cls._plan_item_is_effective(plan_item, target_date):
                projection["care_plan"] = cls._plan_provenance(plan_item)
                visible.append(projection)
        return visible

    @staticmethod
    def _plan_item_is_effective(plan_item: dict[str, Any], target_date: date) -> bool:
        schedule = plan_item.get("schedule")
        if not isinstance(schedule, dict):
            return False
        start = FeedService._schedule_date(schedule, "start_date")
        end = FeedService._schedule_date(schedule, "end_date")
        if (schedule.get("start_date") and start is None) or (
            schedule.get("end_date") and end is None
        ):
            return False
        return (start is None or start <= target_date) and (end is None or target_date <= end)

    @staticmethod
    def _schedule_date(schedule: dict[str, Any], key: str) -> date | None:
        value = schedule.get(key)
        if not value:
            return None
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None

    @staticmethod
    def _plan_provenance(plan_item: dict[str, Any]) -> dict[str, Any]:
        schedule = cast(dict[str, Any], plan_item.get("schedule") or {})
        return {
            "version_number": plan_item["version_number"],
            "category": plan_item["category"],
            "effective_start_date": schedule.get("start_date"),
            "effective_end_date": schedule.get("end_date"),
        }

    def _medications_to_tasks(
        self,
        medications: list[dict[str, Any]],
        target_date_or_adherence_map: date | dict[tuple[str, str], dict[str, Any]],
        reminder_map: dict[tuple[str, str], dict[str, Any]] | None = None,
        adherence_occurrence_map: dict[tuple[str, str, str], dict[str, Any]] | None = None,
        adherence_unscheduled_map: dict[tuple[str, str], dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Transform medications to task format."""
        if isinstance(target_date_or_adherence_map, date):
            target_date = target_date_or_adherence_map
            effective_reminder_map = reminder_map or {}
            effective_occurrence_map = adherence_occurrence_map or {}
            effective_unscheduled_map = adherence_unscheduled_map or {}
        else:
            # Backward-compatible unit-test mode
            target_date = datetime.now().date()
            effective_reminder_map = {}
            effective_occurrence_map = {}
            effective_unscheduled_map = target_date_or_adherence_map

        tasks: list[dict[str, Any]] = []
        for med in medications:
            guidance = infer_frequency_guidance(str(med.get("frequency") or ""))
            required_days = guidance.get("required_days_of_week")
            if required_days and target_date.strftime("%A").lower() not in required_days:
                continue
            schedule = effective_reminder_map.get(("medication", str(med["id"])))
            if schedule and schedule_matches_frequency(schedule, str(med.get("frequency") or "")):
                tasks.extend(
                    self._scheduled_tasks_for_item(
                        target_type="medication",
                        target=med,
                        target_date=target_date,
                        schedule=schedule,
                        adherence_occurrence_map=effective_occurrence_map,
                    )
                )
                continue

            adherence = effective_unscheduled_map.get(("medication", str(med["id"])))
            if adherence is None:
                adherence = self._latest_occurrence_for_target(
                    target_type="medication",
                    target_id=str(med["id"]),
                    adherence_occurrence_map=effective_occurrence_map,
                )
            guidance = infer_frequency_guidance(str(med.get("frequency") or ""))
            tasks.append(
                {
                    "id": f"medication:{med['id']}:unscheduled",
                    "type": "medication",
                    "target_id": med["id"],
                    "name": f"{med['name']} {med['dosage']}",
                    "description": med.get("instructions"),
                    "frequency": med["frequency"],
                    "scheduled_time": adherence.get("scheduled_time") if adherence else None,
                    "scheduled_at": adherence.get("scheduled_time") if adherence else None,
                    "status": self._determine_status(adherence),
                    "completed_at": adherence.get("logged_at") if adherence else None,
                    "requires_schedule_configuration": bool(
                        guidance["supports_automatic_reminders"]
                        and guidance.get("recommended_times_per_day")
                    ),
                    "provider": self._extract_provider(med.get("care_teams")),
                    "care_plan_item_id": med.get("care_plan_item_id"),
                    "care_plan": med.get("care_plan"),
                }
            )
        return tasks

    def _obligations_to_tasks(
        self,
        obligations: list[dict[str, Any]],
        target_date_or_adherence_map: date | dict[tuple[str, str], dict[str, Any]],
        reminder_map: dict[tuple[str, str], dict[str, Any]] | None = None,
        adherence_occurrence_map: dict[tuple[str, str, str], dict[str, Any]] | None = None,
        adherence_unscheduled_map: dict[tuple[str, str], dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Transform obligations to task format."""
        if isinstance(target_date_or_adherence_map, date):
            target_date = target_date_or_adherence_map
            effective_reminder_map = reminder_map or {}
            effective_occurrence_map = adherence_occurrence_map or {}
            effective_unscheduled_map = adherence_unscheduled_map or {}
        else:
            # Backward-compatible unit-test mode
            target_date = datetime.now().date()
            effective_reminder_map = {}
            effective_occurrence_map = {}
            effective_unscheduled_map = target_date_or_adherence_map

        tasks: list[dict[str, Any]] = []
        for obl in obligations:
            guidance = infer_frequency_guidance(str(obl.get("frequency") or ""))
            required_days = guidance.get("required_days_of_week")
            if required_days and target_date.strftime("%A").lower() not in required_days:
                continue
            schedule = effective_reminder_map.get(("obligation", str(obl["id"])))
            if schedule and schedule_matches_frequency(schedule, str(obl.get("frequency") or "")):
                tasks.extend(
                    self._scheduled_tasks_for_item(
                        target_type="obligation",
                        target=obl,
                        target_date=target_date,
                        schedule=schedule,
                        adherence_occurrence_map=effective_occurrence_map,
                    )
                )
                continue

            adherence = effective_unscheduled_map.get(("obligation", str(obl["id"])))
            if adherence is None:
                adherence = self._latest_occurrence_for_target(
                    target_type="obligation",
                    target_id=str(obl["id"]),
                    adherence_occurrence_map=effective_occurrence_map,
                )
            guidance = infer_frequency_guidance(str(obl.get("frequency") or ""))
            tasks.append(
                {
                    "id": f"obligation:{obl['id']}:unscheduled",
                    "type": "obligation",
                    "target_id": obl["id"],
                    "name": obl["description"],
                    "description": obl.get("notes"),
                    "frequency": obl["frequency"],
                    "scheduled_time": adherence.get("scheduled_time") if adherence else None,
                    "scheduled_at": adherence.get("scheduled_time") if adherence else None,
                    "status": self._determine_status(adherence),
                    "completed_at": adherence.get("logged_at") if adherence else None,
                    "requires_schedule_configuration": bool(
                        guidance["supports_automatic_reminders"]
                        and guidance.get("recommended_times_per_day")
                    ),
                    "provider": self._extract_provider(obl.get("care_teams")),
                    "care_plan_item_id": obl.get("care_plan_item_id"),
                    "care_plan": obl.get("care_plan"),
                }
            )
        return tasks

    def _scheduled_tasks_for_item(
        self,
        *,
        target_type: str,
        target: dict[str, Any],
        target_date: date,
        schedule: dict[str, Any],
        adherence_occurrence_map: dict[tuple[str, str, str], dict[str, Any]],
    ) -> list[dict[str, Any]]:
        occurrences = occurrence_datetimes_for_day(schedule, target_date)
        if not occurrences:
            return []

        tasks: list[dict[str, Any]] = []
        for scheduled_at, local_time in occurrences:
            adherence = adherence_occurrence_map.get(
                (target_type, str(target["id"]), self._occurrence_key(scheduled_at))
            )
            name = (
                f"{target['name']} {target['dosage']}"
                if target_type == "medication"
                else target["description"]
            )
            tasks.append(
                {
                    "id": f"{target_type}:{target['id']}:{scheduled_at}",
                    "type": target_type,
                    "target_id": target["id"],
                    "name": name,
                    "description": target.get("instructions") or target.get("notes"),
                    "frequency": target["frequency"],
                    "scheduled_time": local_time,
                    "scheduled_at": scheduled_at,
                    "status": self._determine_status(adherence),
                    "completed_at": adherence.get("logged_at") if adherence else None,
                    "requires_schedule_configuration": False,
                    "provider": self._extract_provider(target.get("care_teams")),
                    "care_plan_item_id": target.get("care_plan_item_id"),
                    "care_plan": target.get("care_plan"),
                }
            )
        return tasks

    def _determine_status(self, adherence: dict[str, Any] | None) -> str:
        """Determine task status from adherence log."""
        if not adherence:
            return "pending"

        status = adherence.get("status")
        if status in ["completed", "taken"]:
            return "completed"
        elif status == "skipped":
            return "skipped"
        else:
            return "pending"

    def _latest_occurrence_for_target(
        self,
        *,
        target_type: str,
        target_id: str,
        adherence_occurrence_map: dict[tuple[str, str, str], dict[str, Any]],
    ) -> dict[str, Any] | None:
        latest: dict[str, Any] | None = None
        for (candidate_type, candidate_id, _scheduled_at), log in adherence_occurrence_map.items():
            if candidate_type != target_type or candidate_id != target_id:
                continue
            if latest is None or str(log.get("logged_at") or "") > str(
                latest.get("logged_at") or ""
            ):
                latest = log
        return latest

    def _extract_provider(self, care_teams: dict[str, Any] | None) -> dict[str, Any] | None:
        """Extract provider info from care_teams join."""
        if not care_teams:
            return None

        clinician = care_teams.get("clinicians")
        if not clinician:
            return None

        return {
            "id": clinician["id"],
            "name": f"Dr. {clinician['first_name']} {clinician['last_name']}",
            "specialty": clinician["specialty"],
            # The clinic of the care-team link that prescribed or set this, not the
            # clinician's default clinic (CLN-003 slice F).
            "clinic_name": (care_teams.get("clinics") or {}).get("display_name") or "",
        }

    def _calculate_summary(self, tasks: list[dict[str, Any]]) -> dict[str, int]:
        """Calculate task summary statistics."""
        total = len(tasks)
        completed = sum(1 for t in tasks if t["status"] == "completed")
        pending = sum(1 for t in tasks if t["status"] == "pending")
        skipped = sum(1 for t in tasks if t["status"] == "skipped")
        missed = sum(1 for t in tasks if t["status"] == "missed")

        return {
            "total": total,
            "completed": completed,
            "pending": pending,
            "skipped": skipped,
            "missed": missed,
        }
