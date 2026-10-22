"""Presenter and service behavior with a synthetic database card; SQL is tested separately."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from postgrest.exceptions import APIError

from app.core.exceptions import (
    AuthorizationError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from app.services.symptom_report_history_service import SymptomReportHistoryService
from app.services.symptom_report_presenter import present_clinician, present_list_item

PATIENT = uuid4()
REPORT = uuid4()
TEAM = uuid4()
OTHER_TEAM = uuid4()


def card(**over):
    base = {
        "id": str(REPORT),
        "patient_id": str(PATIENT),
        "symptom": "Dizziness",
        "severity": 6,
        "onset": "Yesterday",
        "duration": "Two hours",
        "body_area": None,
        "confirmed_at": "2026-10-20T17:00:00+00:00",
        "locale": "es-MX",
        "timezone": "America/Los_Angeles",
        "handoff_state": "sent",
        "handed_off_at": "2026-10-20T17:00:01+00:00",
        "escalation": None,
        "reviews": [],
        "viewer_care_team_ids": [str(TEAM)],
        "summary": "x",
        "answers": {
            "severity": {"state": "answered", "value": 6, "wording": "seis"},
            "course": {"state": "unknown", "value": None},
            "product": {"state": "answered", "value": {"concern": True, "name": "Prueba"}},
        },
        "provenance": {
            "report_id": str(REPORT),
            "intake_id": str(uuid4()),
            "source_message_id": str(uuid4()),
            "consent_recorded": True,
        },
        "safety": {"rule_version": "triage-floor/1", "result": "no_existing_rule_matched"},
    }
    return {**base, **over}


def review(team, name, mine, at="2026-10-21T01:00:00+00:00", label="Cardiology · Cedar Grove"):
    return {
        "care_team_id": str(team),
        "team_label": label,
        "reviewed_by_name": name,
        "reviewed_at": at,
        "mine": mine,
    }


def test_only_recorded_events_and_status():
    item = present_list_item(card(handoff_state="unrecorded", handed_off_at=None))
    assert [e.kind for e in item.events] == ["reported"] and item.status == "reported"
    assert item.handoff == "unrecorded"
    item = present_list_item(card(reviews=[review(TEAM, "A B", True)]))
    assert [e.kind for e in item.events] == ["reported", "shared_with_care_team", "reviewed"]
    assert item.status == "reviewed" and item.events[-1].actor_name == "A B"


def test_no_active_care_team_is_shown_as_not_sent_never_as_sent():
    item = present_list_item(card(handoff_state="not_sent", handed_off_at=None))
    kinds = [e.kind for e in item.events]
    assert kinds == ["reported", "not_sent_no_care_team"]
    assert item.status == "not_sent" and item.handoff == "not_sent"
    assert "shared_with_care_team" not in kinds
    # A claimed hand-off time without a recorded recipient count is never trusted.
    odd = present_list_item(card(handoff_state="not_sent"))
    assert "shared_with_care_team" not in [e.kind for e in odd.events]


def test_each_team_review_is_its_own_event_and_marked_mine_for_the_viewer():
    report = present_clinician(
        card(
            reviews=[
                review(OTHER_TEAM, "Pat Park", False),
                review(TEAM, "Me Myself", True, "2026-10-21T02:00:00+00:00"),
            ]
        )
    )
    assert [r.mine for r in report.reviews] == [False, True]
    assert report.reviewed_by_your_team is True
    assert [e.actor_name for e in report.events if e.kind == "reviewed"] == [
        "Pat Park",
        "Me Myself",
    ]
    other_only = present_clinician(card(reviews=[review(OTHER_TEAM, "Pat Park", False)]))
    assert other_only.reviewed_by_your_team is False and len(other_only.reviews) == 1


def test_escalation_event_requires_delivery():
    undelivered = {
        "urgency": "urgent",
        "at": "2026-10-20T17:00:02+00:00",
        "delivery_state": "no_recipients",
    }
    assert "flagged_urgent" not in [
        e.kind for e in present_list_item(card(escalation=undelivered)).events
    ]
    delivered = {**undelivered, "delivery_state": "delivered"}
    assert "flagged_urgent" in [
        e.kind for e in present_list_item(card(escalation=delivered)).events
    ]


def test_answers_are_in_the_patient_language_and_never_estimated():
    report = present_clinician(card())
    by_id = {a.question_id: a for a in report.answers}
    assert by_id["severity"].label == "Intensidad (0 a 10)" and by_id["severity"].display == "6"
    assert by_id["course"].display == "No sé" and by_id["course"].state == "unknown"
    assert "Producto: Prueba" in by_id["product"].display
    assert report.reviews == [] and report.provenance.consent_recorded
    assert report.triage.safety_result == "no_existing_rule_matched"


def rpc_service(result=None, error=None, authorize=None):
    db = MagicMock()
    execute = (
        MagicMock(side_effect=error) if error else MagicMock(return_value=MagicMock(data=result))
    )
    db.rpc.return_value.execute = execute
    return SymptomReportHistoryService(db, authorize), db


@pytest.mark.asyncio
async def test_clinician_denial_stops_before_any_read():
    denied = AsyncMock(side_effect=AuthorizationError("no"))
    service, db = rpc_service(card(), authorize=denied)
    with pytest.raises(AuthorizationError):
        await service.detail_for_clinician(uuid4(), PATIENT, REPORT)
    db.rpc.assert_not_called()


@pytest.mark.asyncio
async def test_database_denial_is_not_found_and_failure_is_unavailable():
    service, _ = rpc_service(error=APIError({"code": "42501", "message": "Report unavailable"}))
    with pytest.raises(NotFoundError):
        await service.detail_for_patient(PATIENT, REPORT)
    service, _ = rpc_service(error=APIError({"code": "XX000", "message": "boom"}))
    with pytest.raises(ServiceUnavailableError):
        await service.detail_for_patient(PATIENT, REPORT)


@pytest.mark.asyncio
async def test_review_passes_clinician_identity_and_marks_idempotent_result():
    service, db = rpc_service(card(already_reviewed=True), authorize=AsyncMock())
    clinician = uuid4()
    report = await service.mark_reviewed(clinician, PATIENT, REPORT, TEAM)
    assert db.rpc.call_args.args[1]["p_payload"]["care_team_id"] == str(TEAM)
    args = db.rpc.call_args.args[1]
    assert args["p_actor_id"] == str(clinician) and args["p_action"] == "review"
    assert args["p_payload"]["patient_id"] == str(PATIENT) and report.already_reviewed is True


@pytest.mark.asyncio
async def test_patient_list_uses_only_own_identity():
    service, db = rpc_service({"items": [card()], "has_more": False})
    service._timezone = AsyncMock(return_value="America/Los_Angeles")  # type: ignore[method-assign]
    result = await service.list_for_patient(PATIENT)
    assert db.rpc.call_args.args[1]["p_actor_id"] == str(PATIENT)
    assert db.rpc.call_args.args[1]["p_actor_role"] == "patient"
    assert result.timezone == "America/Los_Angeles" and len(result.items) == 1


@pytest.mark.asyncio
async def test_several_links_without_a_choice_asks_for_a_care_team():
    service, _ = rpc_service(
        error=APIError({"code": "P0001", "message": "CARE_TEAM_REQUIRED"}), authorize=AsyncMock()
    )
    with pytest.raises(ValidationError) as caught:
        await service.mark_reviewed(uuid4(), PATIENT, REPORT)
    assert caught.value.code == "CARE_TEAM_REQUIRED"
