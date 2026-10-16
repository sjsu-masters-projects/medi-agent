"""Form FDA 3500 (09/2025) draft data, version ``fda-3500-2025-09``.

The model holds the drug-report items of Sections A, B, D, F and G. Section C (product
availability), Section E (medical device), the place-of-purchase items and the FDA-use-only
header are deliberately absent; the clinician completes them in the downloaded PDF if
needed. ``mediagent_review`` is MediAgent's own Naranjo review and is never written to the
form. ``legacy`` keeps earlier draft text that has no Form 3500 item.

Dates are stored as ISO ``YYYY-MM-DD`` or ``YYYY-MM`` (month and year). Enumerated items
store a code or the template's display text; option lists equal the vendored template's
lists (``TEMPLATE.json``), so any other value fails validation with its field path.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationInfo,
    model_validator,
)
from pydantic import ValidationError as PydanticValidationError
from pydantic_core import InitErrorDetails, PydanticCustomError

from app.models.enums import NaranjoCausality
from app.services.medwatch_3500.dates import (
    clinic_today,
    earliest_day,
    latest_day,
    validate_iso_date,
)

FORM_3500_VERSION = "fda-3500-2025-09"
MAX_TEST_ROWS = 8
MAX_OTHER_PRODUCTS = 10


def _blank_to_none(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _iso_date_or_none(value: object) -> object:
    value = _blank_to_none(value)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Dates must be text in YYYY-MM-DD or YYYY-MM form")
    return validate_iso_date(value)


FdaDate = Annotated[str | None, BeforeValidator(_iso_date_or_none)]
"""ISO full date or month and year; blank means not provided."""

SexCode = Literal["F", "M"]
SEX_LABELS: Mapping[str, str] = {"F": "Female", "M": "Male"}

AgeUnit = Literal["years", "months", "weeks", "days"]
AGE_UNIT_LABELS: Mapping[str, str] = {
    "years": "Year(s)",
    "months": "Month(s)",
    "weeks": "Week(s)",
    "days": "Day(s)",
}

WeightUnit = Literal["kg", "lb"]
WEIGHT_UNIT_LABELS: Mapping[str, str] = {"kg": "kg", "lb": "lb"}

Race = Literal[
    "american_indian_alaska_native",
    "asian",
    "black_african_american",
    "middle_eastern_north_african",
    "native_hawaiian_pacific_islander",
    "white",
]
RACE_LABELS: Mapping[str, str] = {
    "american_indian_alaska_native": "American Indian or Alaska Native",
    "asian": "Asian",
    "black_african_american": "Black or African American",
    "middle_eastern_north_african": "Middle Eastern or North African",
    "native_hawaiian_pacific_islander": "Native Hawaiian or Pacific Islander",
    "white": "White",
}

ReportType = Literal[
    "adverse_event",
    "product_use_error",
    "product_problem",
    "different_manufacturer_problem",
]
REPORT_TYPE_LABELS: Mapping[str, str] = {
    "adverse_event": "Adverse Event",
    "product_use_error": "Product Use/Medication Error",
    "product_problem": "Product Problem (e.g., defects/malfunctions)",
    "different_manufacturer_problem": "Problem with Different Manufacturer of Same Medicine",
}

Outcome = Literal[
    "death",
    "life_threatening",
    "hospitalization",
    "disability",
    "congenital_anomaly",
    "required_intervention",
    "other_serious",
]
OUTCOME_LABELS: Mapping[str, str] = {
    "death": "Death",
    "life_threatening": "Life-threatening",
    "hospitalization": "Hospitalization (Initial or prolonged)",
    "disability": "Disability or Permanent Damage",
    "congenital_anomaly": "Congenital Anomaly/Birth Defects",
    "required_intervention": "Required Intervention to Prevent Permanent Impairment/Damage",
    "other_serious": "Other Serious or Important Medical Events",
}

YesNo = Literal["yes", "no"]
YesNoNotApplicable = Literal["yes", "no", "not_applicable"]
YES_NO_LABELS: Mapping[str, str] = {"yes": "Yes", "no": "No", "not_applicable": "Doesn't apply"}

ProductType = Literal[
    "brand",
    "generic_biosimilar",
    "otc",
    "compounded",
    "other",
    "cannabinoid_hemp",
    "cosmetic_retail",
    "cosmetic_professional",
]
PRODUCT_TYPE_LABELS: Mapping[str, str] = {
    "brand": "Brand",
    "generic_biosimilar": "Generic or Biosimilar",
    "otc": "Over-the-Counter (OTC)",
    "compounded": "Compounded product",
    "other": "Other",
    "cannabinoid_hemp": "Cannabinoid hemp products",
    "cosmetic_retail": "Cosmetics sold on a retail basis",
    "cosmetic_professional": "Cosmetics for professional use only",
}
_COSMETIC_TYPES = frozenset({"cosmetic_retail", "cosmetic_professional"})

AlsoReportedTo = Literal[
    "manufacturer_compounder", "user_facility", "distributor_importer", "packer"
]
ALSO_REPORTED_TO_LABELS: Mapping[str, str] = {
    "manufacturer_compounder": "Manufacturer/Compounder",
    "user_facility": "User Facility",
    "distributor_importer": "Distributor/Importer",
    "packer": "Packer",
}

# Display text of the template's strength and dose unit lists. The blank option and the
# second option (export "INTERNATIONAL UNITS PER MILLILITRE - IU/ML", display
# "AS NECESSARY - AN") are excluded: that pair names two different units.
DoseUnit = Literal[
    "BECQUEREL(S) - BQ",
    "CURIE(S) - CI",
    "CYCLICAL - CYC",
    "DOSAGE FORM - DF",
    "DROP(S) - GTT",
    "GIGABECQUEREL(S) - GBQ",
    "GRAM(S) - GM",
    "INTERNATIONAL UNIT(S) - IU",
    "IU(1,000,000S) - MIU",
    "IU(1000S) - KIU",
    "IU/KILOGRAM - IU/KG",
    "KILOBECQUEREL(S) - KBQ",
    "KILOGRAM(S) - KG",
    "LITRE(S) - L",
    "MEGABECQUEREL(S) - MBQ",
    "MICROCURIE(S) - UCI",
    "MICROGRAM(S) - UGM",
    "MICROGRAM(S)/KILOGRAM(S) -UGM/KG",
    "MICROGRAM(S)/MICROGRAM(S) - UGM/UGM",
    "MICROGRAM(S)/SQ. METERS - UGM/SQ M",
    "MICROGRAMS/HOUR - UGM/HR",
    "MICROLITRE(S) - UL",
    "MICROMOLE(S) - UMOLE",
    "MILLICURIE(S) - MCI",
    "MILLIEQUIVALENT(S) - MEQ",
    "MILLIGRAM(S) - MG",
    "MILLIGRAM(S)/KILOGRAM(S) - MG/KG",
    "MILLIGRAM(S)/SQ. METERS - MG/SQ M",
    "MILLIGRAMS/MILLIGRAMS - MG/MG",
    "MILLIGRAMS/MILLILITRES - MG/ML",
    "MILLILITRE(S) - ML",
    "MILLIMOLE(S) - MMOLE",
    "MOLE(S) - MOLE",
    "NANOCURIE(S) - NCI",
    "NANOGRAM(S) - NGM",
    "PERCENT - %",
    "PICOGRAM(S) - PGM",
    "TOTAL - TOT",
    "TRIMESTER - TRI",
    "UNKNOWN - UNK",
]

Frequency = Literal["BID", "Daily", "HS", "PRN", "QID", "TID", "Other"]

Route = Literal[
    "Auricular (otic)",
    "Buccal",
    "Cutaneous",
    "Dental",
    "Endocervical",
    "Endosinusial",
    "Endotracheal",
    "Epidural",
    "Extra-amniotic",
    "Hemodialysis",
    "Intra corpus cavernosum",
    "Intra-amniotic",
    "Intra-arterial",
    "Intra-articular",
    "Intra-uterine",
    "Intracardiac",
    "Intracavernous",
    "Intracerebral",
    "Intracervical",
    "Intracisternal",
    "Intracorneal",
    "Intracoronary",
    "Intradermal",
    "Intradiscal (intraspinal)",
    "Intrahepatic",
    "Intralesional",
    "Intralymphatic",
    "Intramedullar (bone marrow)",
    "Intrameningeal",
    "Intramuscular",
    "Intraocular",
    "Intrapericardial",
    "Intraperitoneal",
    "Intrapleural",
    "Intrasynovial",
    "Intrathecal",
    "Intrathoracic",
    "Intratracheal",
    "Intratumor",
    "Intravenous (not otherwise specified)",
    "Intravenous bolus",
    "Intravenous drip",
    "Intravesical",
    "Iontophoresis",
    "Nasal",
    "Occlusive dressing technique",
    "Ophthalmic",
    "Oral",
    "Oropharingeal",
    "Parenteral",
    "Periarticular",
    "Perineural",
    "Rectal",
    "Respiratory (inhalation)",
    "Retrobulbar",
    "Subcutaneous",
    "Subdermal",
    "Sublingual",
    "Sunconjunctival",
    "Topical",
    "Transdermal",
    "Transmammary",
    "Transplacental",
    "Unknown",
    "Urethral",
    "Vaginal",
    "Other",
]

DurationUnit = Literal["Minute(s)", "Hour(s)", "Day(s)", "Week(s)", "Month(s)", "Year(s)"]

Occupation = Literal[
    "Administrator/Supervisor",
    "Biomedical Engineer",
    "Dentist",
    "Non-Health Professional",
    "Nurse",
    "Nurse Practitioner",
    "Other Health Professional",
    "Pharmacist",
    "Physician",
    "Physician Assistant",
    "Risk Manager",
    "Third Party Servicer",
]

OptionalSex = Annotated[SexCode | None, BeforeValidator(_blank_to_none)]
OptionalAgeUnit = Annotated[AgeUnit | None, BeforeValidator(_blank_to_none)]
OptionalWeightUnit = Annotated[WeightUnit | None, BeforeValidator(_blank_to_none)]
OptionalDoseUnit = Annotated[DoseUnit | None, BeforeValidator(_blank_to_none)]
OptionalFrequency = Annotated[Frequency | None, BeforeValidator(_blank_to_none)]
OptionalRoute = Annotated[Route | None, BeforeValidator(_blank_to_none)]
OptionalDurationUnit = Annotated[DurationUnit | None, BeforeValidator(_blank_to_none)]
OptionalOccupation = Annotated[Occupation | None, BeforeValidator(_blank_to_none)]
OptionalYesNo = Annotated[YesNo | None, BeforeValidator(_blank_to_none)]
OptionalYesNoNotApplicable = Annotated[YesNoNotApplicable | None, BeforeValidator(_blank_to_none)]


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SectionA(_Section):
    """A. Patient information."""

    identifier: str = Field(default="", max_length=50)
    age_value: str = Field(default="", pattern=r"^(\d{1,3})?$")
    age_unit: OptionalAgeUnit = None
    date_of_birth: FdaDate = None
    sex: OptionalSex = None
    weight_value: str = Field(default="", pattern=r"^(\d{1,5})?$")
    weight_unit: OptionalWeightUnit = None
    race: list[Race] = Field(default_factory=list)
    hispanic_latino: bool = False


class TestRow(_Section):
    """One B6 row: test and result, low and high range, date."""

    test: str = Field(default="", max_length=500)
    low_range: str = Field(default="", max_length=50)
    high_range: str = Field(default="", max_length=50)
    date: FdaDate = None


class SectionB(_Section):
    """B. Adverse event, product problem."""

    report_types: list[ReportType] = Field(default_factory=list)
    outcomes: list[Outcome] = Field(default_factory=list)
    death_date: FdaDate = None
    event_date: FdaDate = None
    event_date_confirmed: bool = False
    report_date: FdaDate = None
    narrative: str = Field(default="", max_length=4000)
    tests: list[TestRow] = Field(default_factory=list, max_length=MAX_TEST_ROWS)
    tests_comments: str = Field(default="", max_length=2000)
    other_history: str = Field(default="", max_length=2000)


class Product(_Section):
    """One D suspect product."""

    name: str = Field(default="", max_length=255)
    strength: str = Field(default="", max_length=50)
    strength_unit: OptionalDoseUnit = None
    manufacturer_compounder: str = Field(default="", max_length=255)
    ndc_or_unique_id: str = Field(default="", max_length=100)
    lot: str = Field(default="", max_length=100)
    dose: str = Field(default="", max_length=50)
    dose_unit: OptionalDoseUnit = None
    frequency: OptionalFrequency = None
    frequency_other: str = Field(default="", max_length=100)
    route: OptionalRoute = None
    route_other: str = Field(default="", max_length=100)
    therapy_start: FdaDate = None
    therapy_stop: FdaDate = None
    therapy_reduced: FdaDate = None
    duration: str = Field(default="", pattern=r"^(\d{1,5})?$")
    duration_unit: OptionalDurationUnit = None
    ongoing: OptionalYesNo = None
    diagnosis_for_use: str = Field(default="", max_length=500)
    product_types: list[ProductType] = Field(default_factory=list)
    expiration_date: FdaDate = None
    abated: OptionalYesNoNotApplicable = None
    reappeared: OptionalYesNoNotApplicable = None


class SectionD(_Section):
    """D. Suspect products (up to two)."""

    product_1: Product = Field(default_factory=Product)
    product_2: Product | None = None


class OtherProduct(_Section):
    """One F row: product name and therapy dates."""

    name: str = Field(default="", max_length=255)
    start: FdaDate = None
    end: FdaDate = None


class SectionF(_Section):
    """F. Other (concomitant) medical products."""

    others: list[OtherProduct] = Field(default_factory=list, max_length=MAX_OTHER_PRODUCTS)


class SectionG(_Section):
    """G. Reporter. Reporter identity appears only here."""

    first_name: str = Field(default="", max_length=100)
    last_name: str = Field(default="", max_length=100)
    address: str = Field(default="", max_length=100)
    city: str = Field(default="", max_length=100)
    state: str = Field(default="", max_length=100)
    zip_code: str = Field(default="", max_length=10)
    country: str = Field(default="", max_length=100)
    phone: str = Field(default="", max_length=30)
    email: str = Field(default="", max_length=254)
    health_professional: OptionalYesNo = None
    occupation: OptionalOccupation = None
    also_reported_to: list[AlsoReportedTo] = Field(default_factory=list)
    identity_withheld: bool = False


class MediAgentReview(_Section):
    """MediAgent's Naranjo review. Shown in MediAgent and JSON only, never on the form."""

    naranjo_score: int | None = Field(default=None, ge=-4, le=13)
    causality: NaranjoCausality | None = None
    reportability_rationale: str = Field(default="", max_length=2000)


