"""Clinician-controlled MedWatch draft preparation, approval, and export."""

from __future__ import annotations

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
