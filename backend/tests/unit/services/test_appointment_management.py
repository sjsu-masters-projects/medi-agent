"""Clinician visit management: edit rules, cancel, complete, no-show (UX-006)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError as SchemaError

from app.core.exceptions import AuthorizationError, ValidationError
from app.models.appointment import AppointmentCancel
from app.services.appointment_calendar import render_appointment_calendar
from app.services.appointment_service import AppointmentService
from app.services.cron_service import CronService

PATIENT = "6b2f0c1e-0000-4000-8000-000000000002"


def _row(status="confirmed", clinician=None, group=None, **extra):
    return {
        "id": "5b2f0c1e-0000-4000-8000-000000000001",
        "patient_id": PATIENT,
        "care_team_id": "7b2f0c1e-0000-4000-8000-000000000003",
        "clinician_id": str(clinician or uuid4()),
        "clinic_id": "8b2f0c1e-0000-4000-8000-000000000004",
        "clinics": {"display_name": "Cedar Grove"},
        "status": status,
        "proposal_group_id": group,
        "scheduled_at": "2026-10-20T16:00:00Z",
        "duration_minutes": 30,
        "appointment_type": "follow_up",
        "created_at": "2026-10-01T00:00:00Z",
        **extra,
    }


def _service(*results, rpc=None):
    db = MagicMock()
    chain = MagicMock()
    chain.execute.side_effect = [SimpleNamespace(data=data) for data in results]
    for method in ("select", "eq", "limit", "update", "in_", "order"):
        getattr(chain, method).return_value = chain
    db.table.return_value = chain
    if rpc is not None:
        db.rpc.return_value.execute.return_value = SimpleNamespace(data=rpc)
    return AppointmentService(db), db, chain


def _done(status="cancelled", **extra):
    return {"appointment": _row(status, **extra)}


# ── authorization ──────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_owner_cancels_and_the_rpc_carries_the_actor_and_reason():
    me = uuid4()
    service, db, _ = _service([_row(clinician=me)], rpc=_done(cancelled_by="clinician"))
    out = await service.manage_for_user(
        user_id=me,
        role="clinician",
        appointment_id=uuid4(),
        action="cancel",
        reason_code="clinic_closed",
        reason="Water leak",
    )
    name, params = db.rpc.call_args.args
    assert name == "manage_appointment"
    assert params["p_actor_id"] == str(me)
    assert (params["p_action"], params["p_reason_code"], params["p_reason"]) == (
        "cancel",
        "clinic_closed",
        "Water leak",
    )
    assert out["status"] == "cancelled"
    assert out["clinic_name"] == "Cedar Grove"


@pytest.mark.asyncio
async def test_a_same_clinic_colleague_with_a_link_may_cancel():
    service, db, _ = _service([_row()], [{"id": "link"}], rpc=_done())
    await service.manage_for_user(
        user_id=uuid4(),
        role="clinician",
        appointment_id=uuid4(),
        action="cancel",
        reason_code="clinician_unavailable",
    )
    db.rpc.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["cancel", "complete", "no_show"])
async def test_an_outsider_is_refused_before_the_rpc(action):
    service, db, _ = _service([_row()], [])  # no link at the appointment's clinic
    with pytest.raises(AuthorizationError):
        await service.manage_for_user(
            user_id=uuid4(), role="clinician", appointment_id=uuid4(), action=action
        )
    db.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_a_patient_cannot_use_clinician_actions():
    service, db, _ = _service()
    with pytest.raises(AuthorizationError):
        await service.manage_for_user(
            user_id=uuid4(), role="patient", appointment_id=uuid4(), action="cancel"
        )
    db.table.assert_not_called()
    db.rpc.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "code"),
    [
        ("stale", "APPOINTMENT_UNAVAILABLE"),
        ("too_early", "APPOINTMENT_NOT_ENDED"),
    ],
)
async def test_a_wrong_status_or_unfinished_visit_is_a_validation_error(error, code):
    me = uuid4()
    service, _, _ = _service([_row(clinician=me)], rpc={"error": error})
    with pytest.raises(ValidationError) as caught:
        await service.manage_for_user(
            user_id=me, role="clinician", appointment_id=uuid4(), action="complete"
        )
    assert caught.value.code == code


@pytest.mark.asyncio
async def test_cancelling_an_already_cancelled_visit_is_refused():
    me = uuid4()
    service, _, _ = _service([_row("cancelled", clinician=me)], rpc={"error": "stale"})
    with pytest.raises(ValidationError):
        await service.manage_for_user(
            user_id=me,
            role="clinician",
            appointment_id=uuid4(),
            action="cancel",
            reason_code="other",
            reason="x",
        )


def test_a_cancel_needs_a_reason_and_other_needs_text():
    with pytest.raises(SchemaError):
        AppointmentCancel.model_validate({})
    with pytest.raises(SchemaError):
        AppointmentCancel.model_validate({"reason_code": "other", "reason": "  "})
    assert AppointmentCancel.model_validate({"reason_code": "clinic_closed"}).reason is None


# ── edit rules ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["confirmed", "scheduled"])
@pytest.mark.parametrize("field", ["scheduled_at", "duration_minutes"])
async def test_a_booked_visits_time_cannot_be_changed_directly(status, field):
    me = uuid4()
    service, _, chain = _service([_row(status, clinician=me)])
    value = "2026-10-21T16:00:00Z" if field == "scheduled_at" else 45
    with pytest.raises(ValidationError) as caught:
        await service.update_for_user(
            user_id=me, role="clinician", appointment_id=uuid4(), data={field: value}
        )
    assert caught.value.code == "APPOINTMENT_TIME_CHANGE_VIA_OFFER"
    chain.update.assert_not_called()


@pytest.mark.asyncio
async def test_details_of_a_confirmed_visit_from_an_offer_can_be_edited():
    me = uuid4()
    group = str(uuid4())
    changed = _row("confirmed", clinician=me, group=group, location="Suite 3")
    service, db, chain = _service(
        [_row("confirmed", clinician=me, group=group)], rpc={"appointment": changed}
    )
    out = await service.update_for_user(
        user_id=me,
        role="clinician",
        appointment_id=uuid4(),
        data={"location": "Suite 3", "appointment_type": "routine"},
    )
    chain.update.assert_not_called()
    assert db.rpc.call_args.args[0] == "edit_appointment_details"
    assert db.rpc.call_args.args[1]["p_changes"] == {
        "location": "Suite 3",
        "appointment_type": "routine",
    }
    assert out["location"] == "Suite 3"


@pytest.mark.asyncio
async def test_details_of_an_open_offer_reach_every_open_slot():
    me = uuid4()
    group = str(uuid4())
    service, db, chain = _service(
        [_row("proposed", clinician=me, group=group)],
        rpc={"appointment": _row("proposed", clinician=me, group=group, reason="New")},
    )
    await service.update_for_user(
        user_id=me, role="clinician", appointment_id=uuid4(), data={"reason": "New"}
    )
    chain.update.assert_not_called()
    assert db.rpc.call_args.args[1]["p_changes"] == {"reason": "New"}


@pytest.mark.asyncio
async def test_a_grouped_offers_time_and_status_stay_with_the_offer_workflow():
    me = uuid4()
    service, _, chain = _service([_row("proposed", clinician=me, group=str(uuid4()))])
    with pytest.raises(ValidationError):
        await service.update_for_user(
            user_id=me,
            role="clinician",
            appointment_id=uuid4(),
            data={"scheduled_at": "2026-10-21T16:00:00Z"},
        )
    chain.update.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["cancelled", "completed", "no_show", "declined"])
async def test_a_finished_visit_cannot_be_edited(status):
    me = uuid4()
    service, _, chain = _service([_row(status, clinician=me)])
    with pytest.raises(ValidationError):
        await service.update_for_user(
            user_id=me, role="clinician", appointment_id=uuid4(), data={"reason": "x"}
        )
    chain.update.assert_not_called()


@pytest.mark.asyncio
async def test_an_outsider_cannot_edit_details():
    service, _, chain = _service([_row()], [])
    with pytest.raises(AuthorizationError):
        await service.update_for_user(
            user_id=uuid4(), role="clinician", appointment_id=uuid4(), data={"reason": "x"}
        )
    chain.update.assert_not_called()


# ── what follows a cancel ──────────────────────────────────────────────────────────────────


def test_a_cancelled_visit_exports_as_cancelled():
    from app.models.appointment import AppointmentRead

    visit = AppointmentRead.model_validate(_row("cancelled"))
    assert "STATUS:CANCELLED" in render_appointment_calendar(visit, "en-US").content
    booked = AppointmentRead.model_validate(_row("confirmed"))
    assert "STATUS:CONFIRMED" in render_appointment_calendar(booked, "es-MX").content


@pytest.mark.asyncio
async def test_calendar_export_is_allowed_for_cancelled_but_not_completed_visits():
    me = uuid4()
    service, _, _ = _service([_row("cancelled", clinician=me)])
    out = await service.export_calendar_for_user(
        user_id=me, role="clinician", appointment_id=uuid4(), locale="en-US"
    )
    assert "STATUS:CANCELLED" in out.content
    service, _, _ = _service([_row("completed", clinician=me)])
    with pytest.raises(ValidationError):
        await service.export_calendar_for_user(
            user_id=me, role="clinician", appointment_id=uuid4(), locale="en-US"
        )


def test_reminders_are_only_for_booked_visits():
    assert "cancelled" not in CronService.BOOKED_APPOINTMENT_STATUSES
    assert set(CronService.BOOKED_APPOINTMENT_STATUSES) == {"confirmed", "scheduled"}


@pytest.mark.parametrize(
    ("locale", "title"), [("en-US", "Appointment cancelled"), ("es-MX", "Cita cancelada")]
)
def test_the_cancel_notice_is_bilingual_and_a_plain_change_is_not(locale, title):
    from app.services.notification_centre_presentation import present_item

    row = {
        "id": str(uuid4()),
        "source_id": str(uuid4()),
        "patient_id": str(uuid4()),
        "event_type": "appointment_changed",
        "category": "appointments",
        "metadata": {"status": "cancelled", "appointment_id": str(uuid4())},
        "created_at": "2026-10-17T12:00:00Z",
        "is_read": False,
        "actionable": True,
    }
    assert present_item(row, "patient", locale).title == title
    row["metadata"] = {"status": "confirmed", "appointment_id": str(uuid4())}
    assert present_item(row, "patient", locale).title != title


@pytest.mark.parametrize(
    ("locale", "subject"), [("en-US", "Appointment cancelled"), ("es-MX", "Cita cancelada")]
)
def test_the_cancel_email_is_bilingual_and_carries_no_health_detail(locale, subject):
    from app.services.email_service import EmailDeliveryService

    service = EmailDeliveryService(MagicMock())
    with patch("app.services.email_service.settings") as config:
        config.patient_portal_url = "https://app.example.com"
        config.clinician_portal_url = "https://clinic.example.com"
        payload = service._payload(
            {
                "role": "patient",
                "locale": locale,
                "email": "owner@example.com",
                "event": {
                    "event_type": "appointment_changed",
                    "category": "appointments",
                    "patient_id": PATIENT,
                    "metadata": {"status": "cancelled", "cancel_reason": "private reason"},
                },
            }
        )
    assert subject in str(payload)
    assert "private reason" not in str(payload)