class MedWatchFormDataV2(BaseModel):
    """A Form 3500 drug-report draft."""

    model_config = ConfigDict(extra="forbid")

    form_version: Literal["fda-3500-2025-09"]
    section_a: SectionA = Field(default_factory=SectionA)
    section_b: SectionB = Field(default_factory=SectionB)
    section_d: SectionD = Field(default_factory=SectionD)
    section_f: SectionF = Field(default_factory=SectionF)
    section_g: SectionG = Field(default_factory=SectionG)
    mediagent_review: MediAgentReview = Field(default_factory=MediAgentReview)
    legacy: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_form_rules(self, info: ValidationInfo) -> MedWatchFormDataV2:
        today = _validation_today(info)
        errors: list[InitErrorDetails] = []
        errors.extend(_not_after_today(self, today))
        errors.extend(_ordered_dates(self))
        errors.extend(_other_text_rules(self))
        errors.extend(_choice_rules(self))
        if errors:
            raise PydanticValidationError.from_exception_data(type(self).__name__, errors)
        return self


def _validation_today(info: ValidationInfo) -> date:
    context = info.context if isinstance(info.context, Mapping) else {}
    today = context.get("today")
    return today if isinstance(today, date) else clinic_today()


def _error(loc: tuple[str | int, ...], kind: str, message: str, value: object) -> InitErrorDetails:
    return {"type": PydanticCustomError(kind, message), "loc": loc, "input": value}


