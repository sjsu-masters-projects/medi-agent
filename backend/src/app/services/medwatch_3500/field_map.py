"""Explicit map from Form 3500 v2 data to the official template's fields.

Every mapped field is one entry: the fully qualified AcroForm name, the XFA ``datasets``
path under ``xfa:data/topmostSubform``, the model path and the kind. XFA paths are written
out because they do not follow the AcroForm names: ``Prod1Name``, ``Prod1Dose``,
``Prod1FreqOther``, ``Prod1RouteOther`` and ``Prod1Diagnosis`` (and the ``Prod2`` ones) sit
at the data root, B5 is under ``Page2``, and B6 and F rows nest irregularly.

Template quirks followed here: the ``WeightKG`` / ``WeightLB`` tooltips are swapped, so the
map follows the printed "kg" and "lb" labels; product 2's cosmetic box is ``pdt2CosmProf``.
Section C, Section E, the place-of-purchase items, the FDA-use-only header, the character
counters and the "Advice" page are never mapped. ``mediagent_review`` is never mapped.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

from app.models.medwatch_form_3500 import (
    AGE_UNIT_LABELS,
    ALSO_REPORTED_TO_LABELS,
    OUTCOME_LABELS,
    PRODUCT_TYPE_LABELS,
    RACE_LABELS,
    REPORT_TYPE_LABELS,
    SEX_LABELS,
    YES_NO_LABELS,
    MedWatchFormDataV2,
)
from app.services.medwatch_3500.dates import fda_date
from app.services.medwatch_3500.template import load_template_record

FieldKind = Literal["text", "date", "checkbox", "choice"]

ACROFORM_ROOT = "topmostSubform[0]"
CHECKBOX_ON = "/1"
CHECKBOX_OFF = "/Off"
XFA_CHECKBOX_ON = "1"
XFA_CHECKBOX_OFF = "0"

# ``(export value, display text)`` pairs that cannot round-trip: the strength and dose
# unit lists pair the export "INTERNATIONAL UNITS PER MILLILITRE - IU/ML" with the display
# text "AS NECESSARY - AN".
INCONSISTENT_CHOICE_PAIRS = frozenset(
    {("INTERNATIONAL UNITS PER MILLILITRE - IU/ML", "AS NECESSARY - AN")}
)


@dataclass(frozen=True)
class FieldEntry:
    """One official form field and the draft value it shows."""

    acroform: str
    xfa: str
    model_path: str
    kind: FieldKind
    item: str
    label: str
    checked_when: str | bool | None = None


def acroform_name(short: str) -> str:
    """``Page1.SecA_Patient.SexF`` -> the fully qualified ``...[0]`` AcroForm name."""
    return ".".join([ACROFORM_ROOT, *(f"{part}[0]" for part in short.split("."))])


def _e(
    short: str,
    xfa: str,
    model_path: str,
    kind: FieldKind,
    item: str,
    label: str,
    checked_when: str | bool | None = None,
) -> FieldEntry:
    return FieldEntry(acroform_name(short), xfa, model_path, kind, item, label, checked_when)


def _section_a() -> list[FieldEntry]:
    p, x = "Page1.SecA_Patient.", "SecA_Patient/"
    entries = [
        _e(
            p + "PatientIdentifier",
            x + "PatientIdentifier",
            "section_a.identifier",
            "text",
            "A1",
            "Patient identifier",
        ),
        _e(p + "AgeValue", x + "AgeValue", "section_a.age_value", "text", "A2", "Age"),
        _e(
            p + "AgeYears",
            x + "AgeYears",
            "section_a.age_unit",
            "checkbox",
            "A2",
            "Age unit: " + AGE_UNIT_LABELS["years"],
            "years",
        ),
        _e(
            p + "AgeMonths",
            x + "AgeMonths",
            "section_a.age_unit",
            "checkbox",
            "A2",
            "Age unit: " + AGE_UNIT_LABELS["months"],
            "months",
        ),
        _e(
            p + "AgeWeeks",
            x + "AgeWeeks",
            "section_a.age_unit",
            "checkbox",
            "A2",
            "Age unit: " + AGE_UNIT_LABELS["weeks"],
            "weeks",
        ),
        _e(
            p + "AgeDays",
            x + "AgeDays",
            "section_a.age_unit",
            "checkbox",
            "A2",
            "Age unit: " + AGE_UNIT_LABELS["days"],
            "days",
        ),
        _e(
            p + "DateBirth",
            x + "DateBirth",
            "section_a.date_of_birth",
            "date",
            "A2",
            "Date of birth",
        ),
        _e(
            p + "SexM",
            x + "SexM",
            "section_a.sex",
            "checkbox",
            "A3",
            "Sex: " + SEX_LABELS["M"],
            "M",
        ),
        _e(
            p + "SexF",
            x + "SexF",
            "section_a.sex",
            "checkbox",
            "A3",
            "Sex: " + SEX_LABELS["F"],
            "F",
        ),
        _e(p + "WeightValue", x + "WeightValue", "section_a.weight_value", "text", "A4", "Weight"),
        _e(
            p + "WeightKG",
            x + "WeightKG",
            "section_a.weight_unit",
            "checkbox",
            "A4",
            "Weight unit: kg",
            "kg",
        ),
        _e(
            p + "WeightLB",
            x + "WeightLB",
            "section_a.weight_unit",
            "checkbox",
            "A4",
            "Weight unit: lb",
            "lb",
        ),
    ]
    for short, code in (
        ("RaceAmInd", "american_indian_alaska_native"),
        ("RaceAsian", "asian"),
        ("RaceBlack", "black_african_american"),
        ("RaceMiddleEastern", "middle_eastern_north_african"),
        ("RacePacific", "native_hawaiian_pacific_islander"),
        ("RaceWhite", "white"),
    ):
        entries.append(
            _e(
                p + short,
                x + short,
                "section_a.race",
                "checkbox",
                "A5",
                "Race: " + RACE_LABELS[code],
                code,
            )
        )
    entries.append(
        _e(
            p + "EthnicLatino",
            x + "EthnicLatino",
            "section_a.hispanic_latino",
            "checkbox",
            "A5",
            "Ethnicity: Hispanic or Latino",
            True,
        )
    )
    return entries


def _section_b() -> list[FieldEntry]:
    p, x = "Page1.SecA_Patient.", "SecA_Patient/"
    entries = [
        _e(
            p + short,
            x + short,
            "section_b.report_types",
            "checkbox",
            "B1",
            "Type of report: " + REPORT_TYPE_LABELS[code],
            code,
        )
        for short, code in (
            ("RepAdverse", "adverse_event"),
            ("RepError", "product_use_error"),
            ("Defects", "product_problem"),
            ("DiffManu", "different_manufacturer_problem"),
        )
    ]
    for short, code in (
        ("Death", "death"),
        ("Hospital", "hospitalization"),
        ("LifeThreaten", "life_threatening"),
        ("Disability", "disability"),
        ("ReqdInter", "required_intervention"),
        ("Congenital", "congenital_anomaly"),
        ("OtherEvents", "other_serious"),
    ):
        entries.append(
            _e(
                p + short,
                x + short,
                "section_b.outcomes",
                "checkbox",
                "B2",
                "Outcome: " + OUTCOME_LABELS[code],
                code,
            )
        )
    entries += [
        _e(p + "DeathDate", x + "DeathDate", "section_b.death_date", "date", "B2", "Date of death"),
        _e(p + "EventDate", x + "EventDate", "section_b.event_date", "date", "B3", "Date of event"),
        _e(
            p + "ReportDate",
            x + "ReportDate",
            "section_b.report_date",
            "date",
            "B4",
            "Date of this report",
        ),
        _e(
            "Page2.SecB_Adverse.DescEvent",
            "Page2/SecB_Adverse/DescEvent",
            "section_b.narrative",
            "text",
            "B5",
            "Describe event, problem or product use/medication error",
        ),
    ]
    test_dates = {1: "Row1.TDate1", 2: "Row2.TDate2"} | {n: f"Row8.TDate{n}" for n in range(3, 9)}
    for n in range(1, 9):
        row = f"Row{n}"
        high = "Row8.THighRange7" if n == 7 else f"{row}.THighRange{n}"
        path = f"section_b.tests[{n - 1}]"
        for short, field, label in (
            (f"{row}.TestData{n}", "test", "relevant test/laboratory data"),
            (f"{row}.TLowRange{n}", "low_range", "low test range"),
            (high, "high_range", "high test range"),
            (test_dates[n], "date", "date"),
        ):
            entries.append(
                _e(
                    "Page3.TestDataTable." + short,
                    "TestDataTable/" + short.replace(".", "/"),
                    f"{path}.{field}",
                    "date" if field == "date" else "text",
                    "B6",
                    f"Test {n}: {label}",
                )
            )
    entries += [
        _e(
            "Page3.AdditionalComments",
            "AdditionalComments",
            "section_b.tests_comments",
            "text",
            "B6",
            "Additional comments on tests",
        ),
        _e(
            "Page3.Sec6Data.OtherHistory",
            "Sec6Data/OtherHistory",
            "section_b.other_history",
            "text",
            "B7",
            "Other relevant history",
        ),
    ]
    return entries


def _product(number: int) -> list[FieldEntry]:
    """Section D entries for suspect product 1 or 2."""
    page = "Page4" if number == 1 else "Page5"
    n = f"Prod{number}"
    p, x, model = f"{page}.{n}.", f"{n}/", f"section_d.product_{number}"
    item = f"D{number}"
    entries = [
        _e(p + f"{n}Name", f"{n}Name", f"{model}.name", "text", item, "Product name"),
        _e(p + f"{n}Strength", x + f"{n}Strength", f"{model}.strength", "text", item, "Strength"),
        _e(
            p + f"{n}StrengthUnit",
            x + f"{n}StrengthUnit",
            f"{model}.strength_unit",
            "choice",
            item,
            "Strength unit",
        ),
        _e(
            p + f"{n}NDC_ID",
            x + f"{n}NDC_ID",
            f"{model}.ndc_or_unique_id",
            "text",
            item,
            "NDC # or unique ID",
        ),
        _e(
            p + f"{n}ManuComp",
            x + f"{n}ManuComp",
            f"{model}.manufacturer_compounder",
            "text",
            item,
            "Manufacturer/compounder name",
        ),
        _e(p + f"{n}LotNum", x + f"{n}LotNum", f"{model}.lot", "text", item, "Lot #"),
        _e(p + f"{n}Dose", f"{n}Dose", f"{model}.dose", "text", item, "Dose or amount"),
        _e(
            p + f"{n}DoseUnit",
            x + f"{n}DoseUnit",
            f"{model}.dose_unit",
            "choice",
            item,
            "Dose unit",
        ),
        _e(p + f"{n}Freq", x + f"{n}Freq", f"{model}.frequency", "choice", item, "Frequency"),
        _e(
            p + f"{n}FreqOther",
            f"{n}FreqOther",
            f"{model}.frequency_other",
            "text",
            item,
            "Other frequency",
        ),
        _e(p + f"{n}Route", x + f"{n}Route", f"{model}.route", "choice", item, "Route"),
        _e(
            p + f"{n}RouteOther",
            f"{n}RouteOther",
            f"{model}.route_other",
            "text",
            item,
            "Other route",
        ),
        _e(
            p + f"{n}TherapyStartDate",
            x + f"{n}TherapyStartDate",
            f"{model}.therapy_start",
            "date",
            item,
            "Therapy/usage started on",
        ),
        _e(
            p + f"{n}TherapyStopDate",
            x + f"{n}TherapyStopDate",
            f"{model}.therapy_stop",
            "date",
            item,
            "Therapy/usage stopped on",
        ),
        _e(
            p + f"{n}TherapyReduceDate",
            x + f"{n}TherapyReduceDate",
            f"{model}.therapy_reduced",
            "date",
            item,
            "Dose reduced on",
        ),
        _e(
            p + f"{n}TherapyDuration",
            x + f"{n}TherapyDuration",
            f"{model}.duration",
            "text",
            item,
            "Duration",
        ),
        _e(
            p + f"{n}TherapyDurUnit",
            x + f"{n}TherapyDurUnit",
            f"{model}.duration_unit",
            "choice",
            item,
            "Duration unit",
        ),
        _e(
            p + f"{n}TherapyOngoingYes",
            x + f"{n}TherapyOngoingYes",
            f"{model}.ongoing",
            "checkbox",
            item,
            "Therapy ongoing: Yes",
            "yes",
        ),
        _e(
            p + f"{n}TherapyOngoingNo",
            x + f"{n}TherapyOngoingNo",
            f"{model}.ongoing",
            "checkbox",
            item,
            "Therapy ongoing: No",
            "no",
        ),
        _e(
            p + f"{n}Diagnosis",
            f"{n}Diagnosis",
            f"{model}.diagnosis_for_use",
            "text",
            item,
            "Diagnosis for use (indication)",
        ),
    ]
    type_fields = (
        (f"{n}Brand", "brand"),
        (f"{n}Generic", "generic_biosimilar"),
        (f"{n}OTC", "otc"),
        (f"{n}Compounded", "compounded"),
        ("Prod1PdtOther" if number == 1 else "Pdt2PdtOther", "other"),
        ("Prod1Cannabi" if number == 1 else "Pdt2Cannabi", "cannabinoid_hemp"),
        ("Prod1CosRetail" if number == 1 else "Pdt2CosRetail", "cosmetic_retail"),
        ("Prod1CosmProf" if number == 1 else "pdt2CosmProf", "cosmetic_professional"),
    )
    for short, code in type_fields:
        entries.append(
            _e(
                p + short,
                x + short,
                f"{model}.product_types",
                "checkbox",
                item,
                "Product type: " + PRODUCT_TYPE_LABELS[code],
                code,
            )
        )
    entries.append(
        _e(
            p + f"{n}ExpDate",
            x + f"{n}ExpDate",
            f"{model}.expiration_date",
            "date",
            item,
            "Expiration date",
        )
    )
    for stem, field, label in (
        ("Abated", "abated", "Event abated after use stopped or dose reduced"),
        ("Reappear", "reappeared", "Event reappeared after reintroduction"),
    ):
        for suffix, code in (("Yes", "yes"), ("No", "no"), ("NA", "not_applicable")):
            short = f"{n}{stem}{suffix}"
            entries.append(
                _e(
                    p + short,
                    x + short,
                    f"{model}.{field}",
                    "checkbox",
                    item,
                    f"{label}: {YES_NO_LABELS[code]}",
                    code,
                )
            )
    return entries


def _section_f() -> list[FieldEntry]:
    entries: list[FieldEntry] = []
    for n in range(1, 11):
        row = f"Row{n}"
        end = f"{row}.End{n}" if n <= 2 else f"{row}.Cell4"
        path = f"section_f.others[{n - 1}]"
        for short, field, kind, label in (
            (f"{row}.Prod{n}", "name", "text", "product name"),
            (f"{row}.Start{n}", "start", "date", "therapy start date"),
            (end, "end", "date", "therapy end date"),
        ):
            entries.append(
                _e(
                    "Page6.SecF_Other.Table1." + short,
                    "SecF_Other/Table1/" + short.replace(".", "/"),
                    f"{path}.{field}",
                    cast(FieldKind, kind),
                    "F1",
                    f"Other product {n}: {label}",
                )
            )
    return entries


def _section_g() -> list[FieldEntry]:
    p, x = "Page7.SecG_Reporter.", "SecG_Reporter/"
    entries = [
        _e(p + short, x + short, f"section_g.{field}", cast(FieldKind, kind), "G1", label)
        for short, field, kind, label in (
            ("LastName", "last_name", "text", "Last name"),
            ("FirstName", "first_name", "text", "First name"),
            ("Address", "address", "text", "Address"),
            ("City", "city", "text", "City"),
            ("State", "state", "text", "State/province/region"),
            ("ZipCode", "zip_code", "text", "ZIP/postal code"),
            ("Country", "country", "choice", "Country"),
            ("PhoneNum", "phone", "text", "Phone #"),
            ("Email", "email", "text", "Email"),
        )
    ]
    entries += [
        _e(
            p + "ProYes",
            x + "ProYes",
            "section_g.health_professional",
            "checkbox",
            "G2",
            "Health professional: Yes",
            "yes",
        ),
        _e(
            p + "ProNo",
            x + "ProNo",
            "section_g.health_professional",
            "checkbox",
            "G2",
            "Health professional: No",
            "no",
        ),
        _e(
            p + "Occupation", x + "Occupation", "section_g.occupation", "choice", "G3", "Occupation"
        ),
    ]
    for short, code in (
        ("ManuComp", "manufacturer_compounder"),
        ("UserFac", "user_facility"),
        ("DistImp", "distributor_importer"),
        ("Packer", "packer"),
    ):
        entries.append(
            _e(
                p + short,
                x + short,
                "section_g.also_reported_to",
                "checkbox",
                "G4",
                "Also reported to: " + ALSO_REPORTED_TO_LABELS[code],
                code,
            )
        )
    entries.append(
        _e(
            p + "IdentityNo",
            x + "IdentityNo",
            "section_g.identity_withheld",
            "checkbox",
            "G5",
            "Do not disclose reporter identity to the manufacturer",
            True,
        )
    )
    return entries


FIELD_MAP: tuple[FieldEntry, ...] = (
    *_section_a(),
    *_section_b(),
    *_product(1),
    *_product(2),
    *_section_f(),
    *_section_g(),
)
FIELD_MAP_NAMES: frozenset[str] = frozenset(entry.acroform for entry in FIELD_MAP)

_PATH_PART = re.compile(r"([a-z0-9_]+)(?:\[(\d+)\])?")


def model_value(form: MedWatchFormDataV2, path: str) -> Any:
    """Value at a model path such as ``section_b.tests[2].date``; ``None`` if absent."""
    current: Any = form
    for part in path.split("."):
        match = _PATH_PART.fullmatch(part)
        if match is None or current is None:
            return None
        current = getattr(current, match[1], None)
        if match[2] is not None:
            index = int(match[2])
            if not isinstance(current, list) or index >= len(current):
                return None
            current = current[index]
    return current


def choice_export_values(
    record: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, str]]:
    """Per choice field, display text -> export value, without unusable pairs."""
    options = cast(
        Mapping[str, list[list[str]]], (record or load_template_record())["choice_options"]
    )
    exports: dict[str, dict[str, str]] = {}
    for name, pairs in options.items():
        exports[name] = {
            display: export
            for export, display in pairs
            if display.strip() and (export, display) not in INCONSISTENT_CHOICE_PAIRS
        }
    return exports


@dataclass(frozen=True)
class MappedValues:
    """Values to write: AcroForm ``/V`` by field name and XFA text by ``datasets`` path."""

    acroform: dict[str, str]
    xfa: dict[str, str]


def _checked(value: Any, checked_when: str | bool | None) -> bool:
    if isinstance(value, list):
        return checked_when in value
    if isinstance(checked_when, bool):
        return value is checked_when
    return value is not None and value == checked_when


def map_form(form: MedWatchFormDataV2, record: Mapping[str, Any] | None = None) -> MappedValues:
    """Map every ``FIELD_MAP`` entry; blank text is ``""``, unchecked boxes ``/Off`` / ``0``."""
    exports = choice_export_values(record)
    acroform: dict[str, str] = {}
    xfa: dict[str, str] = {}
    for entry in FIELD_MAP:
        value = model_value(form, entry.model_path)
        if entry.kind == "checkbox":
            on = _checked(value, entry.checked_when)
            acroform[entry.acroform] = CHECKBOX_ON if on else CHECKBOX_OFF
            xfa[entry.xfa] = XFA_CHECKBOX_ON if on else XFA_CHECKBOX_OFF
            continue
        if value is None or value == "":
            text = ""
        elif entry.kind == "date":
            text = fda_date(str(value))
        elif entry.kind == "choice":
            text = exports[entry.acroform][str(value)]
        else:
            text = str(value)
        acroform[entry.acroform] = text
        xfa[entry.xfa] = text
    return MappedValues(acroform=acroform, xfa=xfa)
