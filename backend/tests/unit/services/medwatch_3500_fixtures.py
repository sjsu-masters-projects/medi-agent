"""Synthetic Form 3500 v2 drafts for the MedWatch tests. No real patient data."""

from datetime import date
from typing import Any, get_args

from app.models.medwatch_form_3500 import (
    FORM_3500_VERSION,
    AgeUnit,
    AlsoReportedTo,
    DoseUnit,
    DurationUnit,
    Frequency,
    MedWatchFormDataV2,
    Occupation,
    Outcome,
    ProductType,
    Race,
    ReportType,
    Route,
    YesNoNotApplicable,
)
from app.services.medwatch_3500.template import load_template_record

TODAY = date(2026, 10, 13)
CONTEXT = {"today": TODAY}

ROUTES: tuple[str, ...] = get_args(Route)
FREQUENCIES: tuple[str, ...] = get_args(Frequency)
DOSE_UNITS: tuple[str, ...] = get_args(DoseUnit)
DURATION_UNITS: tuple[str, ...] = get_args(DurationUnit)
OCCUPATIONS: tuple[str, ...] = get_args(Occupation)
AGE_UNITS: tuple[str, ...] = get_args(AgeUnit)
YES_NO_NA: tuple[str, ...] = get_args(YesNoNotApplicable)
PRODUCT_TYPES: tuple[str, ...] = get_args(ProductType)


def countries() -> list[str]:
    pairs = load_template_record()["choice_options"][
        "topmostSubform[0].Page7[0].SecG_Reporter[0].Country[0]"
    ]
    return [display for _export, display in pairs if display.strip()]


def _rotate(values: tuple[str, ...], i: int) -> list[str]:
    """Every option, none, or one option, so each checkbox is both on and off in a corpus."""
    if i % 3 == 0:
        return list(values)
    if i % 3 == 1:
        return []
    return [values[i % len(values)]]


def _product(i: int, number: int) -> dict[str, Any]:
    # Product 2 is offset so that, over 35 drafts, both products together use every route
    # and every strength and dose unit, and each product uses route Other once.
    slot = 2 * i + number - 1
    offset = 0 if number == 1 else 1
    frequency = FREQUENCIES[(i + 3 * offset) % len(FREQUENCIES)]
    route = ROUTES[(i + 32 * offset) % len(ROUTES)]
    if number == 1 and i == 34:
        route = "Other"
    cosmetic = "cosmetic_retail" if (i // 3 + offset) % 2 else "cosmetic_professional"
    types = _rotate(tuple(t for t in PRODUCT_TYPES if not t.startswith("cosmetic")), i)
    if i % 3 == 0:
        types.append(cosmetic)
    return {
        "name": f"Synthetic product {number}-{i} & <co>",
        "strength": str(5 + i),
        "strength_unit": DOSE_UNITS[(i + 10 * offset) % len(DOSE_UNITS)],
        "manufacturer_compounder": f"Synthetic Labs {i}",
        "ndc_or_unique_id": f"00000-{i:04d}-{number}",
        "lot": f"LOT{i}{number}",
        "dose": str(1 + i),
        "dose_unit": DOSE_UNITS[(i + 20 + 10 * offset) % len(DOSE_UNITS)],
        "frequency": frequency,
        "frequency_other": "Every other day" if frequency == "Other" else "",
        "route": route,
        "route_other": "Via a synthetic device" if route == "Other" else "",
        "therapy_start": "2026-01-05",
        "therapy_stop": "2026-09-30" if i % 3 else "2026-09",
        "therapy_reduced": "2026-06-15",
        "duration": str(30 + i),
        "duration_unit": DURATION_UNITS[(i + 3 * offset) % len(DURATION_UNITS)],
        "ongoing": "yes" if (i + offset) % 2 else "no",
        "diagnosis_for_use": "Synthetic indication: hypertension",
        "product_types": types,
        "expiration_date": "2027-12-31",
        "abated": YES_NO_NA[slot % 3],
        "reappeared": YES_NO_NA[(slot + 1) % 3],
    }


def full_payload(i: int = 0) -> dict[str, Any]:
    """A valid draft that sets every modelled item; options rotate with ``i``."""
    country_list = countries()
    return {
        "form_version": FORM_3500_VERSION,
        "section_a": {
            "identifier": "JN-ABCD",
            "age_value": str(40 + i),
            "age_unit": AGE_UNITS[i % len(AGE_UNITS)],
            "date_of_birth": "1981-03-0" + str(1 + i % 9),
            "sex": "F" if i % 2 else "M",
            "weight_value": str(60 + i),
            "weight_unit": "kg" if i % 2 else "lb",
            "race": _rotate(get_args(Race), i),
            "hispanic_latino": i % 2 == 0,
        },
        "section_b": {
            "report_types": _rotate(get_args(ReportType), i),
            "outcomes": _rotate(get_args(Outcome), i),
            "death_date": "2026-10-02" if i % 3 == 0 else None,
            "event_date": "2026-10-01" if i % 4 else "2026-09",
            "event_date_confirmed": True,
            "report_date": "2026-10-12",
            "narrative": f'Synthetic dizziness after dose increase ({i}); señal <& "quoted">.',
            "tests": [
                {
                    "test": f"Synthetic test {n} result {n}.{i}",
                    "low_range": str(n),
                    "high_range": str(n + 10),
                    "date": f"2026-09-{10 + n:02d}",
                }
                for n in range(1, 9)
            ],
            "tests_comments": "Synthetic comment on tests.",
            "other_history": "Synthetic history: asthma; penicillin (hives).",
        },
        "section_d": {"product_1": _product(i, 1), "product_2": _product(i, 2)},
        "section_f": {
            "others": [
                {"name": f"Synthetic other {n}", "start": "2025-01-01", "end": "2026-08-31"}
                for n in range(1, 11)
            ]
        },
        "section_g": {
            "first_name": "Elena",
            "last_name": "Park-Ríos",
            "address": "100 Synthetic Way",
            "city": "Sacramento",
            "state": "CA",
            "zip_code": "95814",
            "country": country_list[(i * 8) % len(country_list)],
            "phone": "555-0100",
            "email": "elena.synthetic@example.test",
            "health_professional": "yes" if i % 2 == 0 else "no",
            "occupation": OCCUPATIONS[i % len(OCCUPATIONS)],
            "also_reported_to": _rotate(get_args(AlsoReportedTo), i),
            "identity_withheld": i % 2 == 1,
        },
        "mediagent_review": {
            "naranjo_score": 6,
            "causality": "Probable",
            "reportability_rationale": "Synthetic serious event.",
        },
        "legacy": {"event.outcome": "Recovering (synthetic)"},
    }


def full_form(i: int = 0) -> MedWatchFormDataV2:
    return MedWatchFormDataV2.model_validate(full_payload(i), context=CONTEXT)


def empty_form() -> MedWatchFormDataV2:
    return MedWatchFormDataV2.model_validate({"form_version": FORM_3500_VERSION}, context=CONTEXT)
