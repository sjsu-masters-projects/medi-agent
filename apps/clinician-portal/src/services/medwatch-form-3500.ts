/**
 * Form FDA 3500 (09/2025) draft data, version `fda-3500-2025-09`.
 *
 * Mirrors the backend model `app/models/medwatch_form_3500.py`: Sections A, B, D, F and G,
 * MediAgent's own review (never written to the form) and earlier draft text with no Form 3500
 * item. Option lists equal the backend `Literal`s, which equal the vendored template's lists.
 * Dates are ISO `YYYY-MM-DD` or `YYYY-MM` (month and year); `null` means not provided.
 */

import type { NaranjoCausality } from "@/types";

export const FORM_3500_VERSION = "fda-3500-2025-09";
export const MAX_TEST_ROWS = 8;
export const MAX_OTHER_PRODUCTS = 10;

export interface Option<T extends string> {
    value: T;
    label: string;
}

function options<T extends string>(labels: Record<T, string>): Option<T>[] {
    return (Object.keys(labels) as T[]).map((value) => ({ value, label: labels[value] }));
}

function plain<T extends string>(values: readonly T[]): Option<T>[] {
    return values.map((value) => ({ value, label: value }));
}

export type SexCode = "F" | "M";
export const SEX_LABELS: Record<SexCode, string> = { F: "Female", M: "Male" };

export type AgeUnit = "years" | "months" | "weeks" | "days";
export const AGE_UNIT_LABELS: Record<AgeUnit, string> = {
    years: "Year(s)",
    months: "Month(s)",
    weeks: "Week(s)",
    days: "Day(s)",
};

export type WeightUnit = "kg" | "lb";
export const WEIGHT_UNIT_LABELS: Record<WeightUnit, string> = { kg: "kg", lb: "lb" };

export type Race =
    | "american_indian_alaska_native"
    | "asian"
    | "black_african_american"
    | "middle_eastern_north_african"
    | "native_hawaiian_pacific_islander"
    | "white";
export const RACE_LABELS: Record<Race, string> = {
    american_indian_alaska_native: "American Indian or Alaska Native",
    asian: "Asian",
    black_african_american: "Black or African American",
    middle_eastern_north_african: "Middle Eastern or North African",
    native_hawaiian_pacific_islander: "Native Hawaiian or Pacific Islander",
    white: "White",
};

export type ReportType =
    | "adverse_event"
    | "product_use_error"
    | "product_problem"
    | "different_manufacturer_problem";
export const REPORT_TYPE_LABELS: Record<ReportType, string> = {
    adverse_event: "Adverse Event",
    product_use_error: "Product Use/Medication Error",
    product_problem: "Product Problem (e.g., defects/malfunctions)",
    different_manufacturer_problem: "Problem with Different Manufacturer of Same Medicine",
};

export type Outcome =
    | "death"
    | "life_threatening"
    | "hospitalization"
    | "disability"
    | "congenital_anomaly"
    | "required_intervention"
    | "other_serious";
export const OUTCOME_LABELS: Record<Outcome, string> = {
    death: "Death",
    life_threatening: "Life-threatening",
    hospitalization: "Hospitalization (Initial or prolonged)",
    disability: "Disability or Permanent Damage",
    congenital_anomaly: "Congenital Anomaly/Birth Defects",
    required_intervention: "Required Intervention to Prevent Permanent Impairment/Damage",
    other_serious: "Other Serious or Important Medical Events",
};

export type YesNo = "yes" | "no";
export type YesNoNotApplicable = YesNo | "not_applicable";
export const YES_NO_LABELS: Record<YesNoNotApplicable, string> = {
    yes: "Yes",
    no: "No",
    not_applicable: "Doesn't apply",
};

export type ProductType =
    | "brand"
    | "generic_biosimilar"
    | "otc"
    | "compounded"
    | "other"
    | "cannabinoid_hemp"
    | "cosmetic_retail"
    | "cosmetic_professional";
export const PRODUCT_TYPE_LABELS: Record<ProductType, string> = {
    brand: "Brand",
    generic_biosimilar: "Generic or Biosimilar",
    otc: "Over-the-Counter (OTC)",
    compounded: "Compounded product",
    other: "Other",
    cannabinoid_hemp: "Cannabinoid hemp products",
    cosmetic_retail: "Cosmetics sold on a retail basis",
    cosmetic_professional: "Cosmetics for professional use only",
};

export type AlsoReportedTo =
    | "manufacturer_compounder"
    | "user_facility"
    | "distributor_importer"
    | "packer";
export const ALSO_REPORTED_TO_LABELS: Record<AlsoReportedTo, string> = {
    manufacturer_compounder: "Manufacturer/Compounder",
    user_facility: "User Facility",
    distributor_importer: "Distributor/Importer",
    packer: "Packer",
};

export const DOSE_UNITS = [
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
] as const;
export type DoseUnit = (typeof DOSE_UNITS)[number];

export const FREQUENCIES = ["BID", "Daily", "HS", "PRN", "QID", "TID", "Other"] as const;
export type Frequency = (typeof FREQUENCIES)[number];