def _products(form: MedWatchFormDataV2) -> list[tuple[str, Product]]:
    products = [("product_1", form.section_d.product_1)]
    if form.section_d.product_2 is not None:
        products.append(("product_2", form.section_d.product_2))
    return products


def _dated_items(form: MedWatchFormDataV2) -> list[tuple[tuple[str | int, ...], str | None]]:
    """Dates that cannot be after the save date. The expiration date may be future."""
    a, b = form.section_a, form.section_b
    items: list[tuple[tuple[str | int, ...], str | None]] = [
        (("section_a", "date_of_birth"), a.date_of_birth),
        (("section_b", "death_date"), b.death_date),
        (("section_b", "event_date"), b.event_date),
        (("section_b", "report_date"), b.report_date),
    ]
    items.extend(
        (("section_b", "tests", index, "date"), row.date) for index, row in enumerate(b.tests)
    )
    for key, product in _products(form):
        for name in ("therapy_start", "therapy_stop", "therapy_reduced"):
            items.append((("section_d", key, name), getattr(product, name)))
    for index, other in enumerate(form.section_f.others):
        items.append((("section_f", "others", index, "start"), other.start))
        items.append((("section_f", "others", index, "end"), other.end))
    return items


def _not_after_today(form: MedWatchFormDataV2, today: date) -> list[InitErrorDetails]:
    return [
        _error(loc, "date_after_save_date", f"Date must not be after {today.isoformat()}", value)
        for loc, value in _dated_items(form)
        if value is not None and earliest_day(value) > today
    ]


