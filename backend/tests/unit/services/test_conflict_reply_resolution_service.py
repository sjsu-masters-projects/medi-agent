"""The asking clinician resolves a conflict reply (service layer; SQL is covered in Postgres)."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from postgrest.exceptions import APIError

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.services.care_plan_review_service import CarePlanReviewService


def service(rpc_result=None, error_code: str | None = None):
    db = MagicMock()
    call = db.rpc.return_value.execute
    if error_code:
        call.side_effect = APIError({"message": "denied", "code": error_code})
    else:
        call.return_value = MagicMock(data=rpc_result)
    return CarePlanReviewService(db), db


def test_accept_passes_the_action_and_returns_the_blocker_check() -> None:
    item, actor = uuid4(), uuid4()
    svc, db = service({"status": "resolved", "still_blocking": True})

    result = svc.resolve_conflict_reply(actor, item, "accept", None)

    assert result["still_blocking"] is True
    db.rpc.assert_called_once_with(
        "resolve_conflict_reply",
        {"p_item_id": str(item), "p_actor_id": str(actor), "p_action": "accept", "p_reason": None},
    )


def test_keep_both_sends_the_trimmed_reason() -> None:
    svc, db = service({"status": "resolved"})
    svc.resolve_conflict_reply(uuid4(), uuid4(), "keep_both", "  both agreed  ")
    assert db.rpc.call_args.args[1]["p_reason"] == "both agreed"


@pytest.mark.parametrize(
    ("code", "error"),
    [("42501", NotFoundError), ("40001", ConflictError), ("22023", ValidationError)],
)
def test_database_refusals_become_the_matching_api_errors(code, error) -> None:
    svc, _ = service(error_code=code)
    with pytest.raises(error):
        svc.resolve_conflict_reply(uuid4(), uuid4(), "accept", None)
