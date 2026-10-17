"""Clinician-controlled Form FDA 3500 drafts: prepare, preview, approve, export, discard.

MediAgent prepares the form and the clinician submits it. No code path here sends anything
to FDA; a submission is only ever recorded as something the clinician did outside MediAgent.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, cast
from uuid import UUID, uuid4

from postgrest.exceptions import APIError
from supabase import Client

from app.core import authorization_reasons as reasons
from app.core.exceptions import (
    AuthorizationError,
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
from app.db.repositories import CareTeamRepository
from app.db.supabase_execute import execute_async
from app.models.adr import (
    MEDWATCH_APPROVAL_ATTESTATION_VERSION,
    MEDWATCH_APPROVAL_ATTESTATIONS,
    MedWatchDraftApprovalRequest,
    MedWatchDraftCreateRequest,
    MedWatchDraftDiscardRequest,
    MedWatchDraftUpdateRequest,
    MedWatchSubmissionAmendRequest,
    MedWatchSubmissionRecordRequest,
)
from app.models.enums import ADRStatus, MedWatchStatus
from app.models.medwatch_form_3500 import (
    FORM_3500_VERSION,
    MAX_OTHER_PRODUCTS,
    Form3500OptionsRead,
    Form3500PreviewRead,
    MedWatchExternalSubmissionRead,
    MedWatchFormDataV2,
    MedWatchGateIssue,
    MedWatchListState,
)
from app.pharmacovigilance import NaranjoQuestion
from app.services.medwatch_3500.dates import (
    clinic_date_of,
    clinic_today,
    coerce_date,
    earliest_day,
)
from app.services.medwatch_3500.field_map import FIELD_MAP_NAMES
from app.services.medwatch_3500.gate import GateContext, approval_issues
from app.services.medwatch_3500.identifier import (
    NameSources,
    PatientIdentity,
    default_code,
    identifier_violations,
    name_warnings,
)
from app.services.medwatch_3500.legacy import (
    match_frequency,
    match_route,
    past_date,
    split_dose,
    upgrade_legacy_form,
)
from app.services.medwatch_3500.pdf import render_form_3500
from app.services.medwatch_3500.preview import build_preview, form_options, template_read
from app.services.medwatch_3500.template import load_template

# Error codes the clinician portal maps to its own copy (server text is never shown).
ADR_REVIEW_COMPLETED = "ADR_REVIEW_ALREADY_COMPLETED"
MEDWATCH_DRAFT_EXISTS = "MEDWATCH_DRAFT_EXISTS"
MEDWATCH_DRAFT_NOT_EDITABLE = "MEDWATCH_DRAFT_NOT_EDITABLE"
MEDWATCH_DRAFT_DISCARDED = "MEDWATCH_DRAFT_DISCARDED"
MEDWATCH_DRAFT_SUBMITTED = "MEDWATCH_DRAFT_SUBMITTED"
MEDWATCH_NOT_APPROVED = "MEDWATCH_NOT_APPROVED"
MEDWATCH_NOT_SUBMITTED = "MEDWATCH_NOT_SUBMITTED"
MEDWATCH_REVIEW_FIELDS_LOCKED = "MEDWATCH_REVIEW_FIELDS_LOCKED"
MEDWATCH_IDENTIFIER_IDENTIFIES = "MEDWATCH_IDENTIFIER_IDENTIFIES"
MEDWATCH_APPROVAL_INCOMPLETE = "MEDWATCH_APPROVAL_INCOMPLETE"
MEDWATCH_WARNINGS_NOT_ACKNOWLEDGED = "MEDWATCH_WARNINGS_NOT_ACKNOWLEDGED"
MEDWATCH_LEGACY_DRAFT_INCOMPLETE = "MEDWATCH_LEGACY_DRAFT_INCOMPLETE"
MEDWATCH_SUBMISSION_INVALID = "MEDWATCH_SUBMISSION_INVALID"
MEDWATCH_REVISION_CONFLICT = "MEDWATCH_REVISION_CONFLICT"
MEDWATCH_SUBMISSION_CONFLICT = "MEDWATCH_SUBMISSION_CONFLICT"
MEDWATCH_INVALID_STATE = "MEDWATCH_INVALID_STATE"
MEDWATCH_INVALID_REQUEST = "MEDWATCH_INVALID_REQUEST"

_NARRATIVE_MAX = 4000
_HISTORY_MAX = 2000
_NAME_MAX = 255
_REPORTER_NAME_MAX = 100

# Naranjo questions that answer Section D items 7 and 8.
_DECHALLENGE_ITEMS = (
    (NaranjoQuestion.IMPROVED_ON_DECHALLENGE, "abated"),
    (NaranjoQuestion.REAPPEARED_ON_RECHALLENGE, "reappeared"),
)


@dataclass(frozen=True)
class Form3500Sources:
    """Stored records a Form 3500 draft is prepared from. Nothing else is consulted."""

    draft_id: UUID
    assessment: Mapping[str, Any]
    patient: Mapping[str, Any]
    symptom: Mapping[str, Any]
    medication: Mapping[str, Any]
    clinician: Mapping[str, Any]
    medications: Sequence[Mapping[str, Any]] = ()
    conditions: Sequence[Mapping[str, Any]] = ()
    allergies: Sequence[Mapping[str, Any]] = ()
    # Approved clinical facts are accepted but never prefill B6: an ``observation`` fact
    # does not record its FHIR category, so a laboratory result cannot be told apart from
    # a vital sign or survey answer.
    clinical_facts: Sequence[Mapping[str, Any]] = ()
    rationale: str = ""
    today: date | None = None


def patient_identity(patient: Mapping[str, Any]) -> PatientIdentity:
    """The patient facts the A1 identifier and free text must not reveal."""
    return PatientIdentity(
        first_name=str(patient.get("first_name") or ""),
        last_name=str(patient.get("last_name") or ""),
        email=str(patient.get("email") or ""),
        date_of_birth=coerce_date(patient.get("date_of_birth")),
    )


def _text(record: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _fit(value: str, limit: int, legacy: dict[str, str], key: str) -> str:
    """Keep text within an item's length; the full text goes to ``legacy`` when cut."""
    if len(value) <= limit:
        return value
    legacy[key] = value
    return value[:limit]


def _evidence_source_type(entry: Mapping[str, Any]) -> tuple[str, str]:
    """(source type, attribution) by the evidence entry's own ``source``."""
    source = entry.get("source")
    if source == "patient_follow_up":
        return "patient_confirmed_adr_evidence", "Patient-confirmed follow-up answer"
    if not source:
        return "ai_extracted_adr_evidence", "AI-extracted from the patient's report"
    return "adr_assessment_evidence", f"Recorded ADR evidence ({source})"


