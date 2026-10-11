"""Notification copy does not translate clinical text or misstate review authority."""

from uuid import uuid4

import pytest

from app.services.notification_centre_presentation import _COPY, destination, present_item


def item(**changes):
    return {
        "id": str(uuid4()),
        "source_id": str(uuid4()),
        "patient_id": str(uuid4()),
        "event_type": "document_review",
        "category": "documents",
        "metadata": {},
        "created_at": "2026-10-11T12:00:00Z",
        "is_read": False,
        "actionable": True,
        **changes,
    }


@pytest.mark.parametrize("kind", list(_COPY))
def test_all_event_templates_are_bilingual_and_clinician_chrome_stays_english(kind):
    raw = item(event_type=kind)
    english = present_item(raw, "patient", "en-US")
    spanish = present_item(raw, "patient", "es-MX")
    clinician = present_item(raw, "clinician", "es-MX")
    assert english.title != spanish.title
    assert clinician.title == english.title
    assert clinician.action_label == present_item(raw, "clinician", "en-US").action_label


@pytest.mark.parametrize(
    "category,kind",
    [
        ("messages", "message_received"),
        ("appointments", "appointment_offered"),
        ("documents", "document_processed"),
        ("care_plans", "care_plan_published"),
        ("reminders", "med_reminder"),
        ("follow_up", "barrier_reported"),
        ("safety", "adr_review"),
        ("safety", "safety_flag"),
    ],
)
@pytest.mark.parametrize("role", ["patient", "clinician"])
def test_destinations_are_internal_and_include_exact_source(category, kind, role):
    raw = item(category=category, event_type=kind)
    link, _, _ = destination(raw, role)
    assert link is None or (link.startswith("/") and not link.startswith("//"))
    assert "https:" not in (link or "")


def test_untrusted_url_is_never_used_as_destination():
    raw = item(
        source_id="https://malicious.invalid",
        patient_id="//other.invalid",
        metadata={"action_url": "https://malicious.invalid"},
    )
    assert present_item(raw, "patient", "en-US").action_url is None


def test_stale_activity_has_no_action_and_read_is_not_acknowledgment():
    raw = item(event_type="barrier_reported", category="follow_up", actionable=False, is_read=True)
    result = present_item(raw, "clinician", "en-US")
    # History keeps its link to the exact source, but no longer asks for action.
    assert result.action_url is not None and result.action_label == "View"
    assert not result.can_acknowledge
    assert "not a confirmed" in result.body


def test_internal_identifiers_are_not_names_or_visible_copy():
    raw = item(
        event_type="message_received",
        category="messages",
        actor_name=str(uuid4()),
        clinic_name=str(uuid4()),
    )
    result = present_item(raw, "patient", "es-MX")
    assert raw["actor_name"] not in result.title and raw["clinic_name"] not in result.body


def test_information_request_opens_the_requesting_recipient():
    recipient = str(uuid4())
    raw = item(
        event_type="adr_information_requested",
        category="safety",
        metadata={"clinician_id": recipient},
    )
    result = present_item(raw, "patient", "es-MX")
    assert result.action_url == f"/chat?view=care-team&recipient={recipient}"
    assert not result.can_acknowledge


def test_unknown_event_does_not_echo_raw_metadata():
    result = present_item(
        item(event_type="future_event", metadata={"title": "Private SQL", "body": "internal id"}),
        "patient",
        "en-US",
    )
    assert result.title == "Update available"
    assert "Private SQL" not in result.body


def test_reviewed_information_questions_are_shown_as_written_not_translated():
    question = "When did the reported symptom begin?"
    raw = item(
        event_type="adr_information_requested",
        category="safety",
        metadata={"requested_information": [question, {"internal": "ignore"}]},
    )
    result = present_item(raw, "patient", "es-MX")
    assert question in result.body and "texto original" in result.body
    assert "internal" not in result.body