export const ROUTES = [
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
] as const;
export type Route = (typeof ROUTES)[number];

export const DURATION_UNITS = [
    "Minute(s)",
    "Hour(s)",
    "Day(s)",
    "Week(s)",
    "Month(s)",
    "Year(s)",
] as const;
export type DurationUnit = (typeof DURATION_UNITS)[number];

export const OCCUPATIONS = [
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
] as const;
export type Occupation = (typeof OCCUPATIONS)[number];

export const FORM_3500_OPTIONS = {
    sex: options(SEX_LABELS),
    ageUnit: options(AGE_UNIT_LABELS),
    weightUnit: options(WEIGHT_UNIT_LABELS),
    race: options(RACE_LABELS),
    reportType: options(REPORT_TYPE_LABELS),
    outcome: options(OUTCOME_LABELS),
    yesNo: options({ yes: "Yes", no: "No" } as Record<YesNo, string>),
    yesNoNotApplicable: options(YES_NO_LABELS),
    productType: options(PRODUCT_TYPE_LABELS),
    alsoReportedTo: options(ALSO_REPORTED_TO_LABELS),
    doseUnit: plain(DOSE_UNITS),
    frequency: plain(FREQUENCIES),
    route: plain(ROUTES),
    durationUnit: plain(DURATION_UNITS),
    occupation: plain(OCCUPATIONS),
} as const;

export type FdaDate = string | null;

export interface Form3500SectionA {
    identifier: string;
    age_value: string;
    age_unit: AgeUnit | null;
    date_of_birth: FdaDate;
    sex: SexCode | null;
    weight_value: string;
    weight_unit: WeightUnit | null;
    race: Race[];
    hispanic_latino: boolean;
}

export interface Form3500TestRow {
    test: string;
    low_range: string;
    high_range: string;
    date: FdaDate;
}

export interface Form3500SectionB {
    report_types: ReportType[];
    outcomes: Outcome[];
    death_date: FdaDate;
    event_date: FdaDate;
    event_date_confirmed: boolean;
    report_date: FdaDate;
    narrative: string;
    tests: Form3500TestRow[];
    tests_comments: string;
    other_history: string;
}

export interface Form3500Product {
    name: string;
    strength: string;
    strength_unit: DoseUnit | null;
    manufacturer_compounder: string;
    ndc_or_unique_id: string;
    lot: string;
    dose: string;
    dose_unit: DoseUnit | null;
    frequency: Frequency | null;
    frequency_other: string;
    route: Route | null;
    route_other: string;
    therapy_start: FdaDate;
    therapy_stop: FdaDate;
    therapy_reduced: FdaDate;
    duration: string;
    duration_unit: DurationUnit | null;
    ongoing: YesNo | null;
    diagnosis_for_use: string;
    product_types: ProductType[];
    expiration_date: FdaDate;
    abated: YesNoNotApplicable | null;
    reappeared: YesNoNotApplicable | null;
}

export interface Form3500OtherProduct {
    name: string;
    start: FdaDate;
    end: FdaDate;
}

export interface Form3500SectionG {
    first_name: string;
    last_name: string;
    address: string;
    city: string;
    state: string;
    zip_code: string;
    country: string;
    phone: string;
    email: string;
    health_professional: YesNo | null;
    occupation: Occupation | null;
    also_reported_to: AlsoReportedTo[];
    identity_withheld: boolean;
}

export interface MediAgentReview {
    naranjo_score: number | null;
    causality: NaranjoCausality | null;
    reportability_rationale: string;
}

export interface MedWatchFormDataV2 {
    form_version: typeof FORM_3500_VERSION;
    section_a: Form3500SectionA;
    section_b: Form3500SectionB;
    section_d: { product_1: Form3500Product; product_2: Form3500Product | null };
    section_f: { others: Form3500OtherProduct[] };
    section_g: Form3500SectionG;
    mediagent_review: MediAgentReview;
    legacy: Record<string, string>;
}

export function blankProduct(): Form3500Product {
    return {
        name: "",
        strength: "",
        strength_unit: null,
        manufacturer_compounder: "",
        ndc_or_unique_id: "",
        lot: "",
        dose: "",
        dose_unit: null,
        frequency: null,
        frequency_other: "",
        route: null,
        route_other: "",
        therapy_start: null,
        therapy_stop: null,
        therapy_reduced: null,
        duration: "",
        duration_unit: null,
        ongoing: null,
        diagnosis_for_use: "",
        product_types: [],
        expiration_date: null,
        abated: null,
        reappeared: null,
    };
}

export function blankTestRow(): Form3500TestRow {
    return { test: "", low_range: "", high_range: "", date: null };
}

export function blankOtherProduct(): Form3500OtherProduct {
    return { name: "", start: null, end: null };
}

// ── Approval gate and name warnings (backend gate.py / identifier.py) ───────────

export type GateIssueCode =
    | "identifier_missing"
    | "identifier_identifies"
    | "report_type_missing"
    | "death_date_missing"
    | "non_serious_attestation_required"
    | "event_date_missing"
    | "event_date_unconfirmed"
    | "narrative_missing"
    | "product_name_missing"
    | "reporter_first_name_missing"
    | "reporter_last_name_missing"
    | "reporter_contact_missing"
    | "health_professional_missing"
    | "occupation_missing"
    | "reportability_rationale_missing";

