"""Notification copy does not translate clinical text or misstate review authority."""

import itertools
import re
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

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


def test_unlisted_product_review_names_testimony_and_links_the_exact_report():
    raw = item(
        event_type="safety_flag",
        category="safety",
        source_type="symptom_reports",
        can_acknowledge=True,
    )
    shown = present_item(raw, "clinician", "en-US")
    assert shown.title == "Patient-reported product needs review"
    assert "not a confirmed ADR" in shown.body
    assert (
        shown.action_url == f"/patients/{raw['patient_id']}?tab=symptoms#symptom-{raw['source_id']}"
    )
    assert shown.action_label == "Review reported product"
    assert shown.can_acknowledge
    assert shown.source_label == "Confirmed patient symptom report"
    assert shown.state_checked_at is not None


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


def test_message_names_the_sender_and_clinic_once():
    raw = item(
        event_type="message_received",
        category="messages",
        actor_name="Elena Park",
        patient_name="Morgan Ellis",
        clinic_name="Synthetic Clinic",
    )
    patient = present_item(raw, "patient", "en-US")
    assert patient.title == "New message from Elena Park" and patient.body == "Synthetic Clinic"
    clinician = present_item(raw, "clinician", "en-US")
    assert clinician.title == "New message from Morgan Ellis"
    assert clinician.clinic_name == "Synthetic Clinic" and clinician.body == ""


def test_information_request_opens_the_follow_up_form_for_the_assessment():
    raw = item(
        event_type="adr_information_requested",
        category="safety",
        metadata={"clinician_id": str(uuid4())},
    )
    result = present_item(raw, "patient", "es-MX")
    assert result.action_url == f"/chat?view=follow-up&assessment={raw['source_id']}"
    assert result.action_label == "Responder preguntas"
    assert not result.can_acknowledge


def test_unknown_event_does_not_echo_raw_metadata():
    result = present_item(
        item(event_type="future_event", metadata={"title": "Private SQL", "body": "internal id"}),
        "patient",
        "en-US",
    )
    assert result.title == "Update available"
    assert "Private SQL" not in result.body


def test_information_questions_use_fixed_wording_and_never_echo_input():
    free_text = "When did the reported symptom begin?"
    raw = item(
        event_type="adr_information_requested",
        category="safety",
        metadata={"requested_information": ["dose_response", free_text, {"internal": "ignore"}]},
    )
    result = present_item(raw, "patient", "es-MX")
    assert "• Si el síntoma cambió después de un cambio de dosis" in result.body
    assert free_text not in result.body and "dose_response" not in result.body
    assert "internal" not in result.body


@pytest.mark.parametrize(
    ("role", "actionable", "expected"),
    [("clinician", True, True), ("clinician", False, False), ("patient", True, False)],
)
def test_appointment_response_acknowledgement_flows_only_while_actionable(
    role, actionable, expected
):
    raw = item(
        event_type="appointment_response",
        category="appointments",
        actionable=actionable,
        can_acknowledge=True,
    )
    assert present_item(raw, role, "en-US").can_acknowledge is expected


# --- ADR information request: fixed bilingual wording and follow-up link (R4.2, R5, R10.3) ---

# Independent copy of the approved R5 wording, so a drift in the module fails here.
QUESTION_WORDING = {
    "en-US": {
        "reappeared_on_rechallenge": "Whether the symptom came back after restarting this medicine",
        "dose_response": "Whether the symptom changed after a dose change your clinician directed",
        "similar_previous_reaction": "Whether you have had a similar reaction to this medicine before",
    },
    "es-MX": {
        "reappeared_on_rechallenge": "Si el síntoma volvió después de reiniciar este medicamento",
        "dose_response": (
            "Si el síntoma cambió después de un cambio de dosis indicado por tu profesional de salud"
        ),
        "similar_previous_reaction": "Si has tenido antes una reacción similar a este medicamento",
    },
}
QUESTION_KEYS = tuple(QUESTION_WORDING["en-US"])
REQUEST_TITLE = {
    "en-US": "Your care team requested information",
    "es-MX": "Tu equipo de atención solicita información",
}
REQUEST_BODY = {
    "en-US": (
        "Answer a few questions in the app about a symptom you already reported. "
        "Describe only what already happened."
    ),
    "es-MX": (
        "Responde en la app unas preguntas sobre un síntoma que ya reportaste. "
        "Describe solo lo que ya pasó."
    ),
}
QUESTION_HEADING = {
    "en-US": "Your care team asks about:",
    "es-MX": "Tu equipo de atención pregunta sobre:",
}
LOCALES = ("en-US", "es-MX")
UUID_PATTERN = re.compile(
    r"[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}", re.IGNORECASE
)
PATIENT_DESTINATIONS = {"/chat", "/today", "/visits", "/records", "/reminders"}


