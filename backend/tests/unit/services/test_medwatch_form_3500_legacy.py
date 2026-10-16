"""Reading 048-shape MedWatch drafts as Form 3500 v2 (R16.5, R16.8, R17.3)."""

import copy
from typing import Any
from uuid import UUID

import pytest

from app.models.medwatch_form_3500 import MedWatchFormDataV2
from app.services.medwatch_3500.dates import coerce_date
from app.services.medwatch_3500.identifier import (
    DEFAULT_CODE_PATTERN,
    PatientIdentity,
    default_code,
    identifier_violations,
)
from app.services.medwatch_3500.legacy import (
    match_frequency,
    match_route,
    split_dose,
    upgrade_legacy_form,
)
from tests.unit.services.medwatch_3500_fixtures import CONTEXT, TODAY, full_payload

DRAFT_ID = UUID("3b2f7d1c-0a4e-4f5b-8c9d-112233445566")
PATIENT = PatientIdentity("Maya", "Patel", "maya.patel@example.test", "1988-04-03")
PATIENT_ES = PatientIdentity("José", "Núñez", "jose.nunez@example.test", "1979-11-20")


def _legacy(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "patient": {
            "patient_identifier": "Maya Patel",
            "date_of_birth": "1988-04-03",
            "sex": "female",
        },
        "event": {
            "description": "Dizziness (patient-reported severity 2/10)",
            "onset_date_or_time": "2026-10-01",
            "outcome": "Recovering",
            "seriousness": "Not serious",
        },
        "suspect_product": {
            "name": "Fluticasone/salmeterol",
            "dose": "1 puff",
            "frequency": "twice daily",
            "route": "inhaled",
            "therapy_start_date": "2026-09-28",
            "therapy_end_date": "",
        },
        "concomitant_products": {"products": "Albuterol, Lisinopril"},
        "tests_and_history": {"relevant_tests": "BP 90/60", "other_relevant_history": "Asthma"},
        "reporter": {
            "name": "Elena Park",
            "email": "elena@example.test",
            "specialty": "Internal medicine",
            "clinic_name": "Synthetic Clinic",
        },
        "clinical_review": {
            "naranjo_score": 6,
            "causality": "Probable",
            "reportability_rationale": "Clinically significant new event.",
        },
    }
    for path, value in overrides.items():
        section, key = path.split("__")
        payload.setdefault(section, {})[key] = value
    return payload


def _upgrade(data: Any, patient: PatientIdentity = PATIENT) -> dict[str, Any]:
    return upgrade_legacy_form(data, draft_id=DRAFT_ID, patient=patient, today=TODAY)


CORPUS: list[Any] = [
    None,
    {},
    {"patient": {}, "event": {}},
    _legacy(),
    _legacy(
        patient__patient_identifier="Case 17",
        patient__sex="M",
        suspect_product__dose="10 mg",
        suspect_product__frequency="bid",
        suspect_product__route="Oral",
        suspect_product__therapy_end_date="2026-10-05",
    ),
    _legacy(
        patient__patient_identifier="MP 1988-04-03",
        patient__date_of_birth="unknown",
        patient__sex="other",
        event__onset_date_or_time="a few hours after starting",
        suspect_product__therapy_start_date="sometime in spring",
        suspect_product__route="other",
        suspect_product__frequency="",
    ),
    _legacy(
        patient__patient_identifier="JOSE nunez",
        event__description="Mareo después de la dosis; señal leve. Ñandú.",
        reporter__name="José Luis Núñez",
        reporter__clinic_name="Clínica Sintética del Valle",
        suspect_product__name="Losartán",
    ),
    _legacy(
        concomitant_products__products="; ".join(f"Synthetic {n}" for n in range(12)),
        event__onset_date_or_time="2099-01-01",
        suspect_product__therapy_start_date="2026-09-28",
        suspect_product__therapy_end_date="2026-09-01",
        clinical_review__naranjo_score="six",
        clinical_review__causality="Certain",
    ),
    _legacy(extra__note="An unexpected 048 value", event__description="x" * 4100),
    {"patient": "not an object", "notes": "free text", "reporter": {"name": "Solo"}},
]