export interface MedWatchGateIssue {
    path: string;
    code: GateIssueCode | string;
}

export const GATE_ISSUE_LABELS: Record<GateIssueCode, string> = {
    identifier_missing: "A1 Patient identifier is missing",
    identifier_identifies: "A1 Patient identifier contains a name, email or date of birth",
    report_type_missing: "B1 Choose at least one type of report",
    death_date_missing: "B2 Date of death is required when Death is checked",
    non_serious_attestation_required:
        "B2 No outcome is checked: attest that the event is not serious when you approve",
    event_date_missing: "B3 Date of event is missing",
    event_date_unconfirmed: "B3 Confirm the best-estimate date of event",
    narrative_missing: "B5 Event description is missing",
    product_name_missing: "D1 Suspect product name is missing",
    reporter_first_name_missing: "G1 Reporter first name is missing",
    reporter_last_name_missing: "G1 Reporter last name is missing",
    reporter_contact_missing: "G1 Give a reporter phone number or email",
    health_professional_missing: "G2 Answer whether the reporter is a health professional",
    occupation_missing: "G3 Reporter occupation is missing",
    reportability_rationale_missing: "MediAgent review: reportability rationale is missing",
};

export function gateIssueLabel(issue: MedWatchGateIssue): string {
    return (
        GATE_ISSUE_LABELS[issue.code as GateIssueCode] ??
        `${fieldPathLabel(issue.path)} is incomplete`
    );
}

/** Issues the approval dialog can clear itself rather than the saved form. */
export function isAttestationIssue(issue: MedWatchGateIssue): boolean {
    return issue.code === "non_serious_attestation_required";
}

export type NameWarningKind = "patient_name" | "clinician_name" | "clinic_name";

export interface MedWatchNameWarning {
    path: string;
    kind: NameWarningKind | string;
}

export const NAME_WARNING_LABELS: Record<NameWarningKind, string> = {
    patient_name: "Contains the patient's name",
    clinician_name: "Contains a clinician's name",
    clinic_name: "Contains the clinic's name",
};

export function nameWarningLabel(warning: MedWatchNameWarning): string {
    return NAME_WARNING_LABELS[warning.kind as NameWarningKind] ?? "Contains a name";
}

const SIMPLE_PATH_LABELS: Record<string, string> = {
    "section_a.identifier": "A1 Patient identifier",
    "section_b.report_types": "B1 Type of report",
    "section_b.outcomes": "B2 Outcome",
    "section_b.death_date": "B2 Date of death",
    "section_b.event_date": "B3 Date of event",
    "section_b.report_date": "B4 Date of this report",
    "section_b.narrative": "B5 Describe event, problem or product use/medication error",
    "section_b.tests_comments": "B6 Additional comments on tests",
    "section_b.other_history": "B7 Other relevant history",
    "section_d.product_1.name": "D1 Product name",
    "section_g.first_name": "G1 First name",
    "section_g.last_name": "G1 Last name",
    "section_g.email": "G1 Email",
    "section_g.phone": "G1 Phone #",
    "section_g.health_professional": "G2 Health professional",
    "section_g.occupation": "G3 Occupation",
    "mediagent_review.reportability_rationale": "Reportability rationale",
};

const ROW_FIELD_LABELS: Record<string, string> = {
    test: "Test and result",
    low_range: "Low range",
    high_range: "High range",
    date: "Date",
    name: "Product name",
    start: "Start date",
    end: "End date",
};

/** A readable label for a model path such as `section_f.others[2].name`. */
export function fieldPathLabel(path: string): string {
    if (SIMPLE_PATH_LABELS[path]) return SIMPLE_PATH_LABELS[path];
    const test = /^section_b\.tests\[(\d+)\]\.(\w+)$/.exec(path);
    if (test) return `B6 Test ${Number(test[1]) + 1}: ${ROW_FIELD_LABELS[test[2]] ?? test[2]}`;
    const other = /^section_f\.others\[(\d+)\]\.(\w+)$/.exec(path);
    if (other) {
        return `F Other product ${Number(other[1]) + 1}: ${ROW_FIELD_LABELS[other[2]] ?? other[2]}`;
    }
    return humanizePath(path);
}

/** "section_b.lab_notes" as "Section B · Lab notes" for paths with no Form 3500 item. */
function humanizePath(path: string): string {
    return path
        .split(".")
        .map((part) => {
            const section = /^section_([a-z])$/i.exec(part);
            if (section) return `Section ${section[1].toUpperCase()}`;
            const words = part.replace(/\[(\d+)\]/g, (_, index: string) => ` ${Number(index) + 1}`).replaceAll("_", " ").trim();
            return words ? words.charAt(0).toUpperCase() + words.slice(1) : part;
        })
        .join(" · ");
}

/** A label for an earlier-draft key that has no Form 3500 item. */
export function legacyKeyLabel(key: string): string {
    return fieldPathLabel(key);
}
