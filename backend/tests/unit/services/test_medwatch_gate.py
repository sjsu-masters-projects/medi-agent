"""The Form 3500 approval gate (R17.3, R19.1 to R19.5)."""

from itertools import product
from typing import get_args

import pytest

from app.models.medwatch_form_3500 import GateIssueCode, MedWatchFormDataV2, Outcome
from app.services.medwatch_3500.gate import GateContext, approval_issues
from app.services.medwatch_3500.identifier import PatientIdentity
from tests.unit.services.medwatch_3500_fixtures import CONTEXT, empty_form, full_form

PATIENT = PatientIdentity("Maya", "Patel", "maya.patel@example.test", "1988-04-03")
OUTCOMES: tuple[str, ...] = get_args(Outcome)


def _complete() -> MedWatchFormDataV2:
    form = full_form(1)
    form.section_b.report_types = ["adverse_event"]
    form.section_b.outcomes = ["hospitalization"]
    form.section_b.death_date = None
    return form


def _codes(form: MedWatchFormDataV2, attested: bool = False) -> list[str]:
    return [issue.code for issue in approval_issues(form, GateContext(PATIENT, attested))]


def test_complete_form_has_no_issues() -> None:
    assert approval_issues(_complete(), GateContext(PATIENT)) == []


def test_empty_form_lists_every_required_item_in_form_order() -> None:
    issues = approval_issues(empty_form(), GateContext(PATIENT))
    assert [(issue.path, issue.code) for issue in issues] == [
        ("section_a.identifier", "identifier_missing"),
        ("section_b.report_types", "report_type_missing"),
        ("section_b.outcomes", "non_serious_attestation_required"),
        ("section_b.event_date", "event_date_missing"),
        ("section_b.narrative", "narrative_missing"),
        ("section_d.product_1.name", "product_name_missing"),
        ("section_g.first_name", "reporter_first_name_missing"),
        ("section_g.last_name", "reporter_last_name_missing"),
        ("section_g.email", "reporter_contact_missing"),
        ("section_g.health_professional", "health_professional_missing"),
        ("section_g.occupation", "occupation_missing"),
        ("mediagent_review.reportability_rationale", "reportability_rationale_missing"),
    ]


def test_every_gate_code_is_reachable() -> None:
    seen: set[str] = set(_codes(empty_form()))
    identifies = _complete()
    identifies.section_a.identifier = "Maya P"
    seen |= set(_codes(identifies))
    death = _complete()
    death.section_b.outcomes = ["death"]
    seen |= set(_codes(death))
    unconfirmed = _complete()
    unconfirmed.section_b.event_date_confirmed = False
    seen |= set(_codes(unconfirmed))
    assert seen == set(get_args(GateIssueCode))


@pytest.mark.parametrize(
    "value", ["Maya Patel", "PATEL-01", "maya.patel@example.test", "MP 04/03/1988", "máya"]
)
def test_identifier_that_identifies_the_patient_blocks_approval(value) -> None:
    form = _complete()
    form.section_a.identifier = value
    assert _codes(form) == ["identifier_identifies"]


def test_whitespace_counts_as_missing() -> None:
    form = _complete()
    form.section_b.narrative = "   "
    form.section_g.phone = " "
    form.section_g.email = ""
    assert _codes(form) == ["narrative_missing", "reporter_contact_missing"]


@pytest.mark.parametrize(("phone", "email"), [("555-0100", ""), ("", "a@example.test")])
def test_phone_or_email_is_enough(phone, email) -> None:
    form = _complete()
    form.section_g.phone, form.section_g.email = phone, email
    assert _codes(form) == []


# Property 12: the approval gate is total and shared.
REQUIRED = {
    "identifier": ("section_a.identifier", "identifier_missing"),
    "report_types": ("section_b.report_types", "report_type_missing"),
    "event_date": ("section_b.event_date", "event_date_missing"),
    "narrative": ("section_b.narrative", "narrative_missing"),
    "product_name": ("section_d.product_1.name", "product_name_missing"),
    "first_name": ("section_g.first_name", "reporter_first_name_missing"),
    "last_name": ("section_g.last_name", "reporter_last_name_missing"),
    "contact": ("section_g.email", "reporter_contact_missing"),
    "health_professional": ("section_g.health_professional", "health_professional_missing"),
    "occupation": ("section_g.occupation", "occupation_missing"),
    "rationale": ("mediagent_review.reportability_rationale", "reportability_rationale_missing"),
}
IDENTIFIER_STATES = ("present", "absent", "identifying")
EVENT_DATE_STATES = ("confirmed", "unconfirmed", "absent")
CONTACT_STATES = ("phone", "email", "both", "none")