def request_item(**changes: Any) -> dict[str, Any]:
    return item(event_type="adr_information_requested", category="safety", **changes)


def expected_body(locale: str, keys: list[str]) -> str:
    if not keys:
        return REQUEST_BODY[locale]
    lines = [f"• {QUESTION_WORDING[locale][key]}" for key in keys]
    return REQUEST_BODY[locale] + "\n\n" + QUESTION_HEADING[locale] + "\n" + "\n".join(lines)


def question_lines(body: str) -> list[str]:
    return [line.removeprefix("• ") for line in body.splitlines() if line.startswith("• ")]


@pytest.mark.parametrize("locale", LOCALES)
def test_all_three_questions_use_the_fixed_wording_in_each_locale(locale):
    raw = request_item(metadata={"requested_information": list(QUESTION_KEYS)})
    result = present_item(raw, "patient", locale)
    assert result.title == REQUEST_TITLE[locale]
    assert result.body == expected_body(locale, list(QUESTION_KEYS))
    assert question_lines(result.body) == [QUESTION_WORDING[locale][k] for k in QUESTION_KEYS]
    assert result.action_label == (
        "Answer questions" if locale == "en-US" else "Responder preguntas"
    )
    if locale == "es-MX":
        # A Spanish-speaking patient never sees the English request copy (R10.3).
        english = present_item(raw, "patient", "en-US")
        for text in (english.title, REQUEST_BODY["en-US"], QUESTION_HEADING["en-US"]):
            assert text not in result.title and text not in result.body


@pytest.mark.parametrize("locale", LOCALES)
def test_request_body_points_to_the_app_and_keeps_titles(locale):
    result = present_item(request_item(metadata={}), "patient", locale)
    assert result.title == REQUEST_TITLE[locale]
    # With no allowed question there is the introductory sentence and no list (R5.3).
    assert result.body == REQUEST_BODY[locale]
    assert "Care team messages" not in result.body and "•" not in result.body


@pytest.mark.parametrize(("locale", "label"), [("en-US", "View"), ("es-MX", "Ver")])
def test_answered_request_in_history_keeps_its_link_and_is_labelled_view(locale, label):
    raw = request_item(actionable=False, is_read=True)
    result = present_item(raw, "patient", locale)
    assert result.action_url == f"/chat?view=follow-up&assessment={raw['source_id']}"
    assert result.action_label == label
    assert not result.actionable and not result.can_acknowledge


# Feature: adr-loop-gap-fixes, Property 1: Request wording is fixed, ordered and leak-free
FREE_TEXT = "When did the reported symptom begin?"
SPANISH_FREE_TEXT = "¿Cuándo empezó el síntoma después del medicamento?"
PADDED_KEY = " dose_response "
LONG_TEXT = "z" * 201
CORPUS_UUID = str(uuid4())
CORPUS_OBJECT = {"internal": "do-not-show", "question": "dose_response"}
REQUEST_CORPUS: tuple[Any, ...] = (
    *QUESTION_KEYS,
    PADDED_KEY,
    FREE_TEXT,
    SPANISH_FREE_TEXT,
    CORPUS_UUID,
    "",
    LONG_TEXT,
    42,
    None,
    CORPUS_OBJECT,
)
# Every input string that is not an allowed key must never reach the item text.
FORBIDDEN_TEXT = (
    FREE_TEXT,
    SPANISH_FREE_TEXT,
    LONG_TEXT,
    CORPUS_UUID,
    "do-not-show",
    "internal",
    "42",
    "None",
    *QUESTION_KEYS,
)
NON_LIST_VALUES: tuple[Any, ...] = (
    "dose_response",
    PADDED_KEY,
    {"dose_response": True},
    {"0": "similar_previous_reaction"},
    None,
    7,
    ("dose_response",),
)


