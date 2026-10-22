"""Existing plans reach bilingual wording only through draft review, never by approval."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.services.care_plan_bilingual_refresh import BilingualRefreshService
from tests.unit.services.care_plan_wording import verified_wording

DRAFT_PATIENT, APPROVED_PATIENT, QUEUED_PATIENT, DONE_PATIENT = (
    str(UUID(int=n)) for n in (1, 2, 3, 4)
)
DRAFT, DRAFT_BASE, APPROVED, QUEUED, DONE = (str(UUID(int=n)) for n in (11, 12, 13, 14, 15))
SINGLE = {"title": "Caminar", "is_removed": False}
ITEMS = {
    DRAFT: [SINGLE, {**SINGLE, "is_removed": True}],
    DRAFT_BASE: [SINGLE],
    APPROVED: [SINGLE, SINGLE],
    QUEUED: [SINGLE],
    DONE: [{"is_removed": False, **verified_wording()}],
}


def _chain(data: list[dict[str, Any]]) -> MagicMock:
    chain = MagicMock()
    for method in ("select", "in_", "eq"):
        getattr(chain, method).return_value = chain
    chain.execute.return_value.data = data
    return chain


def _service() -> BilingualRefreshService:
    versions = [
        {
            "id": DRAFT,
            "patient_id": DRAFT_PATIENT,
            "care_plan_id": DRAFT_PATIENT,
            "version_number": 4,
            "status": "draft",
        },
        {
            "id": DRAFT_BASE,
            "patient_id": DRAFT_PATIENT,
            "care_plan_id": DRAFT_PATIENT,
            "version_number": 3,
            "status": "approved",
        },
        {
            "id": APPROVED,
            "patient_id": APPROVED_PATIENT,
            "care_plan_id": APPROVED_PATIENT,
            "version_number": 2,
            "status": "approved",
        },
        {
            "id": QUEUED,
            "patient_id": QUEUED_PATIENT,
            "care_plan_id": QUEUED_PATIENT,
            "version_number": 1,
            "status": "approved",
        },
        {
            "id": DONE,
            "patient_id": DONE_PATIENT,
            "care_plan_id": DONE_PATIENT,
            "version_number": 5,
            "status": "approved",
        },
    ]
    db = MagicMock()
    db.table.side_effect = lambda name: _chain(
        versions if name == "care_plan_versions" else [{"care_plan_id": QUEUED_PATIENT}]
    )
    service = BilingualRefreshService(db)
    service.plans._items = MagicMock(  # type: ignore[method-assign]
        side_effect=lambda plan_id: ITEMS[str(plan_id)]
    )
    return service


def test_report_targets_open_drafts_and_unqueued_single_language_plans() -> None:
    proposals = [proposal.to_dict() for proposal in _service().proposals()]
    assert proposals == [
        {
            "patient_id": DRAFT_PATIENT,
            "care_plan_id": DRAFT_PATIENT,
            "plan_version_id": DRAFT,
            "version_number": 4,
            "plan_status": "draft",
            "action": "translate_open_draft",
            "single_language_item_count": 1,
        },
        {
            "patient_id": APPROVED_PATIENT,
            "care_plan_id": APPROVED_PATIENT,
            "plan_version_id": APPROVED,
            "version_number": 2,
            "plan_status": "approved",
            "action": "request_bilingual_draft",
            "single_language_item_count": 2,
        },
    ]


@pytest.mark.asyncio
async def test_apply_drafts_or_requests_review_and_never_approves() -> None:
    service = _service()
    service.plans._draft_missing_translations = AsyncMock(  # type: ignore[method-assign]
        return_value={"translation_drafted_count": 1}
    )
    service.plans._audit = MagicMock()  # type: ignore[method-assign]
    service.plans.request_generation_for_plan = MagicMock()  # type: ignore[method-assign]
    service.plans.approve = MagicMock()  # type: ignore[method-assign]
    draft, approved = service.proposals()

    drafted = await service.apply(draft)
    requested = await service.apply(approved)

    assert drafted["translation_drafted_count"] == 1
    assert service.plans._audit.call_args.args[2] == "bilingual_refresh_drafted"
    assert requested["generation_requested"] is True
    assert service.plans.request_generation_for_plan.call_args.args[0] == UUID(APPROVED_PATIENT)
    service.plans.approve.assert_not_called()
