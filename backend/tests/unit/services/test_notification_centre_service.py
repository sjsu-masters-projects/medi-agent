"""Mark-all-read reports what was marked and what was skipped; no real database."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import ExternalServiceError, ValidationError
from app.models.auth import CurrentUser
from app.models.notification_centre import CentreReadThroughResult
from app.services.notification_centre_service import NotificationCentreService
from app.services.notification_centre_tokens import issue_token


@pytest.fixture
def service():
    db = MagicMock()
    actor = CurrentUser(id=uuid4(), email="synthetic@example.com", role="clinician", aal="aal2")
    return NotificationCentreService(db, actor), db


def respond(db, data):
    db.rpc.return_value.execute.return_value = SimpleNamespace(data=data)


@pytest.mark.asyncio
async def test_read_through_returns_marked_and_skipped_counts(service):
    svc, db = service
    ids = [str(uuid4()), str(uuid4())]
    respond(db, {"updated_count": 1, "skipped_count": 1})
    result = await svc.read_through(issue_token(svc.actor, "read", ids))
    assert result == CentreReadThroughResult(updated_count=1, skipped_count=1)
    db.rpc.assert_called_once_with(
        "notification_centre_operation",
        {
            "p_actor_id": str(svc.actor.id),
            "p_actor_role": "clinician",
            "p_action": "read_through",
            "p_payload": {"ids": ids},
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data", [{"updated_count": 1}, {"updated_count": -1, "skipped_count": 0}, {"updated": 1}]
)
async def test_read_through_rejects_an_unexpected_database_result(service, data):
    svc, db = service
    respond(db, data)
    with pytest.raises(ExternalServiceError):
        await svc.read_through(issue_token(svc.actor, "read", [str(uuid4())]))


@pytest.mark.asyncio
async def test_read_through_rejects_oversized_or_foreign_views_before_rpc(service):
    svc, db = service
    with pytest.raises(ValidationError):
        await svc.read_through(issue_token(svc.actor, "read", [str(uuid4())] * 1001))
    other = CurrentUser(id=uuid4(), email="other@example.com", role="clinician", aal="aal2")
    with pytest.raises(ValidationError):
        await svc.read_through(issue_token(other, "read", [str(uuid4())]))
    db.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_clinic_filter_reaches_the_database_only_for_a_clinician(service):
    svc, db = service
    clinic = uuid4()
    respond(db, {"items": [], "read_ids": [], "next_cursor": None})
    await svc.page({"limit": 10, "clinic_id": clinic})
    assert db.rpc.call_args.args[1]["p_payload"]["clinic_id"] == str(clinic)
    await svc.action_items({"limit": 10, "clinic_id": clinic})
    assert db.rpc.call_args.args[1]["p_payload"]["clinic_id"] == str(clinic)
    await svc.page({"limit": 10})
    assert "clinic_id" not in db.rpc.call_args.args[1]["p_payload"]
    svc.actor.role = "patient"
    await svc.page({"limit": 10, "clinic_id": clinic})
    assert "clinic_id" not in db.rpc.call_args.args[1]["p_payload"]
