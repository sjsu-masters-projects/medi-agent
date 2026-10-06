"""Exercise real assignment/ownership guards before clinical reads or writes."""

from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.core.security import get_current_user
from app.main import app
from app.models.auth import CurrentUser
from app.routers.care_plans import _service
from app.services.care_plan_service import CarePlanService

PATIENT = UUID("00000000-0000-0000-0000-000000000301")
OUTSIDER = UUID("00000000-0000-0000-0000-000000000302")
PLAN = UUID("00000000-0000-0000-0000-000000000303")
BASE = f"/api/v1/care-plans/clinician/patients/{PATIENT}"
EDIT = {
    "items": [
        {
            "id": str(PLAN),
            "title": "Synthetic activity",
            "instructions": "Synthetic instruction",
            "frequency": "daily",
        }
    ]
}


@pytest.fixture
def guarded_service():
    db = MagicMock()
    query = db.table.return_value
    for method in ("select", "eq", "limit"):
        getattr(query, method).return_value = query
    query.execute.return_value.data = []
    app.dependency_overrides[_service] = lambda: CarePlanService(db)
    yield db
    app.dependency_overrides.clear()


@pytest.mark.parametrize("role", ["patient", "clinician"])
@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("GET", "", None),
        ("GET", "/review-context", None),
        ("GET", "/generation", None),
        ("PUT", f"/{PLAN}", EDIT),
        ("POST", f"/{PLAN}/approve", {"note": "Synthetic access-denial test"}),
        ("POST", "/retry-generation", None),
    ],
)
def test_outsider_cannot_read_edit_approve_or_retry(
    client, guarded_service, denial_audit, role, method, suffix, body
):
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=OUTSIDER, email="outsider@example.test", role=role, aal="aal2"
    )

    response = client.request(method, BASE + suffix, json=body)

    assert response.status_code == 403
    guarded_service.rpc.assert_not_called()
    guarded_service.table.return_value.insert.assert_not_called()
    guarded_service.table.return_value.update.assert_not_called()
    if role == "clinician":
        assert {call.args[0] for call in guarded_service.table.call_args_list} == {"care_teams"}
        guarded_service.table.return_value.eq.assert_any_call("patient_id", str(PATIENT))
        assert denial_audit[0]["reason_code"] == "NO_CARE_TEAM_ASSIGNMENT"
    else:
        guarded_service.table.assert_not_called()


def test_patient_cannot_read_another_patients_approved_plan(client, guarded_service):
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=OUTSIDER, email="outsider@example.test", role="patient"
    )

    response = client.get(f"/api/v1/care-plans/patients/{PATIENT}")

    assert response.status_code == 403
    guarded_service.table.assert_not_called()