def reference_keys(requested: Any) -> list[str]:
    if not isinstance(requested, list):
        return []
    keys: list[str] = []
    for value in requested:
        if isinstance(value, str) and value in QUESTION_KEYS and value not in keys:
            keys.append(value)
    return keys[:3]


def property_1_violations(metadata: Any, locale: str) -> list[str]:
    result = present_item(request_item(metadata=metadata), "patient", locale)
    requested = metadata.get("requested_information") if isinstance(metadata, dict) else None
    keys = reference_keys(requested)
    text = f"{result.title}\n{result.body}"
    problems = []
    if question_lines(result.body) != [QUESTION_WORDING[locale][key] for key in keys]:
        problems.append(f"question lines {question_lines(result.body)!r}, expected keys {keys!r}")
    if result.body != expected_body(locale, keys):
        problems.append(f"body {result.body!r}")
    if result.title != REQUEST_TITLE[locale]:
        problems.append(f"title {result.title!r}")
    if UUID_PATTERN.search(text):
        problems.append("a UUID reached the item text")
    problems.extend(f"leaked {value!r}" for value in FORBIDDEN_TEXT if value in text)
    return [f"{locale} {metadata!r}: {problem}" for problem in problems]


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("length", range(5))
def test_property_1_request_wording_is_fixed_ordered_and_leak_free(locale, length):
    """**Validates: Requirements 5.1, 5.2, 5.3, 10.3**"""
    failures: list[str] = []
    cases = 0
    for sequence in itertools.product(REQUEST_CORPUS, repeat=length):
        cases += 1
        failures.extend(property_1_violations({"requested_information": list(sequence)}, locale))
    assert cases == len(REQUEST_CORPUS) ** length
    assert not failures, f"{len(failures)} violations, first: " + "; ".join(failures[:5])


@pytest.mark.parametrize("locale", LOCALES)
def test_property_1_non_list_requested_information_lists_nothing(locale):
    """**Validates: Requirements 5.2, 5.3**"""
    metadata_values: list[Any] = [{"requested_information": value} for value in NON_LIST_VALUES]
    # Metadata itself may be absent or not an object.
    metadata_values += [{}, None, "dose_response", ["dose_response"]]
    failures = [
        problem
        for metadata in metadata_values
        for problem in property_1_violations(metadata, locale)
    ]
    assert not failures, "; ".join(failures)


# Feature: adr-loop-gap-fixes, Property 2: Notification links stay inside the allowlist
CANONICAL = str(uuid4())
EITHER = object()  # The value encodes a UUID in a non-canonical form; bare or canonical is fine.
SOURCE_ID_CASES: tuple[tuple[str, Any, Any], ...] = (
    ("lowercase-uuid", CANONICAL, CANONICAL),
    ("uppercase-uuid", CANONICAL.upper(), CANONICAL),
    ("braced-uuid", "{" + CANONICAL + "}", EITHER),
    ("urn-uuid", f"urn:uuid:{CANONICAL}", EITHER),
    ("undashed-uuid", CANONICAL.replace("-", ""), EITHER),
    ("padded-uuid", f" {CANONICAL} ", None),
    ("uuid-with-query", f"{CANONICAL}&request=//evil.invalid", None),
    ("uuid-with-path", f"{CANONICAL}/../../admin", None),
    ("garbage", "not-an-assessment", None),
    ("empty", "", None),
    ("none", None, None),
    ("int", 12345, None),
    ("32-digit-int", 12345678901234567890123456789012, EITHER),
    ("path-traversal", "../../etc/passwd", None),
    ("protocol-relative", "//evil.invalid", None),
    ("absolute-url", "https://evil.invalid/chat", None),
    ("url-encoded", "%2F%2Fevil.invalid%2Fchat", None),
    ("backslash", "\\\\evil.invalid", None),
    ("newline", f"{CANONICAL}\n/records", None),
)
LINK_METADATA: tuple[Any, ...] = (
    {},
    None,
    "metadata",
    {"action_url": "https://evil.invalid"},
    {"adr_assessment_id": "//evil.invalid", "information_request_id": str(uuid4())},
    {"request_id": str(uuid4()), "requested_information": list(QUESTION_KEYS)},
    {"clinician_id": str(uuid4()), "conversation_id": str(uuid4())},
)
FOLLOW_UP_LINK = re.compile(
    r"/chat\?view=follow-up(?:&assessment=[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})?"
)


