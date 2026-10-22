"""Deterministic cross-plan review flags, not drug interaction/equivalence advice.

Inputs must come from authorized, patient-scoped source reads. This module neither
fetches private source documents nor changes clinical records. Publication must
repeat these comparisons under the patient's transaction lock.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from app.core.exceptions import ValidationError

ConflictKind = Literal["duplicate_medication", "regimen_difference", "stop_continue"]
IdentityBasis = Literal["canonical_target", "recorded_ingredient", "recorded_name"]
INTERACTION_COVERAGE = "not_checked"


def _text(value: Any) -> str:
    return " ".join(value.split()).casefold() if isinstance(value, str) else ""


@dataclass(frozen=True)
class PlanMedication:
    """An immutable source snapshot. Ordinary RxCUIs are not ingredient identifiers."""

    patient_id: UUID
    plan_id: UUID
    care_team_id: UUID
    item_id: UUID
    version_id: UUID
    name: str
    dosage: str
    frequency: str
    route: str
    instructions: str
    action: Literal["continue", "stop", "unknown"] = "unknown"
    canonical_target_id: UUID | None = None
    ingredient_rxcui: str | None = None
    # Reviewed bilingual wording and structured schedule participate in stale checks.
    wording: str = "{}"
    schedule: str = "{}"

    def __post_init__(self) -> None:
        if self.ingredient_rxcui is not None and (
            not self.ingredient_rxcui.isascii() or not self.ingredient_rxcui.isdecimal()
        ):
            raise ValueError("A recorded ingredient identifier must be numeric")
        for value in (self.wording, self.schedule):
            if not isinstance(json.loads(value), dict):
                raise ValueError("Wording and schedule snapshots must be JSON objects")


@dataclass(frozen=True)
class CrossPlanConflict:
    kind: ConflictKind
    identity_basis: IdentityBasis
    draft_item_id: UUID
    other_item_id: UUID
    other_plan_id: UUID
    other_care_team_id: UUID
    fingerprint: str
    requires_resolution: bool = True


def _identity(left: PlanMedication, right: PlanMedication) -> IdentityBasis | None:
    if left.canonical_target_id and left.canonical_target_id == right.canonical_target_id:
        return "canonical_target"
    if left.ingredient_rxcui and left.ingredient_rxcui == right.ingredient_rxcui:
        return "recorded_ingredient"
    if _text(left.name) and _text(left.name) == _text(right.name):
        return "recorded_name"
    return None


def _snapshot(item: PlanMedication) -> dict[str, Any]:
    # Deliberately bind source wording, not a display-language normalization. An
    # edit to either clinical snapshot requires renewed clinician acknowledgement.
    return {
        "patient": str(item.patient_id),
        "plan": str(item.plan_id),
        "team": str(item.care_team_id),
        "version": str(item.version_id),
        "item": str(item.item_id),
        "target": str(item.canonical_target_id) if item.canonical_target_id else None,
        "ingredient": item.ingredient_rxcui,
        "name": item.name,
        "dosage": item.dosage,
        "frequency": item.frequency,
        "route": item.route,
        "instructions": item.instructions,
        "action": item.action,
        "wording": json.loads(item.wording),
        "schedule": json.loads(item.schedule),
    }


def conflict_fingerprint(left: PlanMedication, right: PlanMedication) -> str:
    """Bind a decision to both exact versions; never log this payload."""
    payload = json.dumps(
        {"schema": "cross-plan-review/v1", "draft": _snapshot(left), "other": _snapshot(right)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _kind(left: PlanMedication, right: PlanMedication) -> ConflictKind:
    if {left.action, right.action} == {"stop", "continue"}:
        return "stop_continue"
    fields = ("dosage", "frequency", "route", "instructions")
    if any(_text(getattr(left, key)) != _text(getattr(right, key)) for key in fields):
        return "regimen_difference"
    if json.loads(left.schedule) != json.loads(right.schedule):
        return "regimen_difference"
    return "duplicate_medication"


def detect_cross_plan_conflicts(
    proposed: Sequence[PlanMedication], approved_other: Sequence[PlanMedication]
) -> list[CrossPlanConflict]:
    """Compare authorized snapshots; never equate brand names, salts or release forms."""
    conflicts: dict[tuple[UUID, UUID], CrossPlanConflict] = {}
    for left in proposed:
        for right in approved_other:
            if left.patient_id != right.patient_id:
                raise ValidationError("Cross-plan review requires one patient scope")
            if left.plan_id == right.plan_id:
                continue
            if basis := _identity(left, right):
                conflicts[(left.item_id, right.item_id)] = CrossPlanConflict(
                    kind=_kind(left, right),
                    identity_basis=basis,
                    draft_item_id=left.item_id,
                    other_item_id=right.item_id,
                    other_plan_id=right.plan_id,
                    other_care_team_id=right.care_team_id,
                    fingerprint=conflict_fingerprint(left, right),
                )
    return sorted(
        conflicts.values(), key=lambda value: (str(value.draft_item_id), str(value.other_item_id))
    )


def require_current_acknowledgements(
    conflicts: Sequence[CrossPlanConflict], acknowledgements: Mapping[str, str]
) -> None:
    """A reply/read/old decision cannot substitute for a current written reason."""
    for conflict in conflicts:
        reason = acknowledgements.get(conflict.fingerprint)
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
            raise ValidationError(
                "Resolve each cross-plan conflict or record a current written reason"
            )