def _ordered_dates(form: MedWatchFormDataV2) -> list[InitErrorDetails]:
    pairs: list[tuple[tuple[str | int, ...], str | None, str | None]] = [
        (("section_d", key, "therapy_stop"), product.therapy_start, product.therapy_stop)
        for key, product in _products(form)
    ]
    pairs.extend(
        (("section_f", "others", index, "end"), other.start, other.end)
        for index, other in enumerate(form.section_f.others)
    )
    return [
        _error(loc, "date_before_start", "Stop date must not be before the start date", stop)
        for loc, start, stop in pairs
        if start is not None and stop is not None and latest_day(stop) < earliest_day(start)
    ]


def _other_text_rules(form: MedWatchFormDataV2) -> list[InitErrorDetails]:
    errors: list[InitErrorDetails] = []
    for key, product in _products(form):
        for choice, other in (("frequency", "frequency_other"), ("route", "route_other")):
            chosen = getattr(product, choice) == "Other"
            text = str(getattr(product, other)).strip()
            if chosen and not text:
                errors.append(
                    _error(
                        ("section_d", key, other),
                        "other_text_required",
                        f"Describe the {choice} when Other is selected",
                        text,
                    )
                )
            elif not chosen and text:
                errors.append(
                    _error(
                        ("section_d", key, other),
                        "other_text_not_allowed",
                        f"Only add this text when the {choice} is Other",
                        text,
                    )
                )
    return errors