def patient_destination_allows(link: str) -> bool:
    """Python port of `notificationDestination()` in the patient portal."""
    if not link.startswith("/") or link.startswith("//") or re.search(r"[\\\s]", link):
        return False
    parts = urlsplit(link)
    return not parts.scheme and not parts.netloc and parts.path in PATIENT_DESTINATIONS


@pytest.mark.parametrize(
    ("source_id", "expected"),
    [pytest.param(value, expected, id=name) for name, value, expected in SOURCE_ID_CASES],
)
def test_property_2_patient_request_link_stays_inside_the_allowlist(source_id, expected):
    """**Validates: Requirements 4.2**"""
    for metadata, locale, actionable in itertools.product(LINK_METADATA, LOCALES, (True, False)):
        raw = request_item(source_id=source_id, metadata=metadata, actionable=actionable)
        link = present_item(raw, "patient", locale).action_url
        context = f"source_id={source_id!r} metadata={metadata!r} {locale} actionable={actionable}"
        assert link is not None and FOLLOW_UP_LINK.fullmatch(link), f"{link!r} for {context}"
        assert patient_destination_allows(link), f"{link!r} rejected for {context}"
        assessment = link.partition("&assessment=")[2] or None
        if expected is EITHER:
            assert assessment in (None, str(UUID(str(source_id).strip("{}")))), context
        else:
            assert assessment == expected, f"{link!r} for {context}"


def test_critical_result_alert_opens_the_exact_document_without_health_detail():
    raw = item(event_type="critical_result", category="safety")
    shown = present_item(raw, "clinician", "en-US")
    assert shown.title == "Critical test result reported"
    link, label, _ = destination(raw, "clinician")
    assert link == f"/patients/{raw['patient_id']}?tab=documents#document-{raw['source_id']}"
    assert label == "Open document"
    # No test name, value or patient identifier in the copy itself.
    assert "Potassium" not in shown.body and raw["patient_id"] not in shown.body


def answered_item(**changes: Any) -> dict[str, Any]:
    return item(
        event_type="adr_information_answered",
        category="safety",
        source_type="adr_information_requests",
        actionable=False,
        **changes,
    )


def test_answered_alert_copy_is_english_free_of_clinical_content_and_links_the_assessment():
    assessment = str(uuid4())
    raw = answered_item(
        metadata={"adr_assessment_id": assessment, "information_request_id": str(uuid4())}
    )
    shown = present_item(raw, "clinician", "es-MX")
    assert shown.title == "Patient answered medication-safety follow-up"
    assert shown.body == (
        "A patient sent answers to follow-up questions. Review the updated evidence; "
        "this is not a clinical decision."
    )
    assert shown.category == "safety"
    assert shown.action_url == f"/medwatch?assessment={assessment}"
    # History-only: the link stays, the call to act does not.
    assert not shown.actionable and not shown.can_acknowledge and shown.action_label == "View"
    assert destination(raw, "clinician")[1] == "Review source"
    for clinical in ("Synthetic", "Naranjo", "Doubtful", "dose", raw["source_id"], assessment):
        assert clinical not in shown.title and clinical not in shown.body


def test_answered_alert_without_an_assessment_falls_back_to_its_source():
    raw = answered_item(metadata={"adr_assessment_id": "//evil.invalid"})
    assert present_item(raw, "clinician", "en-US").action_url == (
        f"/medwatch?assessment={raw['source_id']}"
    )


@pytest.mark.parametrize(
    ("locale", "label"), [("en-US", "Answer questions"), ("es-MX", "Responder preguntas")]
)
def test_request_sourced_item_opens_that_request(locale, label):
    raw = request_item(source_type="adr_information_requests")
    result = present_item(raw, "patient", locale)
    assert result.action_url == f"/chat?view=follow-up&request={raw['source_id']}"
    assert result.action_label == label


@pytest.mark.parametrize(("locale", "label"), [("en-US", "View"), ("es-MX", "Ver")])
def test_request_sourced_item_in_history_keeps_its_link(locale, label):
    raw = request_item(source_type="adr_information_requests", actionable=False)
    result = present_item(raw, "patient", locale)
    assert result.action_url == f"/chat?view=follow-up&request={raw['source_id']}"
    assert result.action_label == label and not result.actionable