class _Evidence:
    """One evidence entry per filled field path and source."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def add(
        self,
        path: str,
        source_type: str,
        source_id: object,
        attribution: str,
        citation: str,
        excerpt: str | None = None,
    ) -> None:
        self.entries.append(
            {
                "field_paths": [path],
                "source_type": source_type,
                "source_id": str(source_id) if source_id else None,
                "attribution": attribution,
                "excerpt": excerpt or None,
                "citation": citation,
            }
        )


def build_form_3500(sources: Form3500Sources) -> tuple[MedWatchFormDataV2, list[dict[str, Any]]]:
    """Prefill a Form 3500 draft from stored records, with evidence for every filled item.

    Items without a stored source stay blank: race, ethnicity, weight, outcomes, B4, B6
    rows (see ``Form3500Sources.clinical_facts``), product identifiers, reporter phone,
    address, health-professional answer and occupation, and sex for any gender other than
    female or male. Reporter identity goes only into Section G.
    """
    today = sources.today or clinic_today()
    patient, symptom = sources.patient, sources.symptom
    assessment, clinician = sources.assessment, sources.clinician
    patient_ref, symptom_ref = (
        f"patients/{patient.get('id')}",
        f"symptom_reports/{symptom.get('id')}",
    )
    assessment_ref = f"adr_assessments/{assessment.get('id')}"
    evidence = _Evidence()
    legacy: dict[str, str] = {}

    identity = patient_identity(patient)
    identifier = default_code(identity.first_name, identity.last_name, sources.draft_id, identity)
    evidence.add(
        "section_a.identifier",
        "default_patient_code",
        sources.draft_id,
        "Default code: patient initials and a draft reference",
        f"medwatch_drafts/{sources.draft_id}",
    )
    section_a: dict[str, Any] = {"identifier": identifier}
    date_of_birth = past_date(patient.get("date_of_birth"), today)
    if date_of_birth:
        section_a["date_of_birth"] = date_of_birth
        evidence.add(
            "section_a.date_of_birth",
            "patient_profile",
            patient.get("id"),
            "Patient account profile",
            patient_ref,
        )
    sex = {"female": "F", "male": "M"}.get(_text(patient, "gender"))
    if sex:
        section_a["sex"] = sex
        evidence.add(
            "section_a.sex",
            "patient_profile",
            patient.get("id"),
            "Patient account profile",
            patient_ref,
        )

    section_b: dict[str, Any] = {"report_types": ["adverse_event"], "event_date_confirmed": False}
    evidence.add(
        "section_b.report_types",
        "deterministic_adr_assessment",
        assessment.get("id"),
        "Adverse drug reaction assessment",
        assessment_ref,
    )
    onset = _text(symptom, "onset")
    event_date = past_date(onset, today)
    if event_date:
        excerpt, basis = onset, "Best estimate, confirm: patient-reported onset"
    else:
        reported = clinic_date_of(symptom.get("created_at"))
        event_date = past_date(reported, today) if reported else None
        excerpt = onset or _text(symptom, "created_at")
        basis = "Best estimate, confirm: date the symptom was reported"
    if event_date:
        section_b["event_date"] = event_date
        evidence.add(
            "section_b.event_date",
            "patient_symptom_report",
            symptom.get("id"),
            basis,
            symptom_ref,
            excerpt,
        )

    narrative = _text(symptom, "symptom")
    if symptom.get("severity") is not None:
        narrative = f"{narrative} (patient-reported severity {symptom['severity']}/10)"
    if _text(symptom, "notes"):
        narrative = f"{narrative}. {_text(symptom, 'notes')}"
    if narrative:
        section_b["narrative"] = _fit(narrative, _NARRATIVE_MAX, legacy, "symptom_report.narrative")
        evidence.add(
            "section_b.narrative",
            "patient_symptom_report",
            symptom.get("id"),
            "Patient-reported symptom",
            symptom_ref,
            narrative,
        )

    history: list[str] = []
    condition_names = [
        _text(item, "name")
        for item in sources.conditions
        if _text(item, "status") in {"", "active"}
    ]
    if any(condition_names):
        history.append("Conditions: " + "; ".join(name for name in condition_names if name) + ".")
        evidence.add(
            "section_b.other_history",
            "patient_condition_record",
            None,
            "Active conditions",
            f"{patient_ref}/conditions",
        )
    allergy_texts = [
        f"{_text(item, 'allergen')} ({_text(item, 'reaction')})"
        if _text(item, "reaction")
        else _text(item, "allergen")
        for item in sources.allergies
        if _text(item, "allergen")
    ]
    if allergy_texts:
        history.append("Allergies: " + "; ".join(allergy_texts) + ".")
        evidence.add(
            "section_b.other_history",
            "patient_allergy_record",
            None,
            "Recorded allergies and reactions",
            f"{patient_ref}/allergies",
        )
    if history:
        section_b["other_history"] = _fit(
            " ".join(history), _HISTORY_MAX, legacy, "patient.history"
        )

    product = _prefill_product(sources, today, evidence, legacy)
    others = _prefill_others(sources, today, evidence, legacy)

    section_g: dict[str, Any] = {}
    for key, path in (
        ("first_name", "section_g.first_name"),
        ("last_name", "section_g.last_name"),
        ("email", "section_g.email"),
    ):
        value = _text(clinician, key)
        limit = 254 if key == "email" else _REPORTER_NAME_MAX
        if value and len(value) <= limit:
            section_g[key] = value
            evidence.add(
                path,
                "authenticated_clinician",
                clinician.get("id"),
                "Authenticated clinician",
                f"clinicians/{clinician.get('id')}",
            )

    review: dict[str, Any] = {"reportability_rationale": sources.rationale.strip()}
    if sources.rationale.strip():
        evidence.add(
            "mediagent_review.reportability_rationale",
            "clinician_attestation",
            clinician.get("id"),
            "Authenticated clinician",
            f"clinicians/{clinician.get('id')}",
            sources.rationale.strip(),
        )
    if assessment.get("naranjo_score") is not None:
        review["naranjo_score"] = assessment["naranjo_score"]
        review["causality"] = assessment.get("causality")
        excerpt = f"Naranjo {assessment['naranjo_score']}: {assessment.get('causality')}"
        for path in ("mediagent_review.naranjo_score", "mediagent_review.causality"):
            evidence.add(
                path,
                "deterministic_adr_assessment",
                assessment.get("id"),
                "Naranjo decision support reviewed by clinician",
                assessment_ref,
                excerpt,
            )
    for entry in assessment.get("evidence") or []:
        excerpt = _text(entry, "evidence")
        if excerpt:
            source_type, attribution = _evidence_source_type(entry)
            question = _text(entry, "question")
            evidence.add(
                "mediagent_review.causality",
                source_type,
                entry.get("information_request_id"),
                f"{attribution}: {question}" if question else attribution,
                f"{assessment_ref}/evidence",
                excerpt,
            )
    for key in legacy:
        evidence.add(
            f"legacy.{key}", "prefill_overflow", None, "Source text with no Form 3500 item", key
        )

    form = MedWatchFormDataV2.model_validate(
        {
            "form_version": FORM_3500_VERSION,
            "section_a": section_a,
            "section_b": section_b,
            "section_d": {"product_1": product},
            "section_f": {"others": others},
            "section_g": section_g,
            "mediagent_review": review,
            "legacy": dict(sorted(legacy.items())),
        },
        context={"today": today},
    )
    return form, evidence.entries


def _prefill_product(
    sources: Form3500Sources, today: date, evidence: _Evidence, legacy: dict[str, str]
) -> dict[str, Any]:
    medication, assessment = sources.medication, sources.assessment
    medication_id = medication.get("id")
    document_id = medication.get("source_document_id")
    source_type = "document_grounded_medication" if document_id else "patient_medication_record"
    citation = f"documents/{document_id}" if document_id else f"medications/{medication_id}"
    instructions = _text(medication, "instructions") or None
    base = "section_d.product_1"
    product: dict[str, Any] = {}

    def record(field: str) -> None:
        evidence.add(
            f"{base}.{field}",
            source_type,
            medication_id,
            "Medication record",
            citation,
            instructions,
        )

    name = _text(medication, "name", "generic_name")
    if name:
        product["name"] = _fit(name, _NAME_MAX, legacy, "medication.name")
        record("name")
    elif _text(assessment, "suspect_medication_name"):
        product["name"] = _fit(
            _text(assessment, "suspect_medication_name"), _NAME_MAX, legacy, "medication.name"
        )
        evidence.add(
            f"{base}.name",
            "deterministic_adr_assessment",
            assessment.get("id"),
            "Suspect medication on the ADR assessment",
            f"adr_assessments/{assessment.get('id')}",
        )

    dosage = _text(medication, "dosage")
    dose = split_dose(dosage) if dosage else None
    if dose:
        product["dose"], product["dose_unit"] = dose
        record("dose")
        record("dose_unit")
    elif dosage:
        legacy["medication.dosage"] = dosage
    for key, matcher, other in (
        ("frequency", match_frequency, "frequency_other"),
        ("route", match_route, "route_other"),
    ):
        text = _text(medication, key)
        option, other_text = matcher(text)
        if option and len(other_text) <= 100:
            product[key], product[other] = option, other_text
            record(key)
            if other_text:
                record(other)
        elif text:
            legacy[f"medication.{key}"] = text

    start = past_date(medication.get("start_date"), today)
    stop = past_date(medication.get("end_date"), today)
    if stop and start and earliest_day(stop) < earliest_day(start):
        stop = None
    if start:
        product["therapy_start"] = start
        record("therapy_start")
    if stop:
        product["therapy_stop"] = stop
        record("therapy_stop")
    elif _text(medication, "end_date"):
        legacy["medication.end_date"] = _text(medication, "end_date")
    if medication.get("is_active") is True and not stop:
        product["ongoing"] = "yes"
        record("ongoing")

    answers = cast(Mapping[str, Any], assessment.get("naranjo_answers") or {})
    for question, field in _DECHALLENGE_ITEMS:
        answer = answers.get(question.value)
        if answer not in {"yes", "no"}:
            continue
        product[field] = answer
        entry = _latest_evidence(assessment, question.value)
        if entry is None:
            evidence.add(
                f"{base}.{field}",
                "deterministic_adr_assessment",
                assessment.get("id"),
                "Naranjo answer on the ADR assessment",
                f"adr_assessments/{assessment.get('id')}",
            )
        else:
            source_type_for_answer, attribution = _evidence_source_type(entry)
            evidence.add(
                f"{base}.{field}",
                source_type_for_answer,
                entry.get("information_request_id"),
                attribution,
                f"adr_assessments/{assessment.get('id')}/evidence",
                _text(entry, "evidence"),
            )
    return product


def _latest_evidence(assessment: Mapping[str, Any], question: str) -> Mapping[str, Any] | None:
    matches = [
        entry
        for entry in assessment.get("evidence") or []
        if isinstance(entry, Mapping) and entry.get("question") == question
    ]
    return matches[-1] if matches else None


def _prefill_others(
    sources: Form3500Sources, today: date, evidence: _Evidence, legacy: dict[str, str]
) -> list[dict[str, Any]]:
    suspect_id = str(sources.medication.get("id"))
    rows: list[dict[str, Any]] = []
    extra: list[str] = []
    for item in sources.medications:
        name = _text(item, "name", "generic_name")
        if not name or str(item.get("id")) == suspect_id:
            continue
        if len(rows) >= MAX_OTHER_PRODUCTS or len(name) > _NAME_MAX:
            extra.append(name)
            continue
        index = len(rows)
        path, citation = f"section_f.others[{index}]", f"medications/{item.get('id')}"
        row: dict[str, Any] = {"name": name}
        start = past_date(item.get("start_date"), today)
        end = past_date(item.get("end_date"), today)
        if end and start and earliest_day(end) < earliest_day(start):
            end = None
        fields = ["name"]
        if start:
            row["start"] = start
            fields.append("start")
        if end:
            row["end"] = end
            fields.append("end")
        for field in fields:
            evidence.add(
                f"{path}.{field}",
                "patient_medication_record",
                item.get("id"),
                "Other active medication",
                citation,
            )
        rows.append(row)
    if extra:
        legacy["medications.additional"] = "; ".join(extra)
    return rows


@dataclass(frozen=True)
class _ReadContext:
    """Records the read model needs beyond the draft rows, loaded once per request."""

    patients: Mapping[str, Mapping[str, Any]]
    assigned: Mapping[str, Sequence[Mapping[str, Any]]]
    clinicians: Mapping[str, Mapping[str, Any]]
    clinic_names: Mapping[str, str]
    submissions: Mapping[str, Sequence[Mapping[str, Any]]]

    def identity(self, draft: Mapping[str, Any]) -> PatientIdentity:
        return patient_identity(self.patients.get(str(draft.get("patient_id")), {}))

    def names(self, draft: Mapping[str, Any], form: MedWatchFormDataV2) -> NameSources:
        """Patient, reporter and assigned-clinician names and their clinic names."""
        patient = self.patients.get(str(draft.get("patient_id")), {})
        people: list[tuple[str, str]] = [(form.section_g.first_name, form.section_g.last_name)]
        clinics: list[str] = []
        for team in self.assigned.get(str(draft.get("patient_id")), []):
            clinician = self.clinicians.get(str(team.get("clinician_id")), {})
            people.append((_text(clinician, "first_name"), _text(clinician, "last_name")))
            clinics.extend(
                name
                for name in (
                    _text(team, "clinic_name"),
                    _text(clinician, "clinic_name"),
                    self.clinic_names.get(str(clinician.get("clinic_id")), ""),
                )
                if name
            )
        return NameSources(
            patient_names=[(_text(patient, "first_name"), _text(patient, "last_name"))],
            clinician_names=people,
            clinic_names=tuple(dict.fromkeys(clinics)),
        )

    def history(self, draft_id: object) -> list[MedWatchExternalSubmissionRead]:
        """Submission records of one draft, newest first."""
        rows = self.submissions.get(str(draft_id), [])
        return [_submission_read(row, self.clinicians) for row in rows]


def _submission_read(
    row: Mapping[str, Any], clinicians: Mapping[str, Mapping[str, Any]]
) -> MedWatchExternalSubmissionRead:
    recorder = clinicians.get(str(row.get("recorded_by")), {})
    name = " ".join(
        part for part in (_text(recorder, "first_name"), _text(recorder, "last_name")) if part
    )
    return MedWatchExternalSubmissionRead(
        id=str(row["id"]),
        submitted_on=str(row["submitted_on"]),
        method=row["method"],
        method_detail=row.get("method_detail"),
        fda_reference=row.get("fda_reference"),
        recorded_by=str(row["recorded_by"]),
        recorded_by_name=name or None,
        amends_id=str(row["amends_id"]) if row.get("amends_id") else None,
        amend_reason=row.get("amend_reason"),
        created_at=str(row["created_at"]),
    )


def current_submission(
    history: Sequence[MedWatchExternalSubmissionRead],
) -> MedWatchExternalSubmissionRead | None:
    """The newest record that no other record amends."""
    amended = {item.amends_id for item in history if item.amends_id}
    current = [item for item in history if item.id not in amended]
    return max(current, key=lambda item: item.created_at) if current else None


def _is_discarded(draft: Mapping[str, Any]) -> bool:
    return draft.get("discarded_at") is not None


def _is_exportable(draft: Mapping[str, Any]) -> bool:
    """Approved (``reviewed`` with ``approved_at``) or submitted, and not discarded."""
    status = draft.get("status")
    approved = status == MedWatchStatus.REVIEWED.value and bool(draft.get("approved_at"))
    return not _is_discarded(draft) and (approved or status == MedWatchStatus.SUBMITTED.value)


def export_filename(draft_id: UUID, extension: str) -> str:
    """``fda-3500-<first 8 of the draft ID>-not-submitted.<ext>``: never a patient name."""
    return f"fda-3500-{str(draft_id)[:8]}-not-submitted.{extension}"


def _attestation() -> dict[str, str]:
    return {
        "version": MEDWATCH_APPROVAL_ATTESTATION_VERSION,
        "text": MEDWATCH_APPROVAL_ATTESTATIONS[MEDWATCH_APPROVAL_ATTESTATION_VERSION],
    }


def _issues_payload(issues: Sequence[MedWatchGateIssue]) -> list[dict[str, str]]:
    return [issue.model_dump() for issue in issues]


_DRAFT_COLUMNS = (
    "id",
    "adr_assessment_id",
    "patient_id",
    "source_evidence",
    "clinician_edited_fields",
    "de_identified",
    "status",
    "patient_reference",
    "created_by",
    "approved_by",
    "approved_at",
    "approval_note",
    "submitted_at",
    "discarded_at",
    "discarded_by",
    "discard_reason",
    "revision",
    "export_version",
    "created_at",
    "updated_at",
)


class MedWatchService:
    """Prepare, preview and export Form FDA 3500 drafts. Nothing is ever sent to FDA.

    Form values, free text and the PDF are never logged.
    """

    def __init__(self, db: Client) -> None:
        self.db = db
        self.care_team_repo = CareTeamRepository(self)

    # ── Create, list, read ───────────────────────────────────────────────

    async def create_draft(
        self,
        clinician_id: UUID,
        assessment_id: UUID,
        request: MedWatchDraftCreateRequest,
    ) -> dict[str, Any]:
        """Prepare a Form 3500 draft from stored records and atomically complete ADR review."""
        assessment = await self._get_assessment(assessment_id)
        patient_id = UUID(str(assessment["patient_id"]))
        await self._assert_assignment(clinician_id, patient_id)
        if assessment.get("status") != ADRStatus.DRAFT.value:
            raise ValidationError(
                "ADR assessment review has already been completed", code=ADR_REVIEW_COMPLETED
            )

        existing = await self._execute(
            self.db.table("medwatch_drafts")
            .select("id")
            .eq("adr_assessment_id", str(assessment_id))
            .is_("discarded_at", "null")
            .limit(1)
        )
        if existing.data:
            raise ValidationError(
                "A MedWatch draft already exists for this assessment", code=MEDWATCH_DRAFT_EXISTS
            )

        draft_id = uuid4()
        sources = await self._load_sources(
            draft_id=draft_id,
            clinician_id=clinician_id,
            patient_id=patient_id,
            assessment=assessment,
            rationale=request.reportability_rationale,
        )
        form, source_evidence = build_form_3500(sources)
        row = await self._rpc(
            "create_medwatch_draft",
            {
                "p_assessment_id": str(assessment_id),
                "p_actor_id": str(clinician_id),
                "p_form_data": form.model_dump(mode="json"),
                "p_source_evidence": source_evidence,
                "p_reportability_rationale": request.reportability_rationale,
                "p_draft_id": str(draft_id),
            },
            failure="MedWatch draft could not be created",
            resource=("ADR assessment", assessment_id),
        )
        return (await self._read_models([row]))[0]

    async def list_drafts(
        self, clinician_id: UUID, state: MedWatchListState = "active"
    ) -> dict[str, Any]:
        """List drafts for currently assigned patients: active, submitted or discarded."""
        assignments = await self.care_team_repo.list_assigned_patient_ids(str(clinician_id))
        patient_ids = [str(row["patient_id"]) for row in assignments if row.get("patient_id")]
        if not patient_ids:
            return {"items": [], "total": 0}
        query = self.db.table("medwatch_drafts").select("*").in_("patient_id", patient_ids)
        if state == "submitted":
            query = query.eq("status", MedWatchStatus.SUBMITTED.value)
        elif state in ("draft", "approved"):
            status = MedWatchStatus.DRAFT if state == "draft" else MedWatchStatus.REVIEWED
            query = query.eq("status", status.value).is_("discarded_at", "null")
        elif state == "discarded":
            query = query.not_.is_("discarded_at", "null")
        else:
            query = query.in_(
                "status", [MedWatchStatus.DRAFT.value, MedWatchStatus.REVIEWED.value]
            ).is_("discarded_at", "null")
        result = await self._execute(query.order("created_at", desc=True))
        items = await self._read_models(cast(list[dict[str, Any]], result.data or []))
        return {"items": items, "total": len(items)}

    async def get_draft(self, clinician_id: UUID, draft_id: UUID) -> dict[str, Any]:
        """One draft, readable by exactly the clinicians who can list it.

        An unknown id and an unassigned one are indistinguishable (the same 404).
        """
        draft = await self._get_readable_draft(clinician_id, draft_id)
        return (await self._read_models([draft]))[0]

    async def preview_pdf(self, clinician_id: UUID, draft_id: UUID) -> dict[str, Any]:
        """The filled Form 3500 stamped as a draft. Not an export: nothing is recorded."""
        draft = await self._get_readable_draft(clinician_id, draft_id)
        context = await self._context([draft])
        form, _upgraded = self._form(draft, context)
        if form.section_b.report_date is None and draft.get("approved_at"):
            form.section_b.report_date = clinic_date_of(draft["approved_at"])
        content = await asyncio.to_thread(render_form_3500, form, draft_id, watermark=True)
        return {
            "filename": f"fda-3500-{str(draft_id)[:8]}-draft-preview.pdf",
            "media_type": "application/pdf",
            "content": content,
        }

    async def get_preview(self, clinician_id: UUID, draft_id: UUID) -> Form3500PreviewRead:
        """The read-only Form 3500 layout of a draft in any status."""
        draft = await self._get_authorized_draft(clinician_id, draft_id)
        context = await self._context([draft])
        form, _upgraded = self._form(draft, context)
        history = context.history(draft["id"])
        return build_preview(
            form,
            draft=draft,
            missing=self._missing(draft, form, context),
            warnings=name_warnings(form, context.names(draft, form)),
            current_submission=current_submission(history),
        )

    @staticmethod
    def form_options() -> Form3500OptionsRead:
        """Option lists for the edit form."""
        return form_options()

    # ── Edit and approve ─────────────────────────────────────────────────

    async def update_draft(
        self,
        clinician_id: UUID,
        draft_id: UUID,
        request: MedWatchDraftUpdateRequest,
    ) -> dict[str, Any]:
        """Save a full Form 3500 draft with optimistic locking and field-level audit."""
        draft = await self._get_authorized_draft(clinician_id, draft_id)
        self._assert_editable(draft)
        context = await self._context([draft])
        current, upgraded = self._form(draft, context)
        submitted = request.form_data
        if (
            submitted.mediagent_review.naranjo_score != current.mediagent_review.naranjo_score
            or submitted.mediagent_review.causality != current.mediagent_review.causality
        ):
            raise ValidationError(
                "Naranjo score and causality must come from the reviewed ADR assessment",
                code=MEDWATCH_REVIEW_FIELDS_LOCKED,
            )
        if submitted.section_a.identifier.strip() and identifier_violations(
            submitted.section_a.identifier, context.identity(draft)
        ):
            raise ValidationError(
                "The patient identifier must not contain the patient's name, email or date "
                "of birth",
                code=MEDWATCH_IDENTIFIER_IDENTIFIES,
                details={"path": "section_a.identifier"},
            )
        # Text kept from a 048 draft is read-only.
        updated = submitted.model_copy(update={"legacy": dict(current.legacy)})
        previous_payload = current.model_dump(mode="json")
        updated_payload = updated.model_dump(mode="json")
        changed_fields = self._changed_leaf_paths(previous_payload, updated_payload)
        if not changed_fields and not upgraded:
            return (await self._read_models([draft], context))[0]

        row = await self._rpc(
            "update_medwatch_draft",
            {
                "p_draft_id": str(draft_id),
                "p_actor_id": str(clinician_id),
                "p_form_data": updated_payload,
                "p_changed_fields": changed_fields,
                "p_expected_revision": request.expected_revision,
            },
            failure="MedWatch draft could not be saved",
            resource=("MedWatch draft", draft_id),
        )
        return (await self._read_models([row], context))[0]

    async def approve_draft(
        self,
        clinician_id: UUID,
        draft_id: UUID,
        request: MedWatchDraftApprovalRequest,
    ) -> dict[str, Any]:
        """Approve the stored revision once the Form 3500 gate passes and warnings are seen."""
        draft = await self._get_authorized_draft(clinician_id, draft_id)
        if _is_discarded(draft):
            raise ValidationError(
                "Discarded MedWatch drafts cannot be approved", code=MEDWATCH_DRAFT_DISCARDED
            )
        if draft.get("status") != MedWatchStatus.DRAFT.value:
            raise ValidationError(
                "MedWatch draft has already been approved", code=MEDWATCH_DRAFT_NOT_EDITABLE
            )
        if int(draft.get("revision") or 0) != request.expected_revision:
            raise ConflictError(
                "MedWatch draft changed; refresh before approval", code=MEDWATCH_REVISION_CONFLICT
            )
        context = await self._context([draft])
        form, upgraded = self._form(draft, context)
        issues = approval_issues(
            form,
            GateContext(
                patient=context.identity(draft),
                non_serious_attested=request.non_serious_attested,
            ),
        )
        if issues:
            raise ValidationError(
                "Complete the items Form 3500 needs before approval",
                code=MEDWATCH_APPROVAL_INCOMPLETE,
                details={"missing_for_approval": _issues_payload(issues)},
            )
        if upgraded:
            raise ValidationError(
                "Save this draft as Form 3500 before approval",
                code=MEDWATCH_LEGACY_DRAFT_INCOMPLETE,
            )
        warnings = name_warnings(form, context.names(draft, form))
        if set(request.acknowledged_warnings) != set(warnings):
            raise ValidationError(
                "Review the name warnings before approval",
                code=MEDWATCH_WARNINGS_NOT_ACKNOWLEDGED,
                details={"name_warnings": [warning.model_dump() for warning in warnings]},
            )

        row = await self._rpc(
            "approve_medwatch_draft",
            {
                "p_draft_id": str(draft_id),
                "p_actor_id": str(clinician_id),
                "p_approval_note": request.approval_note,
                "p_expected_revision": request.expected_revision,
                "p_approval": {
                    "attestation_version": request.attestation_version,
                    "non_serious_attested": request.non_serious_attested,
                    "acknowledged_warnings": [warning.model_dump() for warning in warnings],
                },
            },
            failure="MedWatch draft could not be approved",
            resource=("MedWatch draft", draft_id),
        )
        return (await self._read_models([row], context))[0]

    # ── Export ───────────────────────────────────────────────────────────

    async def export_draft(self, clinician_id: UUID, draft_id: UUID) -> dict[str, Any]:
        """Record and return the approved Form 3500 JSON artifact; never file it externally."""
        draft = await self._get_authorized_draft(clinician_id, draft_id)
        self._assert_exportable(draft)
        context = await self._context([draft])
        form, _upgraded = self._form(draft, context)
        exported = await self._rpc(
            "record_medwatch_draft_export",
            {
                "p_draft_id": str(draft_id),
                "p_actor_id": str(clinician_id),
                "p_format": "json",
                "p_template_revision": None,
                "p_template_sha256": None,
            },
            failure="MedWatch draft export could not be recorded",
            resource=("MedWatch draft", draft_id),
        )
        submission = current_submission(context.history(draft_id))
        return {
            "filename": export_filename(draft_id, "json"),
            "media_type": "application/json",
            "content": {
                "artifact_type": "fda_3500_draft",
                "form_version": FORM_3500_VERSION,
                "export_version": exported["export_version"],
                "not_submitted_to_fda": True,
                "draft_id": str(draft_id),
                "adr_assessment_id": exported["adr_assessment_id"],
                "revision": exported["revision"],
                "approval": {
                    "approved_by": exported["approved_by"],
                    "approved_at": exported["approved_at"],
                    "approval_note": exported["approval_note"],
                },
                "form_data": form.model_dump(mode="json"),
                "source_evidence": exported.get("source_evidence") or [],
                "clinician_edited_fields": exported.get("clinician_edited_fields") or [],
                "submission_recorded_outside_mediagent": (
                    submission.model_dump(mode="json") if submission else None
                ),
            },
        }

    async def export_pdf(self, clinician_id: UUID, draft_id: UUID) -> dict[str, Any]:
        """Fill the official Form 3500 and return it only after the export is audited."""
        draft = await self._get_authorized_draft(clinician_id, draft_id)
        self._assert_exportable(draft)
        context = await self._context([draft])
        form, upgraded = self._form(draft, context)
        if upgraded and approval_issues(form, GateContext(patient=context.identity(draft))):
            raise ValidationError(
                "This draft predates Form 3500 and is incomplete. Discard it and prepare a "
                "new draft to download the PDF.",
                code=MEDWATCH_LEGACY_DRAFT_INCOMPLETE,
            )
        if form.section_b.report_date is None and draft.get("approved_at"):
            form.section_b.report_date = clinic_date_of(draft["approved_at"])
        # A mismatched template (503) or a failed fill (502) records no export.
        template = load_template(required_fields=FIELD_MAP_NAMES)
        content = await asyncio.to_thread(render_form_3500, form, draft_id)
        await self._rpc(
            "record_medwatch_draft_export",
            {
                "p_draft_id": str(draft_id),
                "p_actor_id": str(clinician_id),
                "p_format": "pdf",
                "p_template_revision": template.revision,
                "p_template_sha256": template.sha256,
            },
            failure="MedWatch draft export could not be recorded",
            resource=("MedWatch draft", draft_id),
        )
        return {
            "filename": export_filename(draft_id, "pdf"),
            "media_type": "application/pdf",
            "content": content,
        }

    # ── Discard and the external submission record ───────────────────────

    async def discard_draft(
        self, clinician_id: UUID, draft_id: UUID, request: MedWatchDraftDiscardRequest
    ) -> dict[str, Any]:
        """Discard a draft or an approved, unsubmitted one; its assessment returns to review."""
        draft = await self._get_authorized_draft(clinician_id, draft_id)
        if _is_discarded(draft):
            raise ValidationError(
                "MedWatch draft has already been discarded", code=MEDWATCH_DRAFT_DISCARDED
            )
        if draft.get("status") == MedWatchStatus.SUBMITTED.value:
            raise ValidationError(
                "A submitted MedWatch draft cannot be discarded", code=MEDWATCH_DRAFT_SUBMITTED
            )
        row = await self._rpc(
            "discard_medwatch_draft",
            {
                "p_draft_id": str(draft_id),
                "p_actor_id": str(clinician_id),
                "p_reason": request.reason,
                "p_expected_revision": request.expected_revision,
            },
            failure="MedWatch draft could not be discarded",
            resource=("MedWatch draft", draft_id),
        )
        return (await self._read_models([row]))[0]

    async def record_submission(
        self, clinician_id: UUID, draft_id: UUID, request: MedWatchSubmissionRecordRequest
    ) -> dict[str, Any]:
        """Record that the clinician submitted the approved form to FDA outside MediAgent."""
        draft = await self._get_authorized_draft(clinician_id, draft_id)
        if _is_discarded(draft):
            raise ValidationError(
                "Discarded MedWatch drafts cannot be submitted", code=MEDWATCH_DRAFT_DISCARDED
            )
        if draft.get("status") == MedWatchStatus.SUBMITTED.value:
            raise ValidationError(
                "A submission is already recorded for this draft", code=MEDWATCH_DRAFT_SUBMITTED
            )
        if not _is_exportable(draft):
            raise ValidationError(
                "Approve the draft before recording a submission", code=MEDWATCH_NOT_APPROVED
            )
        self._assert_after_approval(draft, request.submitted_on)
        row = await self._rpc(
            "record_medwatch_external_submission",
            {
                "p_draft_id": str(draft_id),
                "p_actor_id": str(clinician_id),
                "p_submitted_on": request.submitted_on.isoformat(),
                "p_method": request.method,
                "p_method_detail": request.method_detail,
                "p_fda_reference": request.fda_reference,
                "p_attested": request.attested,
                "p_expected_revision": request.expected_revision,
            },
            failure="The submission could not be recorded",
            resource=("MedWatch draft", draft_id),
        )
        return (await self._read_models([row]))[0]

    async def amend_submission(
        self, clinician_id: UUID, draft_id: UUID, request: MedWatchSubmissionAmendRequest
    ) -> dict[str, Any]:
        """Correct the current submission record; the original record is kept."""
        draft = await self._get_authorized_draft(clinician_id, draft_id)
        if draft.get("status") != MedWatchStatus.SUBMITTED.value:
            raise ValidationError(
                "Only a recorded submission can be amended", code=MEDWATCH_NOT_SUBMITTED
            )
        self._assert_after_approval(draft, request.submitted_on)
        row = await self._rpc(
            "amend_medwatch_external_submission",
            {
                "p_draft_id": str(draft_id),
                "p_actor_id": str(clinician_id),
                "p_amends_id": str(request.amends_id),
                "p_submitted_on": request.submitted_on.isoformat(),
                "p_method": request.method,
                "p_method_detail": request.method_detail,
                "p_fda_reference": request.fda_reference,
                "p_reason": request.reason,
            },
            failure="The submission amendment could not be recorded",
            resource=("MedWatch draft", draft_id),
            conflict=(
                "The submission record changed; refresh before amending",
                MEDWATCH_SUBMISSION_CONFLICT,
            ),
        )
        return (await self._read_models([row]))[0]

    # ── Read model ───────────────────────────────────────────────────────

    def _form(
        self, draft: Mapping[str, Any], context: _ReadContext
    ) -> tuple[MedWatchFormDataV2, bool]:
        """The stored form as Form 3500 v2, and whether it was upgraded from the 048 shape."""
        stored = draft.get("form_data")
        upgraded = not (
            isinstance(stored, Mapping) and stored.get("form_version") == FORM_3500_VERSION
        )
        data = upgrade_legacy_form(
            stored if isinstance(stored, Mapping) else None,
            draft_id=UUID(str(draft["id"])),
            patient=context.identity(draft),
        )
        return MedWatchFormDataV2.model_validate(data), upgraded

    @staticmethod
    def _missing(
        draft: Mapping[str, Any], form: MedWatchFormDataV2, context: _ReadContext
    ) -> list[MedWatchGateIssue]:
        """What blocks approval, while the draft can still be approved."""
        if _is_discarded(draft) or draft.get("status") != MedWatchStatus.DRAFT.value:
            return []
        return approval_issues(form, GateContext(patient=context.identity(draft)))

    async def _read_models(
        self,
        rows: Sequence[Mapping[str, Any]],
        context: _ReadContext | None = None,
    ) -> list[dict[str, Any]]:
        if not rows:
            return []
        context = context or await self._context(rows)
        template = template_read()
        items: list[dict[str, Any]] = []
        for row in rows:
            form, upgraded = self._form(row, context)
            history = context.history(row["id"])
            pdf_available = _is_exportable(row) and not (
                upgraded and approval_issues(form, GateContext(patient=context.identity(row)))
            )
            item = {key: row.get(key) for key in _DRAFT_COLUMNS}
            item.update(
                form_data=form.model_dump(mode="json"),
                upgraded_from_legacy=upgraded,
                missing_for_approval=_issues_payload(self._missing(row, form, context)),
                name_warnings=[
                    warning.model_dump()
                    for warning in name_warnings(form, context.names(row, form))
                ],
                pdf_available=pdf_available,
                current_submission=current_submission(history),
                submission_history=history,
                attestation=_attestation(),
                template=template,
            )
            items.append(item)
        return items

    async def _context(self, rows: Sequence[Mapping[str, Any]]) -> _ReadContext:
        patient_ids = sorted({str(row["patient_id"]) for row in rows})
        draft_ids = sorted({str(row["id"]) for row in rows})
        patients = await self._rows(
            self.db.table("patients")
            .select("id, first_name, last_name, email, date_of_birth")
            .in_("id", patient_ids)
        )
        teams = await self._rows(
            self.db.table("care_teams")
            .select("patient_id, clinician_id, clinic_name")
            .in_("patient_id", patient_ids)
            .eq("status", "active")
        )
        submissions = await self._rows(
            self.db.table("medwatch_external_submissions")
            .select("*")
            .in_("medwatch_draft_id", draft_ids)
            .order("created_at", desc=True)
        )
        clinician_ids = sorted(
            {str(team["clinician_id"]) for team in teams if team.get("clinician_id")}
            | {str(item["recorded_by"]) for item in submissions if item.get("recorded_by")}
        )
        clinicians = (
            await self._rows(
                self.db.table("clinicians")
                .select("id, first_name, last_name, clinic_name, clinic_id")
                .in_("id", clinician_ids)
            )
            if clinician_ids
            else []
        )
        clinic_ids = sorted({str(c["clinic_id"]) for c in clinicians if c.get("clinic_id")})
        clinics = (
            await self._rows(
                self.db.table("clinics").select("id, display_name").in_("id", clinic_ids)
            )
            if clinic_ids
            else []
        )
        assigned: dict[str, list[Mapping[str, Any]]] = {}
        for team in teams:
            assigned.setdefault(str(team.get("patient_id")), []).append(team)
        by_draft: dict[str, list[Mapping[str, Any]]] = {}
        for item in submissions:
            by_draft.setdefault(str(item.get("medwatch_draft_id")), []).append(item)
        return _ReadContext(
            patients={str(row["id"]): row for row in patients},
            assigned=assigned,
            clinicians={str(row["id"]): row for row in clinicians},
            clinic_names={
                str(row["id"]): _text(row, "display_name") for row in clinics if row.get("id")
            },
            submissions=by_draft,
        )

    # ── Loading and guards ───────────────────────────────────────────────

    async def _get_assessment(self, assessment_id: UUID) -> dict[str, Any]:
        rows = await self._rows(
            self.db.table("adr_assessments").select("*").eq("id", str(assessment_id)).limit(1)
        )
        if not rows:
            raise NotFoundError("ADR assessment", str(assessment_id))
        return dict(rows[0])

    async def _get_authorized_draft(self, clinician_id: UUID, draft_id: UUID) -> dict[str, Any]:
        rows = await self._rows(
            self.db.table("medwatch_drafts").select("*").eq("id", str(draft_id)).limit(1)
        )
        if not rows:
            raise NotFoundError("MedWatch draft", str(draft_id))
        draft = dict(rows[0])
        await self._assert_assignment(clinician_id, UUID(str(draft["patient_id"])))
        return draft

    async def _get_readable_draft(self, clinician_id: UUID, draft_id: UUID) -> dict[str, Any]:
        try:
            return await self._get_authorized_draft(clinician_id, draft_id)
        except AuthorizationError:
            raise NotFoundError("MedWatch draft", str(draft_id)) from None

    async def _load_sources(
        self,
        *,
        draft_id: UUID,
        clinician_id: UUID,
        patient_id: UUID,
        assessment: Mapping[str, Any],
        rationale: str,
    ) -> Form3500Sources:
        """Only stored records: patient, symptom, medications, conditions, allergies, reporter."""

        async def one(table: str, record_id: object, resource: str) -> Mapping[str, Any]:
            rows = await self._rows(
                self.db.table(table).select("*").eq("id", str(record_id)).limit(1)
            )
            if not rows:
                raise NotFoundError(resource, str(record_id))
            return rows[0]

        patient = await one("patients", patient_id, "Patient")
        symptom = await one("symptom_reports", assessment["symptom_report_id"], "Symptom report")
        medication = await one("medications", assessment["suspect_medication_id"], "Medication")
        clinician = await one("clinicians", clinician_id, "Clinician")
        medications = await self._rows(
            self.db.table("medications")
            .select("*")
            .eq("patient_id", str(patient_id))
            .eq("is_active", True)
        )
        conditions = await self._rows(
            self.db.table("conditions").select("*").eq("patient_id", str(patient_id))
        )
        allergies = await self._rows(
            self.db.table("allergies").select("*").eq("patient_id", str(patient_id))
        )
        return Form3500Sources(
            draft_id=draft_id,
            assessment=assessment,
            patient=patient,
            symptom=symptom,
            medication=medication,
            clinician=clinician,
            medications=medications,
            conditions=conditions,
            allergies=allergies,
            rationale=rationale,
        )

    @staticmethod
    def _assert_editable(draft: Mapping[str, Any]) -> None:
        if _is_discarded(draft):
            raise ValidationError(
                "Discarded MedWatch drafts cannot be edited", code=MEDWATCH_DRAFT_DISCARDED
            )
        if draft.get("status") == MedWatchStatus.SUBMITTED.value:
            raise ValidationError(
                "Submitted MedWatch drafts cannot be edited", code=MEDWATCH_DRAFT_SUBMITTED
            )
        if draft.get("status") != MedWatchStatus.DRAFT.value:
            raise ValidationError(
                "Approved MedWatch drafts cannot be edited", code=MEDWATCH_DRAFT_NOT_EDITABLE
            )

    @staticmethod
    def _assert_exportable(draft: Mapping[str, Any]) -> None:
        if _is_discarded(draft):
            raise ValidationError(
                "Discarded MedWatch drafts cannot be exported", code=MEDWATCH_DRAFT_DISCARDED
            )
        if not _is_exportable(draft):
            raise ValidationError(
                "Only approved MedWatch drafts can be exported", code=MEDWATCH_NOT_APPROVED
            )

    @staticmethod
    def _assert_after_approval(draft: Mapping[str, Any], submitted_on: date) -> None:
        approved_on = clinic_date_of(draft.get("approved_at"))
        if approved_on is None or submitted_on.isoformat() < approved_on:
            raise ValidationError(
                "The submission date cannot be before the approval date",
                code=MEDWATCH_SUBMISSION_INVALID,
            )

    @classmethod
    def _changed_leaf_paths(
        cls, previous: dict[str, Any], updated: dict[str, Any], prefix: str = ""
    ) -> list[str]:
        paths: list[str] = []
        for key in sorted(set(previous) | set(updated)):
            path = f"{prefix}.{key}" if prefix else key
            old_value = previous.get(key)
            new_value = updated.get(key)
            if isinstance(old_value, dict) and isinstance(new_value, dict):
                paths.extend(cls._changed_leaf_paths(old_value, new_value, path))
            elif old_value != new_value:
                paths.append(path)
        return paths

    async def _assert_assignment(self, clinician_id: UUID, patient_id: UUID) -> None:
        assignments = await self.care_team_repo.find_active_assignment(
            str(clinician_id), str(patient_id)
        )
        if not assignments:
            raise AuthorizationError(
                "You are not assigned to this patient",
                reason_code=reasons.NO_CARE_TEAM_ASSIGNMENT,
                actor_id=str(clinician_id),
                actor_role="clinician",
                target_type="patient",
                target_id=str(patient_id),
            )

    # ── Database access ──────────────────────────────────────────────────

    async def _rpc(
        self,
        name: str,
        params: dict[str, Any],
        *,
        failure: str,
        resource: tuple[str, UUID],
        conflict: tuple[str, str] = (
            "MedWatch draft changed; refresh and try again",
            MEDWATCH_REVISION_CONFLICT,
        ),
    ) -> dict[str, Any]:
        """Call a MedWatch RPC, mapping only its SQLSTATE; PostgREST detail is never shown."""
        try:
            result = await self._execute(self.db.rpc(name, params))
        except APIError as exc:
            raise _rpc_error(exc.code, failure, resource, conflict) from None
        rows = [row for row in cast(list[Any], result.data or []) if isinstance(row, dict)]
        if not rows:
            raise ExternalServiceError("Supabase", failure)
        return cast(dict[str, Any], rows[0])

    async def _rows(self, query: Any) -> list[Mapping[str, Any]]:
        result = await self._execute(query)
        return [row for row in cast(list[Any], result.data or []) if isinstance(row, Mapping)]

    async def _execute(self, query: Any) -> Any:
        return await execute_async(self, lambda _db: query, operation="MedWatch workflow")


def _rpc_error(
    code: str | None,
    failure: str,
    resource: tuple[str, UUID],
    conflict: tuple[str, str],
) -> Exception:
    if code == "P0002":
        return NotFoundError(resource[0], str(resource[1]))
    if code == "42501":
        return AuthorizationError(
            "You are not assigned to this patient",
            reason_code=reasons.NO_CARE_TEAM_ASSIGNMENT,
            actor_role="clinician",
        )
    if code == "40001":
        return ConflictError(conflict[0], code=conflict[1])
    if code == "23514":
        return ValidationError(
            "This MedWatch draft can no longer be changed this way", code=MEDWATCH_INVALID_STATE
        )
    if code == "22023":
        return ValidationError(
            "The MedWatch request was not accepted", code=MEDWATCH_INVALID_REQUEST
        )
    return ExternalServiceError("Supabase", failure)
