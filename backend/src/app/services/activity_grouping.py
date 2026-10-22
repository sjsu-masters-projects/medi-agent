"""Group identical approved activities from different care plans (PLAN-002).

Read-model only: plan items, medications and obligations are never merged or deleted. Two
live activities group only when they are provably the same instruction; any difference
keeps them apart (publication of a conflicting plan is blocked in SQL anyway). Medication
identity uses the same precedence as ``private.care_plan_cross_conflicts`` (migration 086):
canonical target, recorded ingredient rxcui, normalized recorded name.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

ActivityKind = Literal["medication", "obligation"]
Activity = tuple[ActivityKind, dict[str, Any]]

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def norm_text(value: Any) -> str:
    """Same normalization as private.norm_text: lower-case, collapsed whitespace."""
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _medication_of(item: dict[str, Any]) -> dict[str, Any]:
    medication = item.get("medication")
    return medication if isinstance(medication, dict) else {}


def _identity_keys(row: dict[str, Any], item: dict[str, Any]) -> set[tuple[str, str]]:
    medication = _medication_of(item)
    keys: set[tuple[str, str]] = {("t", str(row["id"]).lower())}
    target = str(medication.get("target_id") or "")
    if _UUID.match(target):
        keys.add(("t", target.lower()))
    rxcui = str(medication.get("ingredient_rxcui") or "")
    if rxcui.isdigit():
        keys.add(("i", rxcui))
    name = norm_text(medication.get("name"))
    if name:
        keys.add(("n", name))
    return keys


def _schedule(item: dict[str, Any]) -> str:
    schedule = item.get("schedule")
    return json.dumps(schedule if isinstance(schedule, dict) else {}, sort_keys=True)


def _signature(kind: ActivityKind, row: dict[str, Any], item: dict[str, Any]) -> tuple[str, ...]:
    medication = _medication_of(item)
    instructions = norm_text(
        item.get("instructions") or row.get("instructions") or row.get("notes")
    )
    if kind == "medication":
        return (
            norm_text(medication.get("dosage") or row.get("dosage")),
            norm_text(medication.get("frequency") or item.get("frequency") or row.get("frequency")),
            norm_text(medication.get("route") or row.get("route")),
            instructions,
            _schedule(item),
        )
    return (
        norm_text(item.get("category")),
        norm_text(row.get("description")),
        instructions,
        norm_text(item.get("frequency") or row.get("frequency")),
        _schedule(item),
    )


def _same(a: Activity, b: Activity, items: dict[str, dict[str, Any]]) -> bool:
    (kind_a, row_a), (kind_b, row_b) = a, b
    if kind_a != kind_b:
        return False
    item_a, item_b = items[str(row_a["care_plan_item_id"])], items[str(row_b["care_plan_item_id"])]
    if _signature(kind_a, row_a, item_a) != _signature(kind_b, row_b, item_b):
        return False
    if kind_a == "obligation":
        return True
    return bool(_identity_keys(row_a, item_a) & _identity_keys(row_b, item_b))


def _order_key(activity: Activity) -> tuple[str, str]:
    row = activity[1]
    return (str(row.get("created_at") or ""), str(row["id"]))


def group_identical_activities(
    activities: list[Activity], plan_items: dict[str, dict[str, Any]]
) -> list[list[Activity]]:
    """Groups of two or more identical activities, oldest (the entry) first.

    Only activities backed by a live approved plan item can group; legacy records never do.
    """
    candidates = [
        a
        for a in activities
        if a[1].get("care_plan_item_id") is not None
        and str(a[1]["care_plan_item_id"]) in plan_items
    ]
    parent = list(range(len(candidates)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for i, first in enumerate(candidates):
        for j in range(i + 1, len(candidates)):
            if _same(first, candidates[j], plan_items):
                parent[find(j)] = find(i)
    clusters: dict[int, list[Activity]] = {}
    for index, activity in enumerate(candidates):
        clusters.setdefault(find(index), []).append(activity)
    return [sorted(c, key=_order_key) for c in clusters.values() if len(c) > 1]
