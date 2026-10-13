"""Clinician-controlled MedWatch draft preparation, approval, and export."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.core import authorization_reasons as reasons
from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.db.repositories import CareTeamRepository
from app.db.supabase_execute import execute_async
from app.models.adr import (
    MedWatchDraftApprovalRequest,
    MedWatchDraftCreateRequest,
    MedWatchDraftUpdateRequest,
    MedWatchFormData,
)
from app.models.enums import ADRStatus, MedWatchStatus
from app.models.medwatch_form_3500 import FORM_3500_VERSION, MAX_OTHER_PRODUCTS, MedWatchFormDataV2
from app.pharmacovigilance import NaranjoQuestion
from app.services.medwatch_3500.dates import (
    clinic_date_of,
    clinic_today,
    coerce_date,
    earliest_day,
)
from app.services.medwatch_3500.identifier import PatientIdentity, default_code
from app.services.medwatch_3500.legacy import match_frequency, match_route, past_date, split_dose

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


class MedWatchService:
    """Build evidence-attributed drafts without performing an FDA submission."""

    def __init__(self, db: Client) -> None:
        self.db = db
        self.care_team_repo = CareTeamRepository(self)

    async def create_draft(
        self,
        clinician_id: UUID,
        assessment_id: UUID,
        request: MedWatchDraftCreateRequest,
    ) -> dict[str, Any]:
        """Prepare a draft from stored facts and atomically complete ADR review."""
        assessment = await self._get_assessment(assessment_id)
        patient_id = UUID(str(assessment["patient_id"]))
        await self._assert_assignment(clinician_id, patient_id)
        if assessment.get("status") != ADRStatus.DRAFT.value:
            raise ValidationError("ADR assessment review has already been completed")

        existing = await self._execute(
            self.db.table("medwatch_drafts")
            .select("id")
            .eq("adr_assessment_id", str(assessment_id))
            .limit(1)
        )
        if existing.data:
            raise ValidationError("A MedWatch draft already exists for this assessment")

        patient, symptom, medication, clinician, medications = await self._load_source_records(
            clinician_id=clinician_id,
            patient_id=patient_id,
            assessment=assessment,
        )
        form_data, source_evidence = self._build_form_data(
            assessment=assessment,
            patient=patient,
            symptom=symptom,
            medication=medication,
            clinician=clinician,
            medications=medications,
            rationale=request.reportability_rationale,
        )
        result = await self._execute(
            self.db.rpc(
                "create_medwatch_draft",
                {
                    "p_assessment_id": str(assessment_id),
                    "p_actor_id": str(clinician_id),
                    "p_form_data": form_data.model_dump(mode="json"),
                    "p_source_evidence": source_evidence,
                    "p_reportability_rationale": request.reportability_rationale,
                },
            )
        )
        return self._first_rpc_row(result.data, "MedWatch draft could not be created")

    async def list_drafts(self, clinician_id: UUID) -> dict[str, Any]:
        """List MedWatch drafts only for currently assigned patients."""
        assignments = await self.care_team_repo.list_assigned_patient_ids(str(clinician_id))
        patient_ids = [str(row["patient_id"]) for row in assignments if row.get("patient_id")]
        if not patient_ids:
            return {"items": [], "total": 0}
        result = await self._execute(
            self.db.table("medwatch_drafts")
            .select("*")
            .in_("patient_id", patient_ids)
            .in_("status", [MedWatchStatus.DRAFT.value, MedWatchStatus.REVIEWED.value])
            .order("created_at", desc=True)
        )
        rows = cast(list[dict[str, Any]], result.data or [])
        return {"items": rows, "total": len(rows)}

    async def update_draft(
        self,
        clinician_id: UUID,
        draft_id: UUID,
        request: MedWatchDraftUpdateRequest,
    ) -> dict[str, Any]:
        """Save a full editable form with optimistic locking and field-level audit."""
        draft = await self._get_authorized_draft(clinician_id, draft_id)
        if draft.get("status") != MedWatchStatus.DRAFT.value:
            raise ValidationError("Approved MedWatch drafts cannot be edited")

        current = MedWatchFormData.model_validate(draft.get("form_data") or {})
        if (
            request.form_data.clinical_review.naranjo_score != current.clinical_review.naranjo_score
            or request.form_data.clinical_review.causality != current.clinical_review.causality
        ):
            raise ValidationError(
                "Naranjo score and causality must come from the reviewed ADR assessment"
            )

        previous_payload = current.model_dump(mode="json")
        updated_payload = request.form_data.model_dump(mode="json")
        changed_fields = self._changed_leaf_paths(previous_payload, updated_payload)
        if not changed_fields:
            return draft

        result = await self._execute(
            self.db.rpc(
                "update_medwatch_draft",
                {
                    "p_draft_id": str(draft_id),
                    "p_actor_id": str(clinician_id),
                    "p_form_data": updated_payload,
                    "p_changed_fields": changed_fields,
                    "p_expected_revision": request.expected_revision,
                },
            )
        )
        return self._first_rpc_row(result.data, "MedWatch draft could not be saved")

    async def approve_draft(
        self,
        clinician_id: UUID,
        draft_id: UUID,
        request: MedWatchDraftApprovalRequest,
    ) -> dict[str, Any]:
        """Approve a complete draft after explicit clinician attestation."""
        draft = await self._get_authorized_draft(clinician_id, draft_id)
        if draft.get("status") != MedWatchStatus.DRAFT.value:
            raise ValidationError("MedWatch draft has already been approved")
        form = MedWatchFormData.model_validate(draft.get("form_data") or {})
        missing = self._approval_missing_fields(form)
        if missing:
            raise ValidationError("Complete required fields before approval: " + ", ".join(missing))

        result = await self._execute(
            self.db.rpc(
                "approve_medwatch_draft",
                {
                    "p_draft_id": str(draft_id),
                    "p_actor_id": str(clinician_id),
                    "p_approval_note": request.approval_note,
                    "p_expected_revision": request.expected_revision,
                },
            )
        )
        return self._first_rpc_row(result.data, "MedWatch draft could not be approved")

    async def export_draft(self, clinician_id: UUID, draft_id: UUID) -> dict[str, Any]:
        """Record and return an approved JSON artifact; never file it externally."""
        draft = await self._get_authorized_draft(clinician_id, draft_id)
        if draft.get("status") != MedWatchStatus.REVIEWED.value or not draft.get("approved_at"):
            raise ValidationError("Only approved MedWatch drafts can be exported")
        result = await self._execute(
            self.db.rpc(
                "record_medwatch_draft_export",
                {"p_draft_id": str(draft_id), "p_actor_id": str(clinician_id)},
            )
        )
        exported = self._first_rpc_row(result.data, "MedWatch draft export could not be recorded")
        return {
            "filename": f"medwatch-draft-{draft_id}.json",
            "media_type": "application/json",
            "content": {
                "artifact_type": "medwatch_3500a_draft",
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
                "form_data": exported["form_data"],
                "source_evidence": exported.get("source_evidence") or [],
                "clinician_edited_fields": exported.get("clinician_edited_fields") or [],
            },
        }

    async def _get_assessment(self, assessment_id: UUID) -> dict[str, Any]:
        result = await self._execute(
            self.db.table("adr_assessments").select("*").eq("id", str(assessment_id)).single()
        )
        assessment = cast(dict[str, Any] | None, result.data)
        if not assessment:
            raise NotFoundError("ADR assessment", str(assessment_id))
        return assessment

    async def _get_authorized_draft(self, clinician_id: UUID, draft_id: UUID) -> dict[str, Any]:
        result = await self._execute(
            self.db.table("medwatch_drafts").select("*").eq("id", str(draft_id)).single()
        )
        draft = cast(dict[str, Any] | None, result.data)
        if not draft:
            raise NotFoundError("MedWatch draft", str(draft_id))
        await self._assert_assignment(clinician_id, UUID(str(draft["patient_id"])))
        return draft

    async def _load_source_records(
        self,
        *,
        clinician_id: UUID,
        patient_id: UUID,
        assessment: dict[str, Any],
    ) -> tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        list[dict[str, Any]],
    ]:
        patient_result = await self._execute(
            self.db.table("patients").select("*").eq("id", str(patient_id)).single()
        )
        symptom_result = await self._execute(
            self.db.table("symptom_reports")
            .select("*")
            .eq("id", str(assessment["symptom_report_id"]))
            .single()
        )
        medication_result = await self._execute(
            self.db.table("medications")
            .select("*")
            .eq("id", str(assessment["suspect_medication_id"]))
            .single()
        )
        clinician_result = await self._execute(
            self.db.table("clinicians").select("*").eq("id", str(clinician_id)).single()
        )
        medications_result = await self._execute(
            self.db.table("medications")
            .select("*")
            .eq("patient_id", str(patient_id))
            .eq("is_active", True)
        )
        patient = cast(dict[str, Any] | None, patient_result.data)
        symptom = cast(dict[str, Any] | None, symptom_result.data)
        medication = cast(dict[str, Any] | None, medication_result.data)
        clinician = cast(dict[str, Any] | None, clinician_result.data)
        if not patient:
            raise NotFoundError("Patient", str(patient_id))
        if not symptom:
            raise NotFoundError("Symptom report", str(assessment["symptom_report_id"]))
        if not medication:
            raise NotFoundError("Medication", str(assessment["suspect_medication_id"]))
        if not clinician:
            raise NotFoundError("Clinician", str(clinician_id))
        return (
            patient,
            symptom,
            medication,
            clinician,
            cast(list[dict[str, Any]], medications_result.data or []),
        )

    @staticmethod
    def _build_form_data(
        *,
        assessment: dict[str, Any],
        patient: dict[str, Any],
        symptom: dict[str, Any],
        medication: dict[str, Any],
        clinician: dict[str, Any],
        medications: list[dict[str, Any]],
        rationale: str,
    ) -> tuple[MedWatchFormData, list[dict[str, Any]]]:
        patient_name = " ".join(
            part for part in [patient.get("first_name"), patient.get("last_name")] if part
        )
        clinician_name = " ".join(
            part for part in [clinician.get("first_name"), clinician.get("last_name")] if part
        )
        description = str(symptom.get("symptom") or "")
        if symptom.get("severity") is not None:
            description = f"{description} (patient-reported severity {symptom['severity']}/10)"
        if symptom.get("notes"):
            description = f"{description}. {symptom['notes']}"
        concomitant = [
            str(item.get("name") or item.get("generic_name") or "").strip()
            for item in medications
            if str(item.get("id")) != str(medication.get("id"))
        ]
        form = MedWatchFormData.model_validate(
            {
                "patient": {
                    "patient_identifier": patient_name,
                    "date_of_birth": str(patient.get("date_of_birth") or ""),
                    "sex": str(patient.get("gender") or ""),
                },
                "event": {
                    "description": description,
                    "onset_date_or_time": str(symptom.get("onset") or ""),
                    "outcome": "",
                    "seriousness": "",
                },
                "suspect_product": {
                    "name": str(
                        medication.get("name")
                        or medication.get("generic_name")
                        or assessment.get("suspect_medication_name")
                        or ""
                    ),
                    "dose": str(medication.get("dosage") or ""),
                    "frequency": str(medication.get("frequency") or ""),
                    "route": str(medication.get("route") or ""),
                    "therapy_start_date": str(medication.get("start_date") or ""),
                    "therapy_end_date": str(medication.get("end_date") or ""),
                },
                "concomitant_products": {
                    "products": ", ".join(item for item in concomitant if item)
                },
                "tests_and_history": {
                    "relevant_tests": "",
                    "other_relevant_history": "",
                },
                "reporter": {
                    "name": clinician_name,
                    "email": str(clinician.get("email") or ""),
                    "specialty": str(clinician.get("specialty") or ""),
                    "clinic_name": str(clinician.get("clinic_name") or ""),
                },
                "clinical_review": {
                    "naranjo_score": assessment["naranjo_score"],
                    "causality": assessment["causality"],
                    "reportability_rationale": rationale,
                },
            }
        )
        evidence: list[dict[str, Any]] = [
            {
                "field_paths": [
                    "patient.patient_identifier",
                    "patient.date_of_birth",
                    "patient.sex",
                ],
                "source_type": "patient_profile",
                "source_id": str(patient["id"]),
                "attribution": "Patient account profile",
                "excerpt": None,
                "citation": f"patients/{patient['id']}",
            },
            {
                "field_paths": ["event.description", "event.onset_date_or_time"],
                "source_type": "patient_symptom_report",
                "source_id": str(symptom["id"]),
                "attribution": "Patient-reported symptom",
                "excerpt": description,
                "citation": f"symptom_reports/{symptom['id']}",
            },
            {
                "field_paths": [
                    "suspect_product.name",
                    "suspect_product.dose",
                    "suspect_product.frequency",
                    "suspect_product.route",
                    "suspect_product.therapy_start_date",
                    "suspect_product.therapy_end_date",
                ],
                "source_type": (
                    "document_grounded_medication"
                    if medication.get("source_document_id")
                    else "patient_medication_record"
                ),
                "source_id": str(medication["id"]),
                "attribution": "Medication record",
                "excerpt": str(medication.get("instructions") or "") or None,
                "citation": (
                    f"documents/{medication['source_document_id']}"
                    if medication.get("source_document_id")
                    else f"medications/{medication['id']}"
                ),
            },
            {
                "field_paths": [
                    "clinical_review.naranjo_score",
                    "clinical_review.causality",
                ],
                "source_type": "deterministic_adr_assessment",
                "source_id": str(assessment["id"]),
                "attribution": "Naranjo decision support reviewed by clinician",
                "excerpt": f"Naranjo {assessment['naranjo_score']}: {assessment['causality']}",
                "citation": f"adr_assessments/{assessment['id']}",
            },
            {
                "field_paths": [
                    "reporter.name",
                    "reporter.email",
                    "reporter.specialty",
                    "reporter.clinic_name",
                    "clinical_review.reportability_rationale",
                ],
                "source_type": "clinician_attestation",
                "source_id": str(clinician["id"]),
                "attribution": "Authenticated clinician",
                "excerpt": rationale,
                "citation": f"clinicians/{clinician['id']}",
            },
        ]
        for answer in assessment.get("evidence") or []:
            excerpt = str(answer.get("evidence") or "").strip()
            if excerpt:
                evidence.append(
                    {
                        "field_paths": ["event.description", "clinical_review.causality"],
                        "source_type": "patient_confirmed_adr_evidence",
                        "source_id": str(symptom["id"]),
                        "attribution": str(answer.get("question") or "Patient ADR answer"),
                        "excerpt": excerpt,
                        "citation": f"adr_assessments/{assessment['id']}/evidence",
                    }
                )
        if concomitant:
            evidence.append(
                {
                    "field_paths": ["concomitant_products.products"],
                    "source_type": "patient_medication_record",
                    "source_id": None,
                    "attribution": "Active medication list excluding suspect product",
                    "excerpt": ", ".join(item for item in concomitant if item),
                    "citation": f"patients/{patient['id']}/medications",
                }
            )
        return form, evidence

    @staticmethod
    def _approval_missing_fields(form: MedWatchFormData) -> list[str]:
        required = {
            "patient identifier": form.patient.patient_identifier,
            "event description": form.event.description,
            "suspect product": form.suspect_product.name,
            "reporter name": form.reporter.name,
            "reportability rationale": form.clinical_review.reportability_rationale,
        }
        return [label for label, value in required.items() if not value.strip()]

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

    @staticmethod
    def _first_rpc_row(data: Any, error_message: str) -> dict[str, Any]:
        rows = [row for row in cast(list[dict[str, Any]], data or []) if isinstance(row, dict)]
        if not rows:
            raise ValidationError(error_message)
        return rows[0]

    async def _execute(self, query: Any) -> Any:
        return await execute_async(self, lambda _db: query, operation="MedWatch workflow")