def _choice_rules(form: MedWatchFormDataV2) -> list[InitErrorDetails]:
    errors: list[InitErrorDetails] = []
    lists: list[tuple[tuple[str | int, ...], list[str]]] = [
        (("section_a", "race"), list(form.section_a.race)),
        (("section_b", "report_types"), list(form.section_b.report_types)),
        (("section_b", "outcomes"), list(form.section_b.outcomes)),
        (("section_g", "also_reported_to"), list(form.section_g.also_reported_to)),
    ]
    lists.extend(
        (("section_d", key, "product_types"), list(product.product_types))
        for key, product in _products(form)
    )
    for loc, values in lists:
        if len(values) != len(set(values)):
            errors.append(_error(loc, "duplicate_choice", "Each option may be chosen once", values))
    for key, product in _products(form):
        if len(_COSMETIC_TYPES & set(product.product_types)) > 1:
            errors.append(
                _error(
                    ("section_d", key, "product_types"),
                    "cosmetic_select_one",
                    "Choose one cosmetic product type",
                    list(product.product_types),
                )
            )
    b = form.section_b
    if b.death_date is not None and "death" not in b.outcomes:
        errors.append(
            _error(
                ("section_b", "death_date"),
                "death_date_without_death",
                "Give a date of death only when Death is checked",
                b.death_date,
            )
        )
    country = form.section_g.country
    if country.strip() and country not in _reporter_countries():
        errors.append(
            _error(
                ("section_g", "country"),
                "country_not_in_form",
                "Choose a country from the form's list",
                country,
            )
        )
    return errors


def _reporter_countries() -> frozenset[str]:
    # The country list is long and lives only in the pinned template record.
    from app.services.medwatch_3500.template import load_template_record

    options: Mapping[str, Any] = load_template_record()["choice_options"]
    pairs = options["topmostSubform[0].Page7[0].SecG_Reporter[0].Country[0]"]
    return frozenset(str(display) for _export, display in pairs if str(display).strip())


class MedWatchNameWarning(BaseModel):
    """Free text that contains a person or clinic name (FDA B5: identify no one by name)."""

    model_config = ConfigDict(frozen=True)

    path: str
    kind: Literal["patient_name", "clinician_name", "clinic_name"]


