"""Notification and email wording follows record ownership (PLAN-002 / CLN-003 slice G).

The recipient rule itself lives in the database (087, covered by the disposable PostgreSQL
contract tests). These tests pin what the Python layer adds: the clinic an email names and the
link and copy of a shared critical-result alert a team cannot open. Synthetic data only.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.email_service import EmailDeliveryService
from app.services.notification_centre_presentation import destination, present_item
from tests.unit.services.care_team_fake_db import (
    CLINIC,
    CLINICIAN,
    OTHER_CLINIC,
    OTHER_TEAM,
    PATIENT,
    TEAM,
    FakeDB,
)

PLAN = str(uuid4())
VERSION = str(uuid4())
DOCUMENT = str(uuid4())


def tables(**extra):
    return FakeDB(
        {
            "care_teams": [
                {
                    "id": TEAM,
                    "patient_id": PATIENT,
                    "clinician_id": CLINICIAN,
                    "clinic_id": CLINIC,
                    "status": "active",
                },
                {
                    "id": OTHER_TEAM,
                    "patient_id": PATIENT,
                    "clinician_id": CLINICIAN,
                    "clinic_id": OTHER_CLINIC,
                    "status": "active",
                },
            ],
            "clinic_memberships": [
                {"clinician_id": CLINICIAN, "clinic_id": CLINIC, "status": "active"},
                {"clinician_id": CLINICIAN, "clinic_id": OTHER_CLINIC, "status": "active"},
            ],
            "clinics": [
                {"id": CLINIC, "display_name": "Cedar Grove"},
                {"id": OTHER_CLINIC, "display_name": "Birch Clinic"},
            ],
            "documents": [{"id": DOCUMENT, "care_team_id": OTHER_TEAM, "routing_state": "routed"}],
            "care_plans": [{"id": PLAN, "care_team_id": OTHER_TEAM}],
            "care_plan_versions": [{"id": VERSION, "care_plan_id": PLAN}],
            "adr_assessments": [],
            **extra,
        }
    )


def notice(source_type: str, source_id: str, kind: str) -> dict:
    return {
        "role": "clinician",
        "user_id": CLINICIAN,
        "event": {
            "event_type": kind,
            "source_type": source_type,
            "source_id": source_id,
            "patient_id": PATIENT,
            "metadata": {},
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_type", "source_id", "kind"),
    [
        ("documents", DOCUMENT, "document_review"),
        ("care_plan_versions", VERSION, "care_plan_draft"),
    ],
)
async def test_a_notice_names_the_clinic_of_the_team_that_owns_the_record(
    source_type, source_id, kind
):
    label = await EmailDeliveryService(tables())._clinic_label(notice(source_type, source_id, kind))
    assert label == "Birch Clinic"


@pytest.mark.asyncio
async def test_a_reviewed_assessment_names_its_reviewing_teams_clinic():
    adr = str(uuid4())
    db = tables(adr_assessments=[{"id": adr, "reviewed_by_care_team_id": TEAM}])
    assert (
        await EmailDeliveryService(db)._clinic_label(notice("adr_assessments", adr, "adr_review"))
        == "Cedar Grove"
    )


@pytest.mark.asyncio
async def test_an_unrouted_or_unowned_record_does_not_pick_one_of_several_clinics():
    # Two links at two clinics and no owner: the notice names no clinic rather than guessing.
    db = tables(documents=[{"id": DOCUMENT, "care_team_id": None, "routing_state": "unrouted"}])
    assert (
        await EmailDeliveryService(db)._clinic_label(
            notice("documents", DOCUMENT, "document_review")
        )
        == ""
    )


@pytest.mark.asyncio
async def test_a_clinician_who_does_not_hold_the_owning_link_gets_no_owner_clinic():
    db = tables()
    db.tables["care_teams"] = [row for row in db.tables["care_teams"] if row["id"] == TEAM]
    # Their only link is Cedar Grove, so the single-link rule applies, never the owner's clinic.
    row = notice("documents", DOCUMENT, "document_review")
    assert await EmailDeliveryService(db)._clinic_label(row) == "Cedar Grove"


def alert(**metadata):
    patient, source = str(uuid4()), str(uuid4())
    return {
        "id": str(uuid4()),
        "event_type": "critical_result",
        "category": "safety",
        "source_type": "documents",
        "source_id": source,
        "patient_id": patient,
        "metadata": metadata,
        "created_at": "2026-10-11T12:00:00Z",
        "is_read": False,
        "actionable": True,
        "can_acknowledge": True,
    }


def test_a_critical_alert_for_a_document_another_team_holds_links_to_the_patient_only():
    raw = alert(source_accessible=False)
    link, label, _ = destination(raw, "clinician")
    assert link == f"/patients/{raw['patient_id']}"
    assert label == "Open patient"
    shown = present_item(raw, "clinician", "en-US")
    assert shown.title == "Critical test result reported"
    assert "another care team" in shown.body
    assert raw["source_id"] not in (shown.action_url or "")
    assert shown.can_acknowledge is True


def test_a_critical_alert_the_team_can_open_still_links_the_exact_document():
    raw = alert()
    link, label, _ = destination(raw, "clinician")
    assert link == f"/patients/{raw['patient_id']}?tab=documents#document-{raw['source_id']}"
    assert label == "Open document"
