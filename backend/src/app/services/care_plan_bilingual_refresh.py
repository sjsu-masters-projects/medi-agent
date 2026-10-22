"""Bring existing care plans to bilingual wording through the normal review path.

Approved and superseded versions are never edited, and nothing here approves anything:
an open draft gets its missing language drafted for clinician review, and an approved
plan with single-language items gets a normal generation request, whose new draft
carries the approved wording forward and is translated for review. Reports carry
identifiers and counts only, never wording.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast
from uuid import UUID

from supabase import Client

from app.models.care_plan import PATIENT_LOCALES
from app.services.care_plan_service import CarePlanService

Action = Literal["translate_open_draft", "request_bilingual_draft"]
_OPEN_REQUESTS = ("pending", "processing", "retry")


@dataclass(frozen=True)
class RefreshProposal:
    patient_id: str
    care_plan_id: str
    plan_version_id: str
    version_number: int
    plan_status: str
    action: Action
    single_language_item_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _single_language(item: dict[str, Any]) -> bool:
    wording = cast(dict[str, Any], item.get("wording") or {})
    return not item.get("is_removed") and any(not wording.get(locale) for locale in PATIENT_LOCALES)


class BilingualRefreshService:
    def __init__(self, db: Client) -> None:
        self.db = db
        self.plans = CarePlanService(db)

    def proposals(self, *, patient_id: UUID | None = None) -> list[RefreshProposal]:
        query = (
            self.db.table("care_plan_versions")
            .select("id, patient_id, care_plan_id, version_number, status")
            .in_("status", ["draft", "approved"])
        )
        if patient_id is not None:
            query = query.eq("patient_id", str(patient_id))
        versions = cast(list[dict[str, Any]], query.execute().data or [])
        # Each care plan is refreshed on its own; nothing here crosses plans.
        by_plan: dict[str, dict[str, dict[str, Any]]] = {}
        for version in versions:
            by_plan.setdefault(str(version["care_plan_id"]), {})[str(version["status"])] = version
        queued = self._plans_with_open_requests(list(by_plan))
        proposals: list[RefreshProposal] = []
        for care_plan, plans in sorted(by_plan.items()):
            # An open draft is where review happens; translate it rather than queue another.
            plan = plans.get("draft") or plans.get("approved")
            if plan is None:
                continue
            missing = sum(
                1 for item in self.plans._items(UUID(str(plan["id"]))) if _single_language(item)
            )
            if not missing:
                continue
            if plan["status"] == "approved" and care_plan in queued:
                continue  # The queued generation already produces a reviewable draft.
            proposals.append(
                RefreshProposal(
                    patient_id=str(plan["patient_id"]),
                    care_plan_id=care_plan,
                    plan_version_id=str(plan["id"]),
                    version_number=int(plan["version_number"]),
                    plan_status=str(plan["status"]),
                    action="translate_open_draft"
                    if plan["status"] == "draft"
                    else "request_bilingual_draft",
                    single_language_item_count=missing,
                )
            )
        return proposals

    async def apply(self, proposal: RefreshProposal) -> dict[str, Any]:
        if proposal.action == "translate_open_draft":
            diagnostics = await self.plans._draft_missing_translations(
                UUID(proposal.plan_version_id)
            )
            self.plans._audit(
                UUID(proposal.plan_version_id), None, "bilingual_refresh_drafted", diagnostics
            )
            return {**proposal.to_dict(), **diagnostics}
        self.plans.request_generation_for_plan(UUID(proposal.care_plan_id), datetime.now(UTC))
        return {**proposal.to_dict(), "generation_requested": True}

    def _plans_with_open_requests(self, plans: list[str]) -> set[str]:
        if not plans:
            return set()
        rows = cast(
            list[dict[str, Any]],
            self.db.table("care_plan_generation_requests")
            .select("care_plan_id")
            .in_("care_plan_id", plans)
            .in_("status", list(_OPEN_REQUESTS))
            .execute()
            .data
            or [],
        )
        return {str(row["care_plan_id"]) for row in rows}
