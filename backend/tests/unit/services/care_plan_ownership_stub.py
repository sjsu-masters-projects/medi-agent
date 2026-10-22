"""Make a CarePlanService act for the owner of the plan under test (ownership has its own tests)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID
from unittest.mock import MagicMock

CARE_PLAN_ID = "00000000-0000-0000-0000-0000000000cc"
CARE_TEAM_ID = "00000000-0000-0000-0000-0000000000dd"


def stub_ownership(service: Any, *, patient_id: str | None = None) -> None:
    """The clinician owns the plan; version/plan lookups succeed without touching the database."""
    plan = {
        "id": CARE_PLAN_ID,
        "care_team_id": CARE_TEAM_ID,
        "ownership_state": "owned",
        "origin": "native",
        "patient_id": patient_id,
    }
    service.lineage = MagicMock()
    service.lineage.require_owned_version.return_value = (
        {"id": "v", "care_plan_id": CARE_PLAN_ID},
        plan,
    )
    service.lineage.select_owned_plan.return_value = plan
    service.lineage.plan.return_value = plan
    service._own_plan_item_ids = MagicMock(return_value=set())
    service.lineage.scope_for_team.return_value = SimpleNamespace(care_team_id=UUID(CARE_TEAM_ID))
    service.lineage.ensure_plan_id.return_value = UUID(CARE_PLAN_ID)
