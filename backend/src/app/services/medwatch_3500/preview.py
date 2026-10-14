"""Read-only Form 3500 layout of a draft, and the option lists the edit form offers.

Item numbers and labels come from ``field_map.py``, so the preview reads like the official
form and shows exactly the items the PDF fill writes. Sections C and E are listed but never
completed by MediAgent. ``mediagent_review`` is returned separately: it is not part of
Form 3500.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from typing import Any, Literal, cast, get_args

from app.models.medwatch_form_3500 import (
    AGE_UNIT_LABELS,
    ALSO_REPORTED_TO_LABELS,
    OUTCOME_LABELS,
    PRODUCT_TYPE_LABELS,
    RACE_LABELS,
    REPORT_TYPE_LABELS,
    SEX_LABELS,
    SUBMISSION_METHOD_LABELS,
    WEIGHT_UNIT_LABELS,
    YES_NO_LABELS,
    DoseUnit,
    DurationUnit,
    Form3500Option,
    Form3500OptionsRead,
    Form3500PreviewItem,
    Form3500PreviewRead,
    Form3500PreviewSection,
    Form3500Provenance,
    Form3500TemplateRead,
    Frequency,
    MedWatchExternalSubmissionRead,
    MedWatchFormDataV2,
    MedWatchGateIssue,
    MedWatchNameWarning,
    Occupation,
    ProvenanceKind,
    Route,
)
from app.services.medwatch_3500.dates import clinic_today, fda_date
from app.services.medwatch_3500.field_map import FIELD_MAP, FieldEntry, model_value
from app.services.medwatch_3500.template import load_template_record

SectionLetter = Literal["A", "B", "C", "D", "E", "F", "G"]
SECTION_TITLES: tuple[tuple[SectionLetter, str], ...] = (
    ("A", "Patient information"),
    ("B", "Adverse event, product problem"),
    ("C", "Product availability"),
    ("D", "Suspect products"),
    ("E", "Suspect medical device"),
    ("F", "Other (concomitant) medical products"),
    ("G", "Reporter"),
)
NOT_COMPLETED_SECTIONS = frozenset({"C", "E"})

_PROVENANCE_KINDS: Mapping[str, ProvenanceKind] = {
    "ai_extracted_adr_evidence": "ai_extracted",
    "patient_confirmed_adr_evidence": "patient_confirmed",
}
_COUNTRY_FIELD = "topmostSubform[0].Page7[0].SecG_Reporter[0].Country[0]"


def _related(path: str, other: str) -> bool:
    """``other`` is ``path``, inside it, or contains it (``section_f.others`` edits row 0)."""
    if path == other:
        return True
    for parent, child in ((path, other), (other, path)):
        if child.startswith(parent) and child[len(parent)] in ".[":
            return True
    return False


def _provenance(
    path: str,
    evidence: Sequence[Mapping[str, Any]],
    edited: Iterable[str],
) -> list[Form3500Provenance]:
    found: list[Form3500Provenance] = []
    for entry in evidence:
        paths = entry.get("field_paths") or []
        if any(isinstance(item, str) and _related(path, item) for item in paths):
            source_type = str(entry.get("source_type") or "") or None
            found.append(
                Form3500Provenance(
                    kind=_PROVENANCE_KINDS.get(source_type or "", "record"),
                    source_type=source_type,
                    attribution=entry.get("attribution"),
                    citation=entry.get("citation"),
                )
            )
    if any(_related(path, item) for item in edited):
        found.append(Form3500Provenance(kind="clinician_edited", attribution="Clinician edited"))
    return found


def _checked(value: Any, checked_when: str | bool | None) -> bool:
    if isinstance(value, list):
        return checked_when in value
    if isinstance(checked_when, bool):
        return value is checked_when
    return value is not None and value == checked_when


def _display(entries: Sequence[FieldEntry], value: Any) -> tuple[str, str | None]:
    """(item label, value as the form shows it, or ``None`` when blank)."""
    first = entries[0]
    if first.kind == "checkbox":
        label = first.label.split(": ", 1)[0]
        chosen = [
            entry.label.split(": ", 1)[1] if ": " in entry.label else "Yes"
            for entry in entries
            if _checked(value, entry.checked_when)
        ]
        return label, "; ".join(chosen) or None
    if value is None or value == "":
        return first.label, None
    if first.kind == "date":
        return first.label, fda_date(str(value))
    return first.label, str(value)


def _grouped(form: MedWatchFormDataV2) -> list[list[FieldEntry]]:
    """``FIELD_MAP`` entries grouped by model path, in form order, for the rows present."""
    test_rows = max(1, len(form.section_b.tests))
    other_rows = max(1, len(form.section_f.others))
    groups: dict[str, list[FieldEntry]] = {}
    for entry in FIELD_MAP:
        path = entry.model_path
        if path.startswith("section_d.product_2") and form.section_d.product_2 is None:
            continue
        if path.startswith("section_b.tests[") and int(path[16:].split("]")[0]) >= test_rows:
            continue
        if path.startswith("section_f.others[") and int(path[17:].split("]")[0]) >= other_rows:
            continue
        groups.setdefault(path, []).append(entry)
    return list(groups.values())


def template_read(today: date | None = None) -> Form3500TemplateRead:
    record = load_template_record()
    expires = date.fromisoformat(str(record["expires"]))
    return Form3500TemplateRead(
        title=str(record["title"]),
        revision=str(record["revision"]),
        omb_number=str(record["omb_number"]),
        expires=expires.isoformat(),
        may_be_superseded=(today or clinic_today()) > expires,
    )


def build_preview(
    form: MedWatchFormDataV2,
    *,
    draft: Mapping[str, Any],
    missing: Sequence[MedWatchGateIssue],
    warnings: Sequence[MedWatchNameWarning],
    current_submission: MedWatchExternalSubmissionRead | None,
    today: date | None = None,
) -> Form3500PreviewRead:
    """The Form 3500 preview of one draft; values are display text, never inputs."""
    evidence = [
        entry
        for entry in cast(list[Any], draft.get("source_evidence") or [])
        if isinstance(entry, Mapping)
    ]
    edited = [str(item) for item in cast(list[Any], draft.get("clinician_edited_fields") or [])]
    missing_by_path: dict[str, list[Any]] = {}
    for issue in missing:
        missing_by_path.setdefault(issue.path, []).append(issue.code)
    items: dict[str, list[Form3500PreviewItem]] = {letter: [] for letter, _ in SECTION_TITLES}
    for entries in _grouped(form):
        first = entries[0]
        label, value = _display(entries, model_value(form, first.model_path))
        items[first.item[0]].append(
            Form3500PreviewItem(
                item=first.item,
                label=label,
                path=first.model_path,
                value=value,
                provenance=_provenance(first.model_path, evidence, edited),
                missing_for_approval=missing_by_path.get(first.model_path, []),
            )
        )
    sections = [
        Form3500PreviewSection(
            section=letter,
            title=title,
            completion="not_completed_by_mediagent"
            if letter in NOT_COMPLETED_SECTIONS
            else "mediagent",
            items=items[letter],
        )
        for letter, title in SECTION_TITLES
    ]
    return Form3500PreviewRead(
        draft_id=str(draft["id"]),
        status=str(draft.get("status") or "draft"),
        revision=int(draft.get("revision") or 1),
        export_version=str(draft.get("export_version") or ""),
        discarded=draft.get("discarded_at") is not None,
        sections=sections,
        missing_for_approval=list(missing),
        name_warnings=list(warnings),
        mediagent_review=form.mediagent_review,
        legacy=dict(form.legacy),
        template=template_read(today),
        current_submission=current_submission,
    )


def _options(labels: Mapping[str, str]) -> list[Form3500Option]:
    return [Form3500Option(value=value, label=label) for value, label in labels.items()]


def _literal_options(literal: Any) -> list[Form3500Option]:
    return [Form3500Option(value=value, label=value) for value in get_args(literal)]


def form_options() -> Form3500OptionsRead:
    """Option lists for the edit form, equal to the model's and the template's lists."""
    record = load_template_record()
    countries = [
        Form3500Option(value=str(display), label=str(display))
        for _export, display in cast(list[list[str]], record["choice_options"][_COUNTRY_FIELD])
        if str(display).strip()
    ]
    return Form3500OptionsRead(
        sex=_options(SEX_LABELS),
        age_unit=_options(AGE_UNIT_LABELS),
        weight_unit=_options(WEIGHT_UNIT_LABELS),
        race=_options(RACE_LABELS),
        report_types=_options(REPORT_TYPE_LABELS),
        outcomes=_options(OUTCOME_LABELS),
        yes_no=_options({key: YES_NO_LABELS[key] for key in ("yes", "no")}),
        yes_no_not_applicable=_options(YES_NO_LABELS),
        product_types=_options(PRODUCT_TYPE_LABELS),
        dose_units=_literal_options(DoseUnit),
        frequencies=_literal_options(Frequency),
        routes=_literal_options(Route),
        duration_units=_literal_options(DurationUnit),
        occupations=_literal_options(Occupation),
        also_reported_to=_options(ALSO_REPORTED_TO_LABELS),
        countries=countries,
        submission_methods=_options(SUBMISSION_METHOD_LABELS),
    )
