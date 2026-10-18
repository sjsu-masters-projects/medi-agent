"""The clinician's own schedule and busy times (UX-006)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.exceptions import AuthorizationError, ValidationError
from app.services.appointment_schedule_service import AppointmentScheduleService

NOW = datetime.now(UTC)
CLINIC = "00000000-0000-0000-0000-0000000000c1"


def _service(*result_sets):
    db = MagicMock()
    chain = MagicMock()
    chain.execute.side_effect = [SimpleNamespace(data=data) for data in result_sets]
    for method in ("select", "eq", "order", "in_", "gte", "lt", "limit"):
        getattr(chain, method).return_value = chain
    db.table.return_value = chain
    db.rpc.return_value.execute.return_value = SimpleNamespace(data={"expired_count": 0})
    return AppointmentScheduleService(db), chain


def _row(status="confirmed", hours=2.0, group=None, expires_in=None, patient="p-1", **extra):
    row = {
        "id": str(uuid4()),
        "patient_id": patient,
        "status": status,
        "scheduled_at": (NOW + timedelta(hours=hours)).isoformat(),
        "clinic_id": CLINIC,
        "clinics": {"display_name": "Cedar Grove"},
        "patients": {"first_name": "Maya", "last_name": "Patel"},
        "proposal_group_id": group,
        "proposal_expires_at": (NOW + timedelta(hours=expires_in)).isoformat()
        if expires_in is not None
        else None,
    }
    row.update(extra)
    return row


@pytest.mark.asyncio
async def test_schedule_reads_only_the_callers_own_visits_and_tags_them():
    me = uuid4()
    service, chain = _service([_row()], [], [])
    out = await service.schedule(
        user_id=me, role="clinician", start=NOW, end=NOW + timedelta(days=1)
    )
    chain.eq.assert_any_call("clinician_id", str(me))
    assert out["visits"][0]["patient_name"] == "Maya Patel"
    assert out["visits"][0]["clinic_name"] == "Cedar Grove"
    assert "patients" not in out["visits"][0]


@pytest.mark.asyncio
async def test_schedule_is_for_clinicians_and_bounded():
    service, _ = _service()
    with pytest.raises(AuthorizationError):
        await service.schedule(user_id=uuid4(), role="patient", start=NOW, end=NOW + timedelta(1))
    with pytest.raises(ValidationError):
        await service.schedule(
            user_id=uuid4(), role="clinician", start=NOW, end=NOW + timedelta(days=90)
        )


@pytest.mark.asyncio
async def test_clinic_filter_for_a_foreign_clinic_is_empty_without_reading():
    service, chain = _service()
    with patch(
        "app.services.appointment_schedule_service.ClinicMembershipService.active_memberships",
        new=AsyncMock(return_value=[]),
    ):
        out = await service.schedule(
            user_id=uuid4(),
            role="clinician",
            start=NOW,
            end=NOW + timedelta(days=1),
            clinic_id=uuid4(),
        )
    assert out == {"visits": [], "needs_action": [], "next_visit": None}
    chain.execute.assert_not_called()


@pytest.mark.asyncio
async def test_needs_action_groups_slots_and_flags_expiring_offers():
    g1, g2, g3 = str(uuid4()), str(uuid4()), str(uuid4())
    rows = [
        _row("proposed", 30, g1, expires_in=10),
        _row("proposed", 31, g1, expires_in=10),
        _row("proposed", 50, g2, expires_in=100),
        _row("alternative_requested", 40, g3, patient="p-2"),
        _row("expired", -1, str(uuid4()), expires_in=-5),
        _row("proposed", 60, str(uuid4()), expires_in=-1),  # a dead offer is not "open"
    ]
    service, _ = _service([], rows, [])
    out = await service.schedule(
        user_id=uuid4(), role="clinician", start=NOW, end=NOW + timedelta(days=1)
    )
    items = out["needs_action"]
    assert [(i["kind"], i["slot_count"], i["expiring_soon"]) for i in items] == [
        ("awaiting_reply", 2, True),
        ("awaiting_reply", 1, False),
        ("change_request", 1, False),
        ("expired", 1, False),
    ]


@pytest.mark.asyncio
async def test_busy_times_carry_intervals_and_clinics_never_patients():
    service, chain = _service(
        [
            {
                "scheduled_at": (NOW + timedelta(hours=1)).isoformat(),
                "duration_minutes": 30,
                "clinic_id": CLINIC,
                "clinics": {"display_name": "Cedar Grove"},
                "patient_id": "must-not-leak",
            },
            {  # ended before the range starts
                "scheduled_at": (NOW - timedelta(hours=3)).isoformat(),
                "duration_minutes": 30,
                "clinic_id": CLINIC,
                "clinics": {"display_name": "Cedar Grove"},
            },
        ]
    )
    me = uuid4()
    out = await service.busy(user_id=me, role="clinician", start=NOW, end=NOW + timedelta(hours=24))
    assert len(out) == 1
    assert set(out[0]) == {"starts_at", "ends_at", "clinic_id", "clinic_name"}
    assert out[0]["clinic_name"] == "Cedar Grove"
    chain.eq.assert_any_call("clinician_id", str(me))
    selected = chain.select.call_args.args[0]
    assert "patient" not in selected
