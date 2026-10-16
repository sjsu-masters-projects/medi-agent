"""Patient service — profile management and care team operations.

Handles:
    - Get/update own patient profile
    - List care team (clinicians assigned to this patient)
    - Join a clinic via invite code
    - Read and answer ADR follow-up requests
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from postgrest.exceptions import APIError
from supabase import Client

from app.core.exceptions import ExternalServiceError, NotFoundError, ValidationError
from app.db.supabase_execute import execute_async
from app.models.adr import ADR_FOLLOW_UP_RECENT_LIMIT, ADRInformationResponseRequest
from app.pharmacovigilance import (
    PATIENT_ANSWERABLE_NARANJO_QUESTIONS,
    NaranjoAnswer,
    NaranjoQuestion,
    score_naranjo,
)
from app.services.reminder_schedule_service import validate_timezone_name

logger = logging.getLogger(__name__)

# Optional profile fields a patient may clear by sending an explicit null.
CLEARABLE_PROFILE_FIELDS: frozenset[str] = frozenset({"gender"})

# Patient follow-up history window (decision D5): answered and cancelled requests
# created within this many days, capped at ADR_FOLLOW_UP_RECENT_LIMIT.
ADR_FOLLOW_UP_RECENT_DAYS = 90

# Patient-visible columns only. No Naranjo score or causality is read for the
# follow-up overview, so none can reach the patient response.
_ADR_FOLLOW_UP_COLUMNS = (
    "id, adr_assessment_id, requested_information, patient_message, status, responses, "
    "created_at, responded_at, updated_at, "
    "adr_assessments(suspect_medication_name, symptom_reports(symptom))"
)

_ADR_REQUEST_CLOSED = "ADR_REQUEST_CLOSED"
_ADR_RESPONSE_INVALID = "ADR_RESPONSE_INVALID"
_ADR_REQUEST_CLOSED_MESSAGE = "This information request is no longer awaiting answers"
_ADR_ALLOWED_QUESTIONS = frozenset(
    question.value for question in PATIENT_ANSWERABLE_NARANJO_QUESTIONS
)
_ADR_ALLOWED_ANSWERS = frozenset(answer.value for answer in NaranjoAnswer)


def _allowed_questions(value: object) -> list[str]:
    """Allowlisted Question_Keys in first-seen order, duplicates removed."""
    if not isinstance(value, list):
        return []
    return list(
        dict.fromkeys(
            item for item in value if isinstance(item, str) and item in _ADR_ALLOWED_QUESTIONS
        )
    )


def _patient_responses(value: object) -> list[dict[str, Any]]:
    """The patient's own stored answers, limited to allowlisted questions and answers."""
    if not isinstance(value, list):
        return []
    responses: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        question = item.get("question")
        answer = item.get("answer")
        if question not in _ADR_ALLOWED_QUESTIONS or answer not in _ADR_ALLOWED_ANSWERS:
            continue
        evidence = item.get("evidence")
        responses.append(
            {
                "question": question,
                "answer": answer,
                "evidence": evidence if isinstance(evidence, str) and evidence else None,
            }
        )
    return responses


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
        """Partial update of the fields the caller explicitly sent.

        ``None`` is ignored for every field except the optional ones in
        ``CLEARABLE_PROFILE_FIELDS``, where an explicit ``None`` clears the
        stored value. Required fields such as names and preferred language
        can therefore never be nulled through this path.
        """
        clean = {k: v for k, v in updates.items() if v is not None or k in CLEARABLE_PROFILE_FIELDS}
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
        with a code column. The patient "claims" the row, so the link keeps the
        clinic that issued the code (``care_teams.clinic_id``).
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

        # Still one active link per clinician: a second link for another clinic waits
        # until the SQL that picks "the" link for a patient and clinician takes an
        # explicit care team (CLN-003 slices C and H).
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

    async def get_adr_follow_up_overview(
        self,
        patient_id: UUID,
        request_id: UUID | None = None,
        assessment_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Return the selected request, pending requests and bounded recent history.

        The client is service-role, so RLS does not apply: the ``patient_id`` filter on
        every query below is the access control. A missing ID and another patient's ID
        raise the same ``NotFoundError``.
        """
        if request_id is not None and assessment_id is not None:
            raise ValidationError("Choose a request or an assessment, not both")
        patient = str(patient_id)

        pending_rows = await self._read_adr_follow_up_rows(
            lambda db: (
                db.table("adr_information_requests")
                .select(_ADR_FOLLOW_UP_COLUMNS)
                .eq("patient_id", patient)
                .eq("status", "pending")
                .order("created_at", desc=True)
            ),
            operation="list patient pending ADR follow-up requests",
        )

        cutoff = (datetime.now(UTC) - timedelta(days=ADR_FOLLOW_UP_RECENT_DAYS)).isoformat()
        recent_rows = await self._read_adr_follow_up_rows(
            lambda db: (
                db.table("adr_information_requests")
                .select(_ADR_FOLLOW_UP_COLUMNS)
                .eq("patient_id", patient)
                .in_("status", ["answered", "cancelled"])
                .gte("created_at", cutoff)
                .order("created_at", desc=True)
                .limit(ADR_FOLLOW_UP_RECENT_LIMIT)
            ),
            operation="list patient recent ADR follow-up requests",
        )

        selected_row: dict[str, Any] | None = None
        if request_id is not None:
            selected_id = str(request_id)
            rows = await self._read_adr_follow_up_rows(
                lambda db: (
                    db.table("adr_information_requests")
                    .select(_ADR_FOLLOW_UP_COLUMNS)
                    .eq("id", selected_id)
                    .eq("patient_id", patient)
                    .limit(1)
                ),
                operation="load patient ADR follow-up request",
            )
            if not rows:
                raise NotFoundError("ADR information request", selected_id)
            selected_row = rows[0]
        elif assessment_id is not None:
            selected_assessment = str(assessment_id)
            rows = await self._read_adr_follow_up_rows(
                lambda db: (
                    db.table("adr_information_requests")
                    .select(_ADR_FOLLOW_UP_COLUMNS)
                    .eq("adr_assessment_id", selected_assessment)
                    .eq("patient_id", patient)
                    .order("created_at", desc=True)
                    .limit(1)
                ),
                operation="load patient ADR follow-up request by assessment",
            )
            if not rows:
                raise NotFoundError("ADR information request", selected_assessment)
            selected_row = rows[0]

        # At most one pending request per assessment (047 unique index), so this maps
        # a cancelled request to the request that replaced it, if any.
        replacements = {
            str(row["adr_assessment_id"]): str(row["id"])
            for row in pending_rows
            if row.get("adr_assessment_id") and row.get("id")
        }

        pending = [
            item
            for item in (self._adr_follow_up_item(row, replacements) for row in pending_rows)
            if item["requested_information"]
        ]
        recent = [
            self._adr_follow_up_item(row, replacements)
            for row in recent_rows[:ADR_FOLLOW_UP_RECENT_LIMIT]
        ]
        selected = (
            self._adr_follow_up_item(selected_row, replacements)
            if selected_row is not None
            else None
        )
        return {"selected": selected, "pending": pending, "recent": recent}

    async def _read_adr_follow_up_rows(
        self,
        build_query: Callable[[Client], Any],
        *,
        operation: str,
    ) -> list[dict[str, Any]]:
        try:
            result = await execute_async(
                self, build_query, operation=operation, retry_transient=True
            )
        except APIError:
            # Never log PostgREST details: they can echo patient-entered text.
            raise ExternalServiceError("Supabase", "ADR follow-up is unavailable") from None
        return cast(list[dict[str, Any]], result.data or [])

    @staticmethod
    def _adr_follow_up_item(raw: dict[str, Any], replacements: dict[str, str]) -> dict[str, Any]:
        """Map a stored request row to the patient-visible follow-up shape."""
        assessment = cast(dict[str, Any], raw.get("adr_assessments") or {})
        symptom = cast(dict[str, Any], assessment.get("symptom_reports") or {})
        status = raw.get("status")
        own_id = str(raw.get("id"))
        replacement = (
            replacements.get(str(raw.get("adr_assessment_id"))) if status == "cancelled" else None
        )
        return {
            "id": raw["id"],
            "adr_assessment_id": raw["adr_assessment_id"],
            "status": status,
            "symptom": symptom.get("symptom") or "Reported symptom",
            "suspect_medication_name": assessment.get("suspect_medication_name") or "",
            "requested_information": _allowed_questions(raw.get("requested_information")),
            "patient_message": raw.get("patient_message") or "",
            "created_at": raw["created_at"],
            "responded_at": raw.get("responded_at"),
            "closed_at": raw.get("updated_at") if status == "cancelled" else None,
            "responses": _patient_responses(raw.get("responses")) if status == "answered" else [],
            "replacement_request_id": replacement if replacement != own_id else None,
        }

    async def respond_to_adr_information_request(
        self,
        patient_id: UUID,
        request_id: UUID,
        response: ADRInformationResponseRequest,
    ) -> dict[str, Any]:
        """Validate confirmed patient evidence, rescore, and save it atomically."""
        try:
            request_result = await execute_async(
                self,
                lambda db: (
                    db.table("adr_information_requests")
                    .select(
                        "id, adr_assessment_id, patient_id, requested_information, status, "
                        "adr_assessments(naranjo_answers, naranjo_assessment, evidence, status)"
                    )
                    .eq("id", str(request_id))
                    .eq("patient_id", str(patient_id))
                    .limit(1)
                ),
                operation="load ADR information request",
                retry_transient=True,
            )
        except APIError:
            # Never log PostgREST details: they can echo patient-entered text.
            raise ExternalServiceError("Supabase", "ADR follow-up is unavailable") from None
        request_rows = cast(list[dict[str, Any]], request_result.data or [])
        raw_request = request_rows[0] if request_rows else None
        # The query filters patient_id; the check below keeps a foreign row out even if a
        # caller changes the query, and gives the same 404 as a missing ID.
        if not raw_request or str(raw_request.get("patient_id")) != str(patient_id):
            raise NotFoundError("ADR information request", str(request_id))

        assessment = cast(dict[str, Any], raw_request.get("adr_assessments") or {})
        if raw_request.get("status") != "pending" or assessment.get("status") != "draft":
            raise ValidationError(_ADR_REQUEST_CLOSED_MESSAGE, code=_ADR_REQUEST_CLOSED)

        requested_questions = {
            NaranjoQuestion(value)
            for value in raw_request.get("requested_information") or []
            if value in PATIENT_ANSWERABLE_NARANJO_QUESTIONS
        }
        answered_questions = {item.question for item in response.answers}
        if answered_questions != requested_questions:
            raise ValidationError("Answer every requested question before sending")

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

        try:
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
        except APIError as exc:
            # Map only the SQLSTATE. Never log PostgREST details: they can echo answers.
            if exc.code == "P0002":
                raise NotFoundError("ADR information request", str(request_id)) from None
            if exc.code == "23514":
                raise ValidationError(
                    _ADR_REQUEST_CLOSED_MESSAGE, code=_ADR_REQUEST_CLOSED
                ) from None
            if exc.code == "22023":
                raise ValidationError(
                    "The answers could not be accepted", code=_ADR_RESPONSE_INVALID
                ) from None
            raise ExternalServiceError(
                "Supabase", "ADR information response could not be saved"
            ) from None
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