# Feature: adr-loop-gap-fixes, Property 2 (full): Notification links stay inside the allowlist
SOURCE_TYPES: tuple[Any, ...] = (
    None,
    "adr_assessments",
    "adr_information_requests",
    "notifications",
    "ADR_INFORMATION_REQUESTS",
    "",
    7,
)
ANY_FOLLOW_UP_LINK = re.compile(
    r"/chat\?view=follow-up(?:&(?:assessment|request)=[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})?"
)
MEDWATCH_LINK = re.compile(
    r"/medwatch\?assessment=[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)


@pytest.mark.parametrize(
    ("source_id", "expected"),
    [pytest.param(value, expected, id=name) for name, value, expected in SOURCE_ID_CASES],
)
def test_property_2_full_patient_request_link_by_source_type(source_id, expected):
    """**Validates: Requirements 4.2**"""
    for source_type, metadata, locale in itertools.product(SOURCE_TYPES, LINK_METADATA, LOCALES):
        raw = request_item(source_id=source_id, source_type=source_type, metadata=metadata)
        link = present_item(raw, "patient", locale).action_url
        context = f"source_id={source_id!r} source_type={source_type!r} metadata={metadata!r}"
        assert link is not None and ANY_FOLLOW_UP_LINK.fullmatch(link), f"{link!r} for {context}"
        assert patient_destination_allows(link), f"{link!r} rejected for {context}"
        parameter = "request" if source_type == "adr_information_requests" else "assessment"
        value = link.partition(f"&{parameter}=")[2] or None
        assert "&" not in (value or "") and link.count("&") <= 1, context
        if expected is EITHER:
            assert value in (None, str(UUID(str(source_id).strip("{}")))), context
        else:
            assert value == expected, f"{link!r} for {context}"


@pytest.mark.parametrize("kind", ["adr_information_answered", "adr_review"])
@pytest.mark.parametrize(
    ("source_id", "expected"),
    [pytest.param(value, expected, id=name) for name, value, expected in SOURCE_ID_CASES],
)
def test_property_2_full_clinician_safety_links_are_none_or_a_canonical_assessment(
    kind, source_id, expected
):
    """**Validates: Requirements 11.2**"""
    assessments = (None, CANONICAL, CANONICAL.upper(), "//evil.invalid", "", 12345)
    for source_type, assessment, extra in itertools.product(
        SOURCE_TYPES, assessments, LINK_METADATA
    ):
        metadata = dict(extra) if isinstance(extra, dict) else {}
        if assessment is not None:
            metadata["adr_assessment_id"] = assessment
        raw = item(
            event_type=kind,
            category="safety",
            source_id=source_id,
            source_type=source_type,
            metadata=metadata,
        )
        link = present_item(raw, "clinician", "en-US").action_url
        context = f"{kind} source_id={source_id!r} metadata={metadata!r}"
        assert link is None or MEDWATCH_LINK.fullmatch(link), f"{link!r} for {context}"
        named = str(UUID(str(assessment))) if assessment in (CANONICAL, CANONICAL.upper()) else None
        if named:
            assert link == f"/medwatch?assessment={named}", context
        elif expected is None:
            assert link is None, context


@pytest.mark.parametrize(
    "review_kind",
    [
        "unowned_plan",
        "unassigned_legacy_plan",
        "cross_plan_conflict",
        "conflict_acknowledged",
        "conflict_published_without",
        "conflict_reply",
        "unowned_clinical_record",
    ],
)
def test_care_team_work_items_name_the_kind_link_to_the_patient_and_carry_no_record_content(
    review_kind,
):
    raw = item(
        event_type="care_plan_review",
        category="care_plans",
        source_type="care_plan_review_items",
        metadata={"review_kind": review_kind, "secret": "conflict wording"},
    )

    shown = present_item(raw, "clinician", "en-US")

    assert shown.title and shown.body and "conflict wording" not in shown.model_dump_json()
    assert (
        shown.action_url == f"/patients/{raw['patient_id']}?tab=care-plan&review={raw['source_id']}"
    )
    assert shown.source_label == "Care-team work item"
    assert present_item({**raw, "metadata": {"review_kind": "unknown"}}, "clinician", "en-US").title
