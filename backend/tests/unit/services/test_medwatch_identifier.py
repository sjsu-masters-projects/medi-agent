"""Non-identifying A1 identifier and name warnings (R17.1 to R17.4)."""

import base64
import hashlib
from uuid import UUID, uuid5

import pytest

from app.models.medwatch_form_3500 import MedWatchFormDataV2, MedWatchNameWarning
from app.services.medwatch_3500.identifier import (
    DEFAULT_CODE_PATTERN,
    NameSources,
    PatientIdentity,
    default_code,
    identifier_violations,
    name_warnings,
)
from tests.unit.services.medwatch_3500_fixtures import CONTEXT, empty_form, full_payload

NAMESPACE = UUID("8f0b2c1e-5d7a-4c3b-9e6f-1a2b3c4d5e6f")
DRAFT_IDS = [uuid5(NAMESPACE, f"draft-{n}") for n in range(40)]


def _window(draft_id: UUID, start: int = 0) -> str:
    encoded = base64.b32encode(hashlib.sha256(draft_id.bytes).digest()).decode().rstrip("=")
    return encoded[start : start + 4]


# Synthetic names: ASCII, accented, hyphenated, multi-part, single-letter, a name equal to
# the draft's first base32 window, and initials that are themselves a name.
NAME_PAIRS = [
    ("Maya", "Patel"),
    ("José", "Núñez"),
    ("Ana-Lucía", "García-Ríos"),
    ("María José", "de la Cruz"),
    ("Ñoño", "Íñiguez"),
    ("A", "B"),
    ("J", "Lee"),
    ("Al", "Lopez"),
    ("Mp", "Park"),
    ("", ""),
    ("Øyvind", "Ølstad"),
    ("O'Brien", "D'Angelo"),
]
EMAILS = ["maya.patel@example.test", "mp@example.test", "abcd@example.test", ""]
BIRTH_DATES = ["1988-04-03", "2001-12-31", None]


def _identities() -> list[tuple[PatientIdentity, UUID]]:
    cases = []
    for index, (first, last) in enumerate(NAME_PAIRS):
        for email in EMAILS:
            for dob in BIRTH_DATES:
                draft_id = DRAFT_IDS[(index * 7 + len(email)) % len(DRAFT_IDS)]
                cases.append((PatientIdentity(first, last, email, dob), draft_id))
    # A last name equal to the draft's first base32 window must push the code onward.
    window_id = DRAFT_IDS[0]
    cases.append((PatientIdentity("Rosa", _window(window_id).title(), "", None), window_id))
    cases.append((PatientIdentity(_window(window_id, 1), "Diaz", "", None), window_id))
    return cases


# Property 11: the identifier never contains a name, email or date of birth.
@pytest.mark.parametrize(("identity", "draft_id"), _identities())
def test_property_11_default_code_is_well_formed_stable_and_clean(identity, draft_id) -> None:
    code = default_code(identity.first_name, identity.last_name, draft_id, identity)
    assert DEFAULT_CODE_PATTERN.fullmatch(code)
    assert identifier_violations(code, identity) == []
    assert default_code(identity.first_name, identity.last_name, draft_id, identity) == code


def test_default_code_uses_accent_stripped_initials_and_the_draft_hash() -> None:
    draft_id = DRAFT_IDS[3]
    code = default_code("José", "Núñez", draft_id)
    assert code.startswith("JN-")
    assert code[3:] == _window(draft_id)
    assert default_code("", "", draft_id).startswith("XX-")
    assert default_code("Øyvind", "Lee", draft_id).startswith("XL-")


def test_default_code_skips_a_window_equal_to_a_name() -> None:
    draft_id = DRAFT_IDS[0]
    last = _window(draft_id).title()
    code = default_code("Rosa", last, draft_id)
    assert code[3:] != _window(draft_id)
    assert identifier_violations(code, PatientIdentity("Rosa", last)) == []


def test_default_code_avoids_initials_that_are_a_name() -> None:
    code = default_code("Al", "Lopez", DRAFT_IDS[1])
    assert not code.startswith("AL-")
    assert DEFAULT_CODE_PATTERN.fullmatch(code)