def _strings(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set().union(*(_strings(item) for item in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(_strings(item) for item in value)) if value else set()
    if value is None or isinstance(value, bool):
        return set()
    return {str(value)}


def _leaves(data: Any, prefix: str = "") -> list[tuple[str, str]]:
    if not isinstance(data, dict):
        return [] if data in (None, "") else [(prefix, str(data))]
    leaves: list[tuple[str, str]] = []
    for key, value in data.items():
        leaves.extend(_leaves(value, f"{prefix}.{key}" if prefix else str(key)))
    return leaves


def _represented(path: str, value: str, upgraded: dict[str, Any]) -> bool:
    stripped = value.strip()
    if not stripped:
        return True
    strings = _strings(upgraded)
    if stripped in strings or stripped in upgraded["legacy"].values():
        return True
    if path == "patient.sex":
        return {"female": "F", "f": "F", "male": "M", "m": "M"}[stripped.casefold()] in strings
    if coerce_date(stripped) in strings:
        return True
    dose = split_dose(stripped)
    if dose and set(dose) <= strings:
        return True
    for matcher in (match_frequency, match_route):
        option, other = matcher(stripped)
        if option and option in strings and (not other or other in strings):
            return True
    if path == "concomitant_products.products":
        return all(part.strip() in strings for part in stripped.replace(";", ",").split(","))
    if path == "reporter.name":
        return all(part in strings for part in stripped.split())
    if path == "event.description":
        return stripped[:4000] in strings
    return False


# Property 8: legacy upgrade is idempotent and lossless.
@pytest.mark.parametrize("patient", [PATIENT, PATIENT_ES], ids=["ascii", "accented"])
@pytest.mark.parametrize("data", CORPUS)
def test_property_8_upgrade_is_valid_idempotent_and_lossless(data, patient) -> None:
    stored = copy.deepcopy(data)
    upgraded = _upgrade(data, patient)
    assert data == stored, "the stored payload must not change"
    form = MedWatchFormDataV2.model_validate(upgraded, context=CONTEXT)
    assert form.model_dump(mode="json") == upgraded
    assert _upgrade(upgraded, patient) == upgraded
    assert _upgrade(_upgrade(upgraded, patient), patient) == upgraded
    identifier = upgraded["section_a"]["identifier"]
    assert identifier and identifier_violations(identifier, patient) == []
    for path, value in _leaves(data):
        if path == "patient.patient_identifier":
            continue
        assert _represented(path, value, upgraded), (path, value)


def test_v2_input_is_returned_unchanged() -> None:
    v2 = MedWatchFormDataV2.model_validate(full_payload(3), context=CONTEXT).model_dump(mode="json")
    result = _upgrade(v2)
    assert result == v2
    assert result is not v2


def test_name_bearing_identifier_is_replaced_by_the_default_code_and_dropped() -> None:
    upgraded = _upgrade(_legacy())
    code = default_code("Maya", "Patel", DRAFT_ID, PATIENT)
    assert upgraded["section_a"]["identifier"] == code
    assert "Maya Patel" not in _strings(upgraded)
    assert "patient.patient_identifier" not in upgraded["legacy"]


def test_a_non_identifying_identifier_is_kept() -> None:
    upgraded = _upgrade(_legacy(patient__patient_identifier="Case 17"))
    assert upgraded["section_a"]["identifier"] == "Case 17"


def test_048_values_map_to_their_form_3500_items() -> None:
    upgraded = _upgrade(_legacy(suspect_product__dose="10 mg", suspect_product__frequency="BID "))
    a, b = upgraded["section_a"], upgraded["section_b"]
    product = upgraded["section_d"]["product_1"]
    assert (a["date_of_birth"], a["sex"]) == ("1988-04-03", "F")
    assert (b["event_date"], b["event_date_confirmed"]) == ("2026-10-01", False)
    assert b["narrative"] == "Dizziness (patient-reported severity 2/10)"
    assert b["outcomes"] == [] and b["report_types"] == []
    assert (b["tests_comments"], b["other_history"]) == ("BP 90/60", "Asthma")
    assert (product["name"], product["dose"], product["dose_unit"]) == (
        "Fluticasone/salmeterol",
        "10",
        "MILLIGRAM(S) - MG",
    )
    assert (product["frequency"], product["frequency_other"]) == ("BID", "")
    assert (product["route"], product["route_other"]) == ("Respiratory (inhalation)", "")
    assert product["therapy_start"] == "2026-09-28"
    assert [row["name"] for row in upgraded["section_f"]["others"]] == ["Albuterol", "Lisinopril"]
    g = upgraded["section_g"]
    assert (g["first_name"], g["last_name"], g["email"]) == ("Elena", "Park", "elena@example.test")
    assert (g["health_professional"], g["occupation"], g["phone"]) == (None, None, "")
    assert upgraded["mediagent_review"] == {
        "naranjo_score": 6,
        "causality": "Probable",
        "reportability_rationale": "Clinically significant new event.",
    }
    assert upgraded["legacy"] == {
        "event.outcome": "Recovering",
        "event.seriousness": "Not serious",
        "reporter.clinic_name": "Synthetic Clinic",
        "reporter.specialty": "Internal medicine",
    }


def test_unparseable_values_go_to_legacy() -> None:
    upgraded = _upgrade(
        _legacy(
            event__onset_date_or_time="a few hours after starting",
            patient__sex="prefer_not_to_say",
            reporter__name="Dr. Elena Park",
        )
    )
    legacy = upgraded["legacy"]
    assert legacy["event.onset_date_or_time"] == "a few hours after starting"
    assert legacy["patient.sex"] == "prefer_not_to_say"
    assert legacy["suspect_product.dose"] == "1 puff"
    assert legacy["reporter.name"] == "Dr. Elena Park"
    product = upgraded["section_d"]["product_1"]
    assert (product["frequency"], product["frequency_other"]) == ("Other", "twice daily")
    assert upgraded["section_b"]["event_date"] is None
    assert upgraded["section_a"]["sex"] is None
    assert upgraded["section_g"]["first_name"] == ""


def test_more_than_ten_other_products_stay_as_one_legacy_string() -> None:
    products = ", ".join(f"Synthetic {n}" for n in range(11))
    upgraded = _upgrade(_legacy(concomitant_products__products=products))
    assert upgraded["section_f"]["others"] == []
    assert upgraded["legacy"]["concomitant_products.products"] == products
    ten = "\n".join(f"Synthetic {n}" for n in range(10))
    assert len(_upgrade(_legacy(concomitant_products__products=ten))["section_f"]["others"]) == 10


def test_future_and_reversed_dates_are_kept_in_legacy() -> None:
    upgraded = _upgrade(
        _legacy(
            event__onset_date_or_time="2026-10-14",
            suspect_product__therapy_start_date="2026-09-28",
            suspect_product__therapy_end_date="2026-09-01",
        )
    )
    assert upgraded["section_b"]["event_date"] is None
    assert upgraded["legacy"]["event.onset_date_or_time"] == "2026-10-14"
    assert upgraded["section_d"]["product_1"]["therapy_stop"] is None
    assert upgraded["legacy"]["suspect_product.therapy_end_date"] == "2026-09-01"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10 mg", ("10", "MILLIGRAM(S) - MG")),
        ("2.5mg", ("2.5", "MILLIGRAM(S) - MG")),
        ("5 ML", ("5", "MILLILITRE(S) - ML")),
        ("0.5 mg/kg", ("0.5", "MILLIGRAM(S)/KILOGRAM(S) - MG/KG")),
        ("2 gtt", ("2", "DROP(S) - GTT")),
        ("1 puff", None),
        ("10 mg twice daily", None),
        ("ten mg", None),
        ("", None),
    ],
)
def test_split_dose_only_on_number_and_unit_abbreviation(text, expected) -> None:
    assert split_dose(text) == expected


@pytest.mark.parametrize(
    ("text", "frequency", "route"),
    [
        ("daily", ("Daily", ""), ("Other", "daily")),
        ("PRN", ("PRN", ""), ("Other", "PRN")),
        ("oral", ("Other", "oral"), ("Oral", "")),
        ("iv", ("Other", "iv"), ("Intravenous (not otherwise specified)", "")),
        ("im", ("Other", "im"), ("Intramuscular", "")),
        ("Other", (None, ""), (None, "")),
        ("", (None, ""), (None, "")),
    ],
)
def test_option_matchers(text, frequency, route) -> None:
    assert match_frequency(text) == frequency
    assert match_route(text) == route


def test_accented_name_identifier_is_replaced_for_an_accented_patient() -> None:
    upgraded = _upgrade(_legacy(patient__patient_identifier="JOSE nunez"), PATIENT_ES)
    assert DEFAULT_CODE_PATTERN.fullmatch(upgraded["section_a"]["identifier"])
    assert upgraded["section_a"]["identifier"].startswith("JN-")