def _apply(form: MedWatchFormDataV2, states: dict[str, object]) -> MedWatchFormDataV2:
    a, b, g = form.section_a, form.section_b, form.section_g
    a.identifier = {"present": "MP-ABCD", "absent": "", "identifying": "Patel"}[
        states["identifier"]
    ]
    b.report_types = ["adverse_event"] if states["report_types"] else []
    b.event_date = None if states["event_date"] == "absent" else "2026-10-01"
    b.event_date_confirmed = states["event_date"] == "confirmed"
    b.narrative = "Dizziness" if states["narrative"] else ""
    form.section_d.product_1.name = "Lisinopril" if states["product_name"] else ""
    g.first_name = "Elena" if states["first_name"] else ""
    g.last_name = "Park" if states["last_name"] else ""
    g.phone = "555-0100" if states["contact"] in {"phone", "both"} else ""
    g.email = "e@example.test" if states["contact"] in {"email", "both"} else ""
    g.health_professional = "yes" if states["health_professional"] else None
    g.occupation = "Physician" if states["occupation"] else None
    form.mediagent_review.reportability_rationale = "Serious" if states["rationale"] else ""
    b.outcomes = list(states["outcomes"])
    b.death_date = "2026-10-02" if states["death_date"] else None
    return form


def _reference(states: dict[str, object], attested: bool) -> set[tuple[str, str]]:
    """An independent statement of R19.1 to R19.3, D12 and R17.3."""
    expected: set[tuple[str, str]] = set()
    if states["identifier"] == "absent":
        expected.add(REQUIRED["identifier"])
    if states["identifier"] == "identifying":
        expected.add(("section_a.identifier", "identifier_identifies"))
    for key in ("report_types", "narrative", "product_name", "first_name", "last_name"):
        if not states[key]:
            expected.add(REQUIRED[key])
    for key in ("health_professional", "occupation", "rationale"):
        if not states[key]:
            expected.add(REQUIRED[key])
    if states["event_date"] == "absent":
        expected.add(REQUIRED["event_date"])
    if states["event_date"] == "unconfirmed":
        expected.add(("section_b.event_date", "event_date_unconfirmed"))
    if states["contact"] == "none":
        expected.add(REQUIRED["contact"])
    outcomes = states["outcomes"]
    if not outcomes and not attested:
        expected.add(("section_b.outcomes", "non_serious_attestation_required"))
    if "death" in outcomes and not states["death_date"]:
        expected.add(("section_b.death_date", "death_date_missing"))
    return expected


def _issue_set(form: MedWatchFormDataV2, attested: bool) -> set[tuple[str, str]]:
    issues = approval_issues(form, GateContext(PATIENT, attested))
    assert len(issues) == len({(i.path, i.code) for i in issues}), "no duplicate issues"
    return {(issue.path, issue.code) for issue in issues}


def test_property_12_every_presence_combination_matches_the_reference_model() -> None:
    base = _complete()
    booleans = (
        "report_types",
        "narrative",
        "product_name",
        "first_name",
        "last_name",
        "health_professional",
        "occupation",
        "rationale",
    )
    count = 0
    for identifier, event_date, contact, *flags in product(
        IDENTIFIER_STATES, EVENT_DATE_STATES, CONTACT_STATES, *([(True, False)] * len(booleans))
    ):
        states: dict[str, object] = dict(zip(booleans, flags, strict=True))
        states.update(
            identifier=identifier,
            event_date=event_date,
            contact=contact,
            outcomes=("hospitalization",),
            death_date=False,
        )
        form = _apply(base.model_copy(deep=True), states)
        assert _issue_set(form, False) == _reference(states, False), states
        count += 1
    assert count == 3 * 3 * 4 * 2 ** len(booleans)


def test_property_12_every_outcome_death_date_and_attestation_combination() -> None:
    outcome_sets = [(), *((outcome,) for outcome in OUTCOMES), OUTCOMES, ("death", "disability")]
    for outcomes, death_date, attested, complete in product(
        outcome_sets, (True, False), (True, False), (True, False)
    ):
        if death_date and "death" not in outcomes:
            continue  # the model rejects a date of death without the Death outcome
        states: dict[str, object] = {key: complete for key in REQUIRED}
        states.update(
            identifier="present" if complete else "absent",
            event_date="confirmed" if complete else "absent",
            contact="email" if complete else "none",
            outcomes=outcomes,
            death_date=death_date,
        )
        form = _apply(_complete(), states)
        MedWatchFormDataV2.model_validate(form.model_dump(mode="json"), context=CONTEXT)
        assert _issue_set(form, attested) == _reference(states, attested), (states, attested)
        if complete and _reference(states, attested) == set():
            assert approval_issues(form, GateContext(PATIENT, attested)) == []


def test_attestation_clears_only_the_non_serious_issue() -> None:
    form = _complete()
    form.section_b.outcomes = []
    assert _codes(form) == ["non_serious_attestation_required"]
    assert _codes(form, attested=True) == []
    form.section_b.outcomes = ["other_serious"]
    assert _codes(form, attested=True) == []
    form.section_b.outcomes = ["death"]
    assert _codes(form, attested=True) == ["death_date_missing"]