def test_default_code_is_the_first_clean_hash_window() -> None:
    for draft_id in DRAFT_IDS:
        code = default_code("Maya", "Patel", draft_id)
        assert code[3:] == next(
            _window(draft_id, start)
            for start in range(49)
            if not identifier_violations(
                f"MP-{_window(draft_id, start)}", PatientIdentity("Maya", "Patel")
            )
        )


PATIENT = PatientIdentity("José", "Núñez-Ortega", "jose.nunez@example.test", "1988-04-03")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("José Núñez-Ortega", {"full_name", "name_token", "email"}),
        ("JOSE NUNEZORTEGA", {"full_name", "name_token", "email"}),
        ("nunez-ortega jose", {"full_name", "name_token"}),
        ("Pt jose 12", {"name_token"}),
        ("NUNEZ", {"name_token"}),
        ("ortega-7", {"name_token"}),
        ("jose.nunez@example.test", {"email", "name_token"}),
        ("ID JOSE.NUNEZ", {"email", "name_token"}),
        ("1988-04-03", {"date_of_birth"}),
        ("04/03/1988", {"date_of_birth"}),
        ("4/3/1988", {"date_of_birth"}),
        ("03-Apr-1988", {"date_of_birth"}),
        ("03-APR-1988", {"date_of_birth"}),
        ("19880403", {"date_of_birth"}),
        ("pt 04031988", {"date_of_birth"}),
        ("X-03041988", {"date_of_birth"}),
        ("JN-ABCD", set()),
        ("Josefina", set()),
        ("Case 2026-0042", set()),
    ],
)
def test_identifier_violations_ignore_case_and_accents(value, expected) -> None:
    assert set(identifier_violations(value, PATIENT)) == expected


def test_identifier_check_with_single_letter_names() -> None:
    identity = PatientIdentity("A", "B")
    assert "full_name" in identifier_violations("AB-QRST", identity)
    assert "name_token" in identifier_violations("b 22", identity)
    assert identifier_violations("XX-QRST", identity) == []


def test_name_warnings_report_each_path_and_kind() -> None:
    payload = full_payload(0)
    payload["section_b"]["narrative"] = (
        "José felt dizzy; seen by Dr. Elena Park at Sunrise Family Clinic."
    )
    payload["section_b"]["tests"][2]["test"] = "INR checked by Lee"
    payload["section_b"]["tests"][4]["high_range"] = "Nuñez lab"
    payload["section_b"]["tests_comments"] = "Repeat at sunrise family clinic"
    payload["section_b"]["other_history"] = "Mother of Jose has asthma"
    payload["section_f"]["others"][1]["name"] = "Aspirin from Dr Park"
    form = MedWatchFormDataV2.model_validate(payload, context=CONTEXT)
    names = NameSources(
        patient_names=[("José", "Núñez")],
        clinician_names=[("Elena", "Park"), ("Sam", "Lee")],
        clinic_names=["Sunrise Family Clinic"],
    )
    warnings = name_warnings(form, names)
    assert warnings == [
        MedWatchNameWarning(path="section_b.narrative", kind="patient_name"),
        MedWatchNameWarning(path="section_b.narrative", kind="clinician_name"),
        MedWatchNameWarning(path="section_b.narrative", kind="clinic_name"),
        MedWatchNameWarning(path="section_b.tests[2].test", kind="clinician_name"),
        MedWatchNameWarning(path="section_b.tests[4].high_range", kind="patient_name"),
        MedWatchNameWarning(path="section_b.tests_comments", kind="clinic_name"),
        MedWatchNameWarning(path="section_b.other_history", kind="patient_name"),
        MedWatchNameWarning(path="section_f.others[1].name", kind="clinician_name"),
    ]


def test_name_warnings_ignore_identity_fields_and_partial_words() -> None:
    payload = full_payload(0)
    payload["section_b"]["narrative"] = "Josefina reported parking-lot dizziness at the clinic."
    form = MedWatchFormDataV2.model_validate(payload, context=CONTEXT)
    names = NameSources(
        patient_names=[("José", "Núñez")],
        clinician_names=[("Elena", "Park-Ríos")],
        clinic_names=["Sunrise Family Clinic"],
    )
    # Section G holds the reporter's own name; it is not free text and is not checked.
    assert name_warnings(form, names) == []
    assert name_warnings(empty_form(), names) == []
