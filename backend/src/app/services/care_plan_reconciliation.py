"""Conservative overlap detection; never infer clinical equivalence or pick therapy."""

from __future__ import annotations

import json
from typing import Any


def evidence_key(fact: dict[str, Any]) -> str | None:
    """Exact structured evidence, independent of document/fact identity."""
    value = fact.get("value") or {}
    identity = "name" if fact.get("fact_type") == "medication" else "description"
    if not value.get(identity):
        return None
    return json.dumps([fact.get("fact_type"), value], sort_keys=True)


def publication_key(item: dict[str, Any]) -> str | None:
    """Medication name or identical activity wording/cadence; not fuzzy matching."""

    def text(value: Any) -> str:
        return " ".join(str(value or "").split()).casefold()

    if item.get("category") == "medication":
        name = text((item.get("medication") or {}).get("name"))
        return f"medication:{name}" if name else None
    instruction, frequency = text(item.get("instructions")), text(item.get("frequency"))
    if not instruction or not frequency:
        return None
    return json.dumps(
        [item.get("category"), instruction, frequency, item.get("schedule") or {}], sort_keys=True
    )


def overlaps(items: list[dict[str, Any]], facts: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Keep every row and citation; return peers for an explicit reviewer choice."""
    by_fact = {str(fact["id"]): evidence_key(fact) for fact in facts}
    groups: dict[str, set[str]] = {}
    for item in items:
        if item.get("is_removed"):
            continue
        keys = [publication_key(item)]
        if item.get("category") != "medication" and str(item.get("instructions") or "").strip():
            # Identical wording with different cadence needs a choice, not an
            # automatic merge. Keep event/schedule context distinct.
            keys.append(
                json.dumps(
                    [
                        item.get("category"),
                        " ".join(str(item["instructions"]).split()).casefold(),
                        item.get("schedule") or {},
                    ],
                    sort_keys=True,
                )
            )
        if source_key := by_fact.get(str(item.get("source_fact_id"))):
            keys.append(f"source:{source_key}")
        for key in keys:
            if key:
                groups.setdefault(key, set()).add(str(item["id"]))
    peers: dict[str, set[str]] = {}
    for group in groups.values():
        for item_id in group:
            peers.setdefault(item_id, set()).update(group - {item_id})
    return {item_id: sorted(group) for item_id, group in peers.items() if group}
