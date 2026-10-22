"""Patient confirmation of a medication discrepancy (MED-002).

The clinician asks one plain question about one medication fact. The patient answers Yes,
No (I stopped), It changed (with a note) or Not sure. The answer is patient testimony: it is
stored with the request and shown next to the candidate, and nothing here writes to the
approved medication list, the fact, the care plan or reminders. The clinician decides through
the existing reconciliation decision.

Authorization lives in the database as well (care-team link, fact visibility, patient
ownership); a request that is missing, belongs to another link or another patient is reported
as not found. The patient routes never accept an actor id from the request.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast
from uuid import UUID, uuid4

from postgrest.exceptions import APIError
from supabase import Client

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.medication_confirmation import (
    MedicationConfirmationAnswer,
    MedicationConfirmationClinicianRead,
    MedicationConfirmationCreate,
    MedicationConfirmationPatientRead,
)
from app.services.acting_care_team import acting_care_team
from app.services.clinical_fact_service import ClinicalFactService
from app.services.clinical_reconciliation_service import ClinicalReconciliationService
from app.services.clinician_record_gate import ClinicianRecordGate
from app.services.frequency_labels import localized_frequency

ALREADY_ANSWERED = "MEDCONFIRM_ALREADY_ANSWERED"
EXPIRED = "MEDCONFIRM_EXPIRED"
TTL_DAYS = 14


def _text(value: Any, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:limit] or None


class MedicationConfirmationService:
    def __init__(self, db: Client) -> None:
        self.db = db
        self.gate = ClinicianRecordGate(db)

    async def _rpc(self, name: str, params: dict[str, Any]) -> Any:
        result = await asyncio.to_thread(self.db.rpc(name, params).execute)
        return result.data

    async def _call(self, name: str, params: dict[str, Any], what: str, key: UUID | str) -> Any:
        try:
            return await self._rpc(name, params)
        except APIError as error:
            code = str(error.code)
            text = f"{error.message or ''} {error.hint or ''}"
            if code == "42501":
                raise NotFoundError(what, str(key)) from None
            if ALREADY_ANSWERED in text or code == "40001":
                raise ConflictError(
                    "This question was already answered.", code=ALREADY_ANSWERED
                ) from None
            if EXPIRED in text:
                raise ValidationError("This question has expired.", code=EXPIRED) from None
            if code == "54000":
                raise ValidationError(
                    "This patient already has the maximum number of open questions."
                ) from None
            if code == "22023":
                raise ValidationError("The confirmation request is not valid.") from None
            raise

    # ── clinician ───────────────────────────────────────────────────────────────────────

    async def request(
        self,
        *,
        clinician_id: UUID,
        patient_id: UUID,
        fact_id: UUID,
        body: MedicationConfirmationCreate,
    ) -> MedicationConfirmationClinicianRead:
        access = await asyncio.to_thread(self.gate.fact, clinician_id, patient_id, fact_id)
        team = acting_care_team(access, body.care_team_id)
        fact = await asyncio.to_thread(ClinicalFactService(self.db).get_fact, fact_id, patient_id)
        if fact.get("fact_type") != "medication":
            raise ValidationError("Only a medication can be confirmed with the patient.")
        if fact.get("review_state") != "pending_review" or fact.get("reconciliation_state") not in {
            None,
            "not_started",
            "deferred",
        }:
            raise ValidationError("This imported record has already been decided.")
        if body.subject == "approved":
            query = (
                self.db.table("medications")
                .select("id, name, dosage, frequency")
                .eq("id", str(body.medication_id))
                .eq("patient_id", str(patient_id))
                .limit(1)
            )
            rows = cast(list[dict[str, Any]], (await asyncio.to_thread(query.execute)).data or [])
            if not rows:
                raise NotFoundError("Medication", str(body.medication_id))
            subject: dict[str, Any] = rows[0]
        else:
            subject = ClinicalReconciliationService(self.db).candidate_for(fact)
        name = _text(subject.get("name"), 200)
        if not name:
            raise ValidationError("This record has no medication name to ask about.")
        data = await self._call(
            "create_medication_confirmation",
            {
                "p_actor_id": str(clinician_id),
                "p_patient_id": str(patient_id),
                "p_care_team_id": team,
                "p_request_id": str(body.client_request_id or uuid4()),
                "p_fact_id": str(fact_id),
                "p_subject_kind": body.subject,
                "p_medication_id": str(body.medication_id) if body.medication_id else None,
                "p_medication_name": name,
                "p_dosage": _text(subject.get("dosage"), 100),
                "p_frequency": _text(subject.get("frequency"), 200),
                "p_ttl_days": TTL_DAYS,
            },
            "Clinical fact",
            fact_id,
        )
        return MedicationConfirmationClinicianRead.model_validate(data)

    async def list_for_fact(
        self, *, clinician_id: UUID, patient_id: UUID, fact_id: UUID
    ) -> list[MedicationConfirmationClinicianRead]:
        await asyncio.to_thread(self.gate.fact, clinician_id, patient_id, fact_id)
        data = await self._call(
            "list_fact_medication_confirmations",
            {
                "p_actor_id": str(clinician_id),
                "p_patient_id": str(patient_id),
                "p_fact_id": str(fact_id),
            },
            "Clinical fact",
            fact_id,
        )
        return [MedicationConfirmationClinicianRead.model_validate(row) for row in data or []]

    # ── patient ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _patient_read(row: dict[str, Any]) -> MedicationConfirmationPatientRead:
        frequency = row.get("frequency")
        return MedicationConfirmationPatientRead.model_validate(
            {
                **row,
                "frequency_label_en": localized_frequency(frequency, "en-US")
                if frequency
                else None,
                "frequency_label_es": localized_frequency(frequency, "es-MX")
                if frequency
                else None,
            }
        )

    async def list_for_patient(self, patient_id: UUID) -> list[MedicationConfirmationPatientRead]:
        data = await self._call(
            "list_patient_medication_confirmations",
            {"p_patient_id": str(patient_id)},
            "Patient",
            patient_id,
        )
        return [self._patient_read(row) for row in data or []]

    async def answer(
        self, *, patient_id: UUID, request_id: UUID, body: MedicationConfirmationAnswer
    ) -> MedicationConfirmationPatientRead:
        data = await self._call(
            "answer_medication_confirmation",
            {
                "p_patient_id": str(patient_id),
                "p_request_id": str(request_id),
                "p_answer": body.answer,
                "p_note": body.note,
            },
            "Medication question",
            request_id,
        )
        return self._patient_read(cast(dict[str, Any], data))