GateIssueCode = Literal[
    "identifier_missing",
    "identifier_identifies",
    "report_type_missing",
    "death_date_missing",
    "non_serious_attestation_required",
    "event_date_missing",
    "event_date_unconfirmed",
    "narrative_missing",
    "product_name_missing",
    "reporter_first_name_missing",
    "reporter_last_name_missing",
    "reporter_contact_missing",
    "health_professional_missing",
    "occupation_missing",
    "reportability_rationale_missing",
]


class MedWatchGateIssue(BaseModel):
    """One item that blocks approval, with the field path it belongs to."""

    model_config = ConfigDict(frozen=True)

    path: str
    code: GateIssueCode


MedWatchListState = Literal["active", "submitted", "discarded"]
SubmissionMethod = Literal["medwatch_online", "fax", "mail", "other"]
SUBMISSION_METHOD_LABELS: Mapping[str, str] = {
    "medwatch_online": "MedWatch Online",
    "fax": "Fax",
    "mail": "Mail",
    "other": "Other",
}


class MedWatchExternalSubmissionRead(BaseModel):
    """A clinician's record of a Form 3500 submission made outside MediAgent."""

    id: str
    submitted_on: str
    method: SubmissionMethod
    method_detail: str | None = None
    fda_reference: str | None = None
    recorded_by: str
    recorded_by_name: str | None = None
    amends_id: str | None = None
    amend_reason: str | None = None
    created_at: str


ProvenanceKind = Literal["record", "ai_extracted", "patient_confirmed", "clinician_edited"]


class Form3500Provenance(BaseModel):
    """Where one preview item's value came from."""

    kind: ProvenanceKind
    source_type: str | None = None
    attribution: str | None = None
    citation: str | None = None


class Form3500PreviewItem(BaseModel):
    """One Form 3500 item as it reads on the form; ``value`` is ``None`` when blank."""

    item: str
    label: str
    path: str
    value: str | None = None
    provenance: list[Form3500Provenance] = Field(default_factory=list)
    missing_for_approval: list[GateIssueCode] = Field(default_factory=list)


class Form3500PreviewSection(BaseModel):
    """One Form 3500 section, in form order. C and E are never completed by MediAgent."""

    section: Literal["A", "B", "C", "D", "E", "F", "G"]
    title: str
    completion: Literal["mediagent", "not_completed_by_mediagent"]
    items: list[Form3500PreviewItem] = Field(default_factory=list)


class Form3500TemplateRead(BaseModel):
    """The vendored official form revision the draft is laid out on."""

    title: str
    revision: str
    omb_number: str
    expires: str
    may_be_superseded: bool


class Form3500PreviewRead(BaseModel):
    """Read-only Form 3500 layout of a draft in any status."""

    draft_id: str
    status: str
    revision: int
    export_version: str
    discarded: bool
    sections: list[Form3500PreviewSection]
    missing_for_approval: list[MedWatchGateIssue] = Field(default_factory=list)
    name_warnings: list[MedWatchNameWarning] = Field(default_factory=list)
    mediagent_review: MediAgentReview
    legacy: dict[str, str] = Field(default_factory=dict)
    template: Form3500TemplateRead
    current_submission: MedWatchExternalSubmissionRead | None = None
    not_submitted_to_fda: Literal[True] = True


class Form3500Option(BaseModel):
    """One allowed value of an enumerated item and its form text."""

    value: str
    label: str


class Form3500OptionsRead(BaseModel):
    """Every option list the edit form offers, taken from the model and the template."""

    form_version: Literal["fda-3500-2025-09"] = "fda-3500-2025-09"
    sex: list[Form3500Option]
    age_unit: list[Form3500Option]
    weight_unit: list[Form3500Option]
    race: list[Form3500Option]
    report_types: list[Form3500Option]
    outcomes: list[Form3500Option]
    yes_no: list[Form3500Option]
    yes_no_not_applicable: list[Form3500Option]
    product_types: list[Form3500Option]
    dose_units: list[Form3500Option]
    frequencies: list[Form3500Option]
    routes: list[Form3500Option]
    duration_units: list[Form3500Option]
    occupations: list[Form3500Option]
    also_reported_to: list[Form3500Option]
    countries: list[Form3500Option]
    submission_methods: list[Form3500Option]
