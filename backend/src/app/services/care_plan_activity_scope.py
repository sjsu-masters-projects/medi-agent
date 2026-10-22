"""Which care team's plan an activity belongs to (PLAN-002, CLN-003 slice G).

A medication or obligation a care plan created carries ``care_plan_item_id``, which leads to
``care_plan_versions.care_plan_id`` and ``care_plans.care_team_id``. Adherence and barrier
reports about such an activity are that plan's team's. An activity with no plan item, or
whose plan is not owned by one team, stays visible to every team of the patient.

The helpers are synchronous (the Supabase client is); async callers wrap them in
``asyncio.to_thread``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, cast

from supabase import Client

from app.services.care_team_access import PatientAccess

_CHUNK = 100
_TABLES = {"medication": "medications", "obligation": "obligations"}


def _rows(db: Client, table: str, columns: str, ids: list[str], **eq: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for start in range(0, len(ids), _CHUNK):
        query = db.table(table).select(columns).in_("id", ids[start : start + _CHUNK])
        for column, value in eq.items():
            query = query.eq(column, value)
        found += cast(list[dict[str, Any]], query.execute().data or [])
    return found


def plan_owner_by_target(
    db: Client, patient_id: Any, targets: Iterable[tuple[str, Any]]
) -> dict[str, str | None]:
    """Owning care team of each (target_type, target_id), or None when it is unowned.

    None means no single team owns the activity (no plan item, an unowned plan, a lookup that
    finds nothing); such an activity is shared. Keys are the target ids as strings.
    """
    wanted: dict[str, list[str]] = {}
    for target_type, target_id in targets:
        if target_type in _TABLES:
            wanted.setdefault(target_type, []).append(str(target_id))
    owners: dict[str, str | None] = {
        target_id: None for ids in wanted.values() for target_id in ids
    }
    item_of: dict[str, str] = {}
    for target_type, ids in wanted.items():
        for row in _rows(
            db,
            _TABLES[target_type],
            "id, care_plan_item_id",
            sorted(set(ids)),
            patient_id=str(patient_id),
        ):
            if row.get("care_plan_item_id"):
                item_of[str(row["id"])] = str(row["care_plan_item_id"])
    if not item_of:
        return owners
    version_of = {
        str(row["id"]): str(row["plan_version_id"])
        for row in _rows(
            db, "care_plan_items", "id, plan_version_id", sorted(set(item_of.values()))
        )
        if row.get("plan_version_id")
    }
    plan_of = {
        str(row["id"]): str(row["care_plan_id"])
        for row in _rows(
            db, "care_plan_versions", "id, care_plan_id", sorted(set(version_of.values()))
        )
        if row.get("care_plan_id")
    }
    team_of = {
        str(row["id"]): str(row["care_team_id"])
        for row in _rows(
            db, "care_plans", "id, care_team_id, ownership_state", sorted(set(plan_of.values()))
        )
        if row.get("ownership_state") == "owned" and row.get("care_team_id")
    }
    for target_id, item_id in item_of.items():
        plan_id = plan_of.get(version_of.get(item_id, ""), "")
        owners[target_id] = team_of.get(plan_id)
    return owners


def visible_to(access: PatientAccess, owner: str | None) -> bool:
    """An unowned activity is every team's; an owned one belongs to its team only."""
    return bool(access) and (owner is None or access.owns(owner))


class ActivityScope:
    """Filters adherence rows (target_type, target_id) to what one clinician may read."""

    def __init__(self, db: Client, patient_id: Any, access: PatientAccess) -> None:
        self.db = db
        self.patient_id = str(patient_id)
        self.access = access
        self._owners: dict[str, str | None] = {}

    def owners(self, targets: Iterable[tuple[str, Any]]) -> Mapping[str, str | None]:
        fresh = [(t, i) for t, i in targets if str(i) not in self._owners]
        if fresh:
            self._owners.update(plan_owner_by_target(self.db, self.patient_id, fresh))
            for _, target_id in fresh:  # an unknown target is unowned, looked up once
                self._owners.setdefault(str(target_id), None)
        return self._owners

    def keep(self, rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """Rows (with ``target_type`` and ``target_id``) this clinician may read."""
        listed = [dict(row) for row in rows]
        owners = self.owners((str(r.get("target_type")), r.get("target_id")) for r in listed)
        return [
            row for row in listed if visible_to(self.access, owners.get(str(row.get("target_id"))))
        ]
