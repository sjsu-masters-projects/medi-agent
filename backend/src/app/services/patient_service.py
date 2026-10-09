"""Patient service — profile management and care team operations.

Handles:
    - Get/update own patient profile
    - List care team (clinicians assigned to this patient)
    - Join a clinic via invite code
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.core.exceptions import NotFoundError, ValidationError
from app.db.supabase_execute import execute_async
from app.models.adr import ADRInformationResponseRequest
from app.pharmacovigilance import (
    PATIENT_ANSWERABLE_NARANJO_QUESTIONS,
    NaranjoQuestion,
    score_naranjo,
)
from app.services.reminder_schedule_service import validate_timezone_name

logger = logging.getLogger(__name__)


class PatientService:
    """Patient-scoped operations. All methods require the patient's user ID."""

    def __init__(self, db: Client) -> None:
        self.db = db

    # ── Profile ─────────────────────────────────────────

    async def get_profile(self, patient_id: UUID) -> Any:
        """Fetch the patient's own profile by auth user ID."""
        result = self.db.table("patients").select("*").eq("id", str(patient_id)).single().execute()
        if not result.data:
            raise NotFoundError("Patient", str(patient_id))
        return result.data

    async def update_profile(self, patient_id: UUID, updates: dict[str, Any]) -> Any:
        """Partial update — only non-None fields are sent."""
        # Filter out None values so we don't overwrite with nulls
        clean = {k: v for k, v in updates.items() if v is not None}
        if not clean:
            return await self.get_profile(patient_id)

        if "timezone" in clean:
            clean["timezone"] = validate_timezone_name(str(clean["timezone"]))

        result = self.db.table("patients").update(clean).eq("id", str(patient_id)).execute()
        if not result.data:
            raise NotFoundError("Patient", str(patient_id))
        return result.data[0]

    # ── Care Team ───────────────────────────────────────

    async def get_care_team(self, patient_id: UUID) -> Any:
        """List all clinicians assigned to this patient, with their names."""
        result = (
            self.db.table("care_teams")
            .select("*, clinicians(first_name, last_name, specialty, clinic_name)")
            .eq("patient_id", str(patient_id))
            .eq("status", "active")
            .execute()
        )
        # Flatten the joined clinician data for the response
        teams = []
        for row in cast(list[dict[str, Any]], result.data or []):
            clinician = cast(dict[str, Any], row.pop("clinicians", {}) or {})
            row["clinician_first_name"] = clinician.get("first_name", "")
            row["clinician_last_name"] = clinician.get("last_name", "")
            row["specialty_context"] = clinician.get("specialty", "")
            row["clinic_name"] = clinician.get("clinic_name", "")
            teams.append(row)
        return teams

    async def join_care_team(self, patient_id: UUID, invite_code: str) -> Any:
        """Join a clinician's care team using an invite code.

        Invite codes are stored in the care_teams table as pending rows
        with a code column. The patient "claims" the row.
        """
        normalized_code = invite_code.strip().upper()

        # Look up invite regardless of status so errors can be precise.
        result = (
            self.db.table("care_teams")
            .select("*")
            .eq("invite_code", normalized_code)
            .single()
            .execute()
        )
        if not result.data:
            raise ValidationError("Invite code is invalid")

        raw_invite = result.data
        if isinstance(raw_invite, list):
            if not raw_invite:
                raise ValidationError("Invite code is invalid")
            invite = cast(dict[str, Any], raw_invite[0])
        else:
            invite = cast(dict[str, Any], raw_invite)

        expires_at = invite.get("invite_expires_at")
        if isinstance(expires_at, str):
            try:
                if datetime.fromisoformat(expires_at.replace("Z", "+00:00")) <= datetime.now(UTC):
                    self.db.table("care_teams").update({"status": "inactive"}).eq(
                        "id", invite["id"]
                    ).execute()
                    raise ValidationError(
                        "Invite code has expired. Request a new active invite code"
                    )
            except ValueError:
                logger.warning(
                    "Invalid invite_expires_at value on care_teams row %s", invite.get("id")
                )

        if invite.get("status") != "pending":
            if invite.get("status") == "active":
                raise ValidationError("Invite code is already active and cannot be reused")
            raise ValidationError("Invite code is no longer active. Request a new code")

        if invite.get("patient_id"):
            raise ValidationError("Invite code has already been claimed")

        existing_link = (
            self.db.table("care_teams")
            .select("id")
            .eq("patient_id", str(patient_id))
            .eq("clinician_id", str(invite["clinician_id"]))
            .eq("status", "active")
            .execute()
        )
        if existing_link.data:
            raise ValidationError("You are already linked to this care team")

        care_team_id = invite["id"]

        # Claim the invite
        updated = (
            self.db.table("care_teams")
            .update(
                {
                    "invite_claimed_at": datetime.now(UTC).isoformat(),
                    "patient_id": str(patient_id),
                    "status": "active",
                }
            )
            .eq("id", care_team_id)
            .execute()
        )
        if not updated.data:
            raise ValidationError("Failed to join care team")

        joined = (
            self.db.table("care_teams")
            .select("*, clinicians(first_name, last_name, specialty, clinic_name)")
            .eq("id", care_team_id)
            .single()
            .execute()
        )
        if not joined.data:
            raise ValidationError("Failed to load care team after joining")

        row = cast(dict[str, Any], joined.data)
        clinician = cast(dict[str, Any], row.pop("clinicians", {}) or {})
        row["clinician_first_name"] = clinician.get("first_name", "")
        row["clinician_last_name"] = clinician.get("last_name", "")
        row["specialty_context"] = clinician.get("specialty", "")
        row["clinic_name"] = clinician.get("clinic_name", "")
        return row

    # ── ADR information requests ────────────────────────

    async def list_adr_information_requests(self, patient_id: UUID) -> list[dict[str, Any]]:
        """Return pending, patient-safe ADR follow-up requests for this patient."""
        result = await execute_async(
            self,
            lambda db: (
                db.table("adr_information_requests")
                .select(
                    "id, adr_assessment_id, requested_information, patient_message, status, "
                    "created_at, adr_assessments(suspect_medication_name, naranjo_score, "
                    "causality, symptom_reports(symptom, severity))"
                )
                .eq("patient_id", str(patient_id))
                .eq("status", "pending")
                .order("created_at", desc=True)
            ),
            operation="list patient ADR information requests",
            retry_transient=True,
        )

        requests: list[dict[str, Any]] = []
        for raw in cast(list[dict[str, Any]], result.data or []):
            assessment = cast(dict[str, Any], raw.get("adr_assessments") or {})
            symptom = cast(dict[str, Any], assessment.get("symptom_reports") or {})
            questions = [
                NaranjoQuestion(value)
                for value in raw.get("requested_information") or []
                if value in PATIENT_ANSWERABLE_NARANJO_QUESTIONS
            ]
            if not questions:
                continue
            requests.append(
                {
                    "id": raw["id"],
                    "adr_assessment_id": raw["adr_assessment_id"],
                    "symptom": symptom.get("symptom") or "Reported symptom",
                    "symptom_severity": symptom.get("severity") or 1,
                    "suspect_medication_name": assessment.get("suspect_medication_name") or "",
                    "requested_information": questions,
                    "patient_message": raw.get("patient_message") or "",
                    "current_naranjo_score": assessment.get("naranjo_score") or 0,
                    "current_causality": assessment.get("causality") or "Doubtful",
                    "status": raw["status"],
                    "created_at": raw["created_at"],
                }
            )
        return requests

    async def respond_to_adr_information_request(
        self,
        patient_id: UUID,
        request_id: UUID,
        response: ADRInformationResponseRequest,
    ) -> dict[str, Any]:
        """Validate confirmed patient evidence, rescore, and save it atomically."""
        request_result = await execute_async(
            self,
            lambda db: (
                db.table("adr_information_requests")
                .select(
                    "id, adr_assessment_id, patient_id, requested_information, status, "
                    "adr_assessments(naranjo_answers, naranjo_assessment, evidence, status)"
                )
                .eq("id", str(request_id))
                .single()
            ),
            operation="load ADR information request",
            retry_transient=True,
        )
        raw_request = cast(dict[str, Any] | None, request_result.data)
        if not raw_request or str(raw_request.get("patient_id")) != str(patient_id):
            raise NotFoundError("ADR information request", str(request_id))
        if raw_request.get("status") != "pending":
            raise ValidationError("This information request has already been completed")

        requested_questions = {
            NaranjoQuestion(value)
            for value in raw_request.get("requested_information") or []
            if value in PATIENT_ANSWERABLE_NARANJO_QUESTIONS
        }
        answered_questions = {item.question for item in response.answers}
        if answered_questions != requested_questions:
            raise ValidationError("Answer every requested question before sending")

        assessment = cast(dict[str, Any], raw_request.get("adr_assessments") or {})
        if assessment.get("status") != "draft":
            raise ValidationError("This ADR assessment is no longer awaiting information")

        existing_answers = cast(dict[str, str], assessment.get("naranjo_answers") or {})
        merged_answers = {
            **existing_answers,
            **{item.question.value: item.answer.value for item in response.answers},
        }
        rescored = score_naranjo(merged_answers)

        existing_evidence = list(assessment.get("evidence") or [])
        response_evidence = [
            {
                "question": item.question.value,
                "answer": item.answer.value,
                "evidence": item.evidence,
                "source": "patient_follow_up",
                "information_request_id": str(request_id),
            }
            for item in response.answers
        ]
        combined_evidence = [*existing_evidence, *response_evidence]
        response_payload = [item.model_dump(mode="json") for item in response.answers]

        result = await execute_async(
            self,
            lambda db: db.rpc(
                "respond_to_adr_information_request",
                {
                    "p_request_id": str(request_id),
                    "p_patient_id": str(patient_id),
                    "p_responses": response_payload,
                    "p_naranjo_answers": merged_answers,
                    "p_naranjo_assessment": rescored.model_dump(mode="json"),
                    "p_evidence": combined_evidence,
                    "p_score": rescored.score,
                    "p_causality": rescored.causality.value,
                },
            ),
            operation="save ADR information response",
        )
        rows = cast(list[dict[str, Any]], result.data or [])
        if not rows:
            raise ValidationError("The information response could not be saved")
        saved = rows[0]
        return {
            "request_id": saved["id"],
            "adr_assessment_id": saved["adr_assessment_id"],
            "status": saved["status"],
            "naranjo_score": saved["resolved_naranjo_score"],
            "causality": saved["resolved_causality"],
            "responded_at": saved["responded_at"],
        }
