"""Clinician service — profile, patient list, dashboard, patient deep dive.

Handles:
    - Get own clinician profile
    - List assigned patients (via care_teams junction)
    - Get full detail for a specific patient
    - Generate invite codes for patients to join
    - Dashboard risk aggregation (delegates to RiskScoreService)
    - Patient deep dive (all sub-resources for the deep dive view)
    - Clinician obligations for patients
    - Document annotations
"""

from __future__ import annotations

import asyncio
import logging
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.core.exceptions import (
    AuthorizationError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
from app.db.repositories import CareTeamRepository, ClinicianRepository, ClinicRepository
from app.db.supabase_execute import execute_async
from app.models.dashboard import DashboardSortBy, DashboardSortOrder, RiskLevel
from app.models.enums import DocumentReviewStatus, UploaderRole

logger = logging.getLogger(__name__)


class ClinicianService:
    """Clinician-scoped operations. All methods require the clinician's user ID."""

    def __init__(self, db: Client) -> None:
        self.db = db
        self.clinic_repo = ClinicRepository(self)
        self.clinician_repo = ClinicianRepository(self)
        self.care_team_repo = CareTeamRepository(self)

    # ── Profile ─────────────────────────────────────

    async def get_profile(self, clinician_id: UUID) -> Any:
        """Fetch the clinician's own profile."""
        result = await self._execute(
            self.db.table("clinicians").select("*").eq("id", str(clinician_id)).single()
        )
        if not result.data:
            raise NotFoundError("Clinician", str(clinician_id))
        return result.data

    async def update_profile(self, clinician_id: UUID, updates: dict[str, Any]) -> Any:
        """Partial update for the clinician's own profile."""
        clean = {key: value for key, value in updates.items() if value is not None}
        if not clean:
            return await self.get_profile(clinician_id)

        clinic_code = clean.pop("clinic_code", None)
        if clinic_code:
            clinic = await self._resolve_active_clinic(str(clinic_code))
            clean["clinic_id"] = clinic["id"]
            clean["clinic_name"] = clinic["display_name"]

        result = await self._execute(
            self.db.table("clinicians").update(clean).eq("id", str(clinician_id))
        )
        if not result.data:
            raise NotFoundError("Clinician", str(clinician_id))
        return result.data[0]

    async def _resolve_active_clinic(self, clinic_code: str) -> dict[str, Any]:
        """Resolve clinic identity by code and enforce active status."""
        clinics = await self.clinic_repo.find_matching_by_code_async(clinic_code)
        if not clinics:
            raise ValidationError("Clinic code is invalid")

        clinic = clinics[0]
        if clinic.get("status") != "active":
            raise ValidationError("Clinic code is inactive")

        return clinic

    # ── Patient List ────────────────────────────────────

    async def get_patients(self, clinician_id: UUID) -> Any:
        """List all patients assigned to this clinician via active care teams."""
        result = await self._execute(
            self.db.table("care_teams")
            .select("*, patients(id, email, first_name, last_name, date_of_birth, avatar_url)")
            .eq("clinician_id", str(clinician_id))
            .eq("status", "active")
        )
        patients = []
        for row in cast(list[dict[str, Any]], result.data or []):
            patient = cast(dict[str, Any], row.pop("patients", {}) or {})
            if patient:
                patient["care_team_id"] = row["id"]
                patient["role"] = row.get("role", "")
                patients.append(patient)
        return patients

    async def get_patient_detail(self, clinician_id: UUID, patient_id: UUID) -> Any:
        """Get full patient profile — only if clinician is assigned.

        Security: checks the care_teams junction table to ensure
        the clinician has an active relationship with this patient.
        """
        assignment_rows = await self.care_team_repo.find_active_assignment(
            str(clinician_id),
            str(patient_id),
        )
        if not assignment_rows:
            raise AuthorizationError("You are not assigned to this patient")

        result = await self._execute(
            self.db.table("patients").select("*").eq("id", str(patient_id)).single()
        )
        if not result.data:
            raise NotFoundError("Patient", str(patient_id))
        return result.data

    # ── Invite Codes ────────────────────────────────────

    async def generate_invite_code(self, clinician_id: UUID) -> Any:
        """Create a pending care_team row with a unique invite code.

        The patient uses this code via POST /patients/me/care-team/join.
        Codes are 8-char uppercase alphanumeric for easy sharing.
        """
        code = secrets.token_hex(4).upper()
        expires_at = (datetime.now(UTC) + timedelta(days=7)).isoformat()

        result = await self._execute(
            self.db.table("care_teams").insert(
                {
                    "clinician_id": str(clinician_id),
                    "invite_code": code,
                    "invite_expires_at": expires_at,
                    "status": "pending",
                    "role": "provider",
                }
            )
        )
        if not result.data:
            raise ExternalServiceError("Supabase", "Failed to generate invite code")

        return {
            "invite_code": code,
            "care_team_id": cast(list[dict[str, Any]], result.data)[0]["id"],
        }

    async def list_invite_codes(self, clinician_id: UUID) -> dict[str, Any]:
        """List invite codes created by the clinician with lifecycle buckets.

        Lifecycle states:
            - active: pending + unclaimed + not expired
            - claimed: linked to a patient and active
            - inactive: revoked/expired/otherwise not actionable
        """
        clinician_ids = await self._get_invite_scope_clinician_ids(clinician_id)
        rows = await self.care_team_repo.list_invites_for_clinician_ids(clinician_ids)

        now = datetime.now(UTC)
        expired_pending_ids: list[str] = []
        invites: list[dict[str, Any]] = []
        counts = {"active": 0, "claimed": 0, "inactive": 0}

        for row in rows:
            invite_id = str(row.get("id", ""))
            status = str(row.get("status") or "")
            patient_id = row.get("patient_id")
            is_expired = self._is_invite_expired(row.get("invite_expires_at"), now)

            if status == "pending" and not patient_id and is_expired and invite_id:
                expired_pending_ids.append(invite_id)
                status = "inactive"

            lifecycle_state = self._derive_invite_lifecycle_state(
                status=status,
                has_patient=bool(patient_id),
                is_expired=is_expired,
            )
            counts[lifecycle_state] += 1

            patient_data = cast(dict[str, Any], row.get("patients") or {})
            creator_data = cast(dict[str, Any], row.get("clinicians") or {})
            invites.append(
                {
                    "care_team_id": invite_id,
                    "invite_code": row.get("invite_code"),
                    "status": status,
                    "role": row.get("role"),
                    "created_at": row.get("created_at"),
                    "invite_expires_at": row.get("invite_expires_at"),
                    "invite_claimed_at": row.get("invite_claimed_at"),
                    "is_expired": is_expired,
                    "lifecycle_state": lifecycle_state,
                    "patient": (
                        {
                            "id": patient_data.get("id"),
                            "first_name": patient_data.get("first_name"),
                            "last_name": patient_data.get("last_name"),
                            "email": patient_data.get("email"),
                        }
                        if patient_data
                        else None
                    ),
                    "created_by": (
                        {
                            "id": creator_data.get("id"),
                            "first_name": creator_data.get("first_name"),
                            "last_name": creator_data.get("last_name"),
                            "email": creator_data.get("email"),
                        }
                        if creator_data
                        else None
                    ),
                }
            )

        for invite_id in expired_pending_ids:
            await self.care_team_repo.deactivate_invite(invite_id)

        return {"invites": invites, "counts": counts}

    async def _get_invite_scope_clinician_ids(self, clinician_id: UUID) -> list[str]:
        """Admins can see clinic-wide invite codes; others see only their own."""
        context = await self.clinician_repo.get_context_async(str(clinician_id), include_role=True)
        if not context:
            raise NotFoundError("Clinician", str(clinician_id))

        if context.get("role") != "admin":
            return [str(clinician_id)]

        clinician_ids: set[str] = {str(clinician_id)}
        clinic_id = context.get("clinic_id")
        clinic_name = str(context.get("clinic_name") or "")

        if clinic_id:
            clinician_ids.update(
                await self.clinician_repo.list_ids_by_clinic_id_async(str(clinic_id))
            )

        if clinic_name:
            clinician_ids.update(
                await self.clinician_repo.list_ids_by_clinic_name_async(clinic_name)
            )

        return sorted(clinician_ids)

    async def revoke_invite_code(self, clinician_id: UUID, care_team_id: UUID) -> dict[str, Any]:
        """Revoke a pending invite code created by this clinician."""
        invite = await self.care_team_repo.find_invite_for_creator(
            str(care_team_id), str(clinician_id)
        )
        if not invite:
            raise NotFoundError("Invite code", str(care_team_id))

        if invite.get("status") != "pending" or invite.get("patient_id"):
            raise ValidationError("Only pending unclaimed invite codes can be revoked")

        updated_rows = await self.care_team_repo.deactivate_invite(
            str(care_team_id), str(clinician_id)
        )
        if not updated_rows:
            raise ValidationError("Failed to revoke invite code")

        return {
            "care_team_id": str(care_team_id),
            "invite_code": invite.get("invite_code"),
            "status": "inactive",
        }

    async def get_current_invite_code(self, clinician_id: UUID) -> dict[str, str | None]:
        """Return the latest pending invite code for this clinician.

        This is a read-only lookup used by settings screens so page load does
        not create additional pending invite rows.
        """
        now = datetime.now(UTC)
        rows = await self.care_team_repo.list_pending_invites_for_clinician(str(clinician_id))
        for row in rows:
            invite_code = row.get("invite_code")
            expires_at = row.get("invite_expires_at")
            if not invite_code:
                continue

            if isinstance(expires_at, str):
                normalized = expires_at.replace("Z", "+00:00")
                try:
                    if datetime.fromisoformat(normalized) <= now:
                        continue
                except ValueError:
                    logger.warning("Invalid invite_expires_at on care_teams row %s", row.get("id"))

            if invite_code:
                return {
                    "invite_code": str(invite_code),
                    "care_team_id": str(row.get("id")) if row.get("id") else None,
                }

        return {
            "invite_code": None,
            "care_team_id": None,
        }

    # ── Dashboard ────────────────────────────────────────

    async def get_dashboard_data(
        self,
        clinician_id: UUID,
        *,
        sort_by: DashboardSortBy = "risk",
        sort_order: DashboardSortOrder = "desc",
        risk_filter: RiskLevel | None = None,
        min_med_count: int | None = None,
        max_last_activity_days: int | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Any:
        """Aggregate risk data for all assigned patients.

        Delegates per-patient risk calculation to RiskScoreService.
        Returns DashboardResponse-compatible dict.
        """
        from app.services.risk_score_service import RiskScoreService

        risk_service = RiskScoreService(self.db)
        patient_ids = await self._get_assigned_patient_ids(clinician_id)
        medwatch_count = await self._get_pending_medwatch_count(patient_ids)

        risk_results = await asyncio.gather(
            *(risk_service.get_patient_risk(pid) for pid in patient_ids),
            return_exceptions=True,
        )

        risk_data: list[dict[str, Any]] = []
        for _pid, result in zip(patient_ids, risk_results, strict=False):
            if isinstance(result, BaseException):
                logger.warning(
                    "Failed to compute risk for an assigned patient",
                    exc_info=result,
                )
                continue
            risk_data.append(result.model_dump())

        if risk_filter:
            risk_data = [p for p in risk_data if p["risk_level"] == risk_filter]

        if min_med_count is not None:
            risk_data = [p for p in risk_data if int(p.get("active_med_count", 0)) >= min_med_count]

        if max_last_activity_days is not None:
            risk_data = [
                p
                for p in risk_data
                if (age := self._last_activity_age_days(str(p.get("last_activity", ""))))
                is not None
                and age <= float(max_last_activity_days)
            ]

        reverse = sort_order.lower() != "asc"
        risk_rank = {"high": 3, "medium": 2, "unknown": 1, "low": 0}

        if sort_by == "adherence":
            risk_data.sort(key=lambda p: float(p.get("adherence_score", 0.0)), reverse=reverse)
        elif sort_by == "last_activity":
            # Smaller age means more recent activity.
            def _activity_sort_key(p: dict[str, Any]) -> float:
                age = self._last_activity_age_days(str(p.get("last_activity", "")))
                return age if age is not None else float("inf")

            risk_data.sort(key=_activity_sort_key, reverse=reverse)
        elif sort_by == "med_count":
            risk_data.sort(key=lambda p: int(p.get("active_med_count", 0)), reverse=reverse)
        else:
            risk_data.sort(
                key=lambda p: risk_rank.get(str(p.get("risk_level", "unknown")), 1), reverse=reverse
            )

        safe_page_size = max(1, min(page_size, 100))
        safe_page = max(1, page)
        total_count = len(risk_data)
        high = sum(1 for p in risk_data if p["risk_level"] == "high")
        medium = sum(1 for p in risk_data if p["risk_level"] == "medium")
        low_count = sum(1 for p in risk_data if p["risk_level"] == "low")
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        risk_data = risk_data[start:end]

        return {
            "patients": risk_data,
            "total": total_count,
            "high_risk": high,
            "medium_risk": medium,
            "low_risk": low_count,
            "medwatch_pending": medwatch_count,
        }

    async def get_patient_risk_snapshot(self, clinician_id: UUID, patient_id: UUID) -> Any:
        """Return the latest risk card payload for one assigned patient."""
        assignment_rows = await self.care_team_repo.find_active_assignment(
            str(clinician_id),
            str(patient_id),
        )
        if not assignment_rows:
            raise AuthorizationError("You are not assigned to this patient")

        from app.services.risk_score_service import RiskScoreService

        risk_service = RiskScoreService(self.db)
        risk = await risk_service.get_patient_risk(patient_id)
        return risk.model_dump()

    async def get_patient_deep_dive(self, clinician_id: UUID, patient_id: UUID) -> Any:
        """Aggregate all patient data for the Patient Deep Dive view.

        Security: verifies care_team assignment before fetching.
        """
        await self._assert_patient_assignment(clinician_id, patient_id)

        pid = str(patient_id)

        patient_row = await self._execute(
            self.db.table("patients").select("*").eq("id", pid).single()
        )
        if not patient_row.data:
            raise NotFoundError("Patient", pid)
        patient = cast(dict[str, Any], patient_row.data)

        meds = await self._execute(
            self.db.table("medications").select("*").eq("patient_id", pid).eq("is_active", True)
        )
        medications = cast(list[dict[str, Any]], meds.data or [])

        care_team_rows = await self._execute(
            self.db.table("care_teams")
            .select("id, clinicians(first_name, last_name)")
            .eq("patient_id", pid)
            .eq("status", "active")
        )
        care_teams = cast(list[dict[str, Any]], care_team_rows.data or [])
        provider_by_team: dict[str, str] = {}
        for team in care_teams:
            clinician = cast(dict[str, Any], team.get("clinicians") or {})
            first = str(clinician.get("first_name", "")).strip()
            last = str(clinician.get("last_name", "")).strip()
            name = " ".join(part for part in [first, last] if part).strip()
            if team.get("id") and name:
                provider_by_team[str(team["id"])] = name

        for med in medications:
            team_id = med.get("prescribed_by_care_team_id")
            if team_id and str(team_id) in provider_by_team:
                med["prescribed_by_name"] = provider_by_team[str(team_id)]

        adherence_series = await self._build_adherence_series(patient_id)

        symptoms = await self._execute(
            self.db.table("symptom_reports")
            .select("*")
            .eq("patient_id", pid)
            .order("created_at", desc=True)
            .limit(50)
        )
        symptom_reports = cast(list[dict[str, Any]], symptoms.data or [])

        chats = await self._execute(
            self.db.table("chat_messages")
            .select("role, content, created_at, audio_url")
            .eq("patient_id", pid)
            .order("created_at", desc=True)
            .limit(30)
        )
        chat_messages = cast(list[dict[str, Any]], chats.data or [])

        conds = await self._execute(self.db.table("conditions").select("*").eq("patient_id", pid))
        conditions = cast(list[dict[str, Any]], conds.data or [])

        allergies_res = await self._execute(
            self.db.table("allergies").select("*").eq("patient_id", pid)
        )
        allergies = cast(list[dict[str, Any]], allergies_res.data or [])

        docs = await self._execute(
            self.db.table("documents")
            .select(
                "id, file_name, document_type, parse_status, ai_summary, "
                "created_at, uploaded_by_role, clinician_annotation, "
                "review_status, reviewed_by, reviewed_at, review_note"
            )
            .eq("patient_id", pid)
            .order("created_at", desc=True)
        )
        documents = await self._attach_document_reviewers(
            cast(list[dict[str, Any]], docs.data or [])
        )

        soap_res = await self._execute(
            self.db.table("soap_notes")
            .select("*")
            .eq("patient_id", pid)
            .order("generated_at", desc=True)
            .limit(1)
        )
        soap_rows = cast(list[dict[str, Any]], soap_res.data or [])
        latest_soap_note = soap_rows[0] if soap_rows else None

        obligations_res = await self._execute(
            self.db.table("obligations")
            .select("id, obligation_type, description, frequency, notes, is_active, created_at")
            .eq("patient_id", pid)
            .eq("is_active", True)
            .order("created_at", desc=True)
        )
        obligations = cast(list[dict[str, Any]], obligations_res.data or [])

        obligation_completion_rate = await self._compute_obligation_completion_rate(patient_id)

        from app.services.risk_score_service import RiskScoreService

        risk_service = RiskScoreService(self.db)
        try:
            risk_data = await risk_service.get_patient_risk(patient_id)
            risk_level = risk_data.risk_level
            adherence_score = risk_data.adherence_score
        except Exception as exc:
            logger.warning(
                "Failed to compute risk during deep dive",
                exc_info=exc,
            )
            risk_level = "unknown"
            adherence_score = 0.0

        return {
            "patient_id": pid,
            "first_name": patient.get("first_name", ""),
            "last_name": patient.get("last_name", ""),
            "email": patient.get("email", ""),
            "date_of_birth": patient.get("date_of_birth"),
            "avatar_url": patient.get("avatar_url"),
            "risk_level": risk_level,
            "adherence_score": adherence_score,
            "medications": medications,
            "adherence_series": adherence_series,
            "symptom_reports": symptom_reports,
            "chat_messages": list(reversed(chat_messages)),
            "conditions": conditions,
            "allergies": allergies,
            "documents": documents,
            "latest_soap_note": latest_soap_note,
            "obligations": obligations,
            "obligation_completion_rate": obligation_completion_rate,
        }

    async def list_document_review_queue(self, clinician_id: UUID) -> list[dict[str, Any]]:
        """List pending patient-uploaded documents for assigned patients."""
        patient_ids = await self._get_assigned_patient_ids(clinician_id)
        if not patient_ids:
            return []

        patient_id_values = [str(patient_id) for patient_id in patient_ids]
        patient_rows = await self._execute(
            self.db.table("patients")
            .select("id, first_name, last_name")
            .in_("id", patient_id_values)
        )
        patients_by_id = {
            str(row["id"]): row
            for row in cast(list[dict[str, Any]], patient_rows.data or [])
            if row.get("id")
        }

        docs = await self._execute(
            self.db.table("documents")
            .select(
                "id, patient_id, file_name, document_type, parse_status, ai_summary, "
                "source_clinic, created_at, uploaded_by_role, review_status"
            )
            .in_("patient_id", patient_id_values)
            .eq("uploaded_by_role", UploaderRole.PATIENT.value)
            .eq("review_status", DocumentReviewStatus.PENDING.value)
            .order("created_at", desc=True)
        )

        queue_items: list[dict[str, Any]] = []
        for row in cast(list[dict[str, Any]], docs.data or []):
            patient = patients_by_id.get(str(row.get("patient_id")))
            if not patient:
                continue
            queue_items.append(
                {
                    **row,
                    "patient_first_name": patient.get("first_name", ""),
                    "patient_last_name": patient.get("last_name", ""),
                }
            )

        return queue_items

    async def approve_document_review(
        self,
        clinician_id: UUID,
        patient_id: UUID,
        document_id: UUID,
    ) -> dict[str, Any]:
        """Approve a pending patient-uploaded document review."""
        return await self._set_document_review(
            clinician_id=clinician_id,
            patient_id=patient_id,
            document_id=document_id,
            review_status=DocumentReviewStatus.APPROVED,
            review_note=None,
        )

    async def reject_document_review(
        self,
        clinician_id: UUID,
        patient_id: UUID,
        document_id: UUID,
        review_note: str | None = None,
    ) -> dict[str, Any]:
        """Reject a pending patient-uploaded document review with optional note."""
        return await self._set_document_review(
            clinician_id=clinician_id,
            patient_id=patient_id,
            document_id=document_id,
            review_status=DocumentReviewStatus.REJECTED,
            review_note=review_note,
        )

    async def set_patient_obligation(
        self, clinician_id: UUID, patient_id: UUID, obligation_data: dict[str, Any]
    ) -> Any:
        """Create an obligation for a patient on behalf of a clinician."""
        assignment_rows = await self.care_team_repo.find_active_assignment(
            str(clinician_id),
            str(patient_id),
        )
        if not assignment_rows:
            raise AuthorizationError("You are not assigned to this patient")

        care_team_id = assignment_rows[0]["id"]

        row = {
            "patient_id": str(patient_id),
            "set_by_care_team_id": care_team_id,
            "obligation_type": obligation_data["obligation_type"],
            "description": obligation_data["description"],
            "frequency": obligation_data["frequency"],
            "notes": obligation_data.get("notes"),
            "is_active": True,
        }

        result = await self._execute(self.db.table("obligations").insert(row))
        if not result.data:
            raise ExternalServiceError("Supabase", "Failed to create obligation")

        return cast(list[dict[str, Any]], result.data)[0]

    async def save_document_annotation(
        self, clinician_id: UUID, patient_id: UUID, document_id: UUID, annotation_text: str
    ) -> Any:
        """Save clinician annotation on a document.

        Security: verifies both care_team assignment AND document belongs to patient.
        """
        await self._assert_patient_assignment(clinician_id, patient_id)

        await self._get_document_row(patient_id, document_id)

        await self._execute(
            self.db.table("documents")
            .update(
                {
                    "clinician_annotation": annotation_text,
                    "annotation_by": str(clinician_id),
                }
            )
            .eq("id", str(document_id))
        )

        return {"status": "saved", "document_id": str(document_id)}

    async def get_patient_a2a_timeline(
        self,
        clinician_id: UUID,
        patient_id: UUID,
        *,
        session_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Return A2A lifecycle timeline for an assigned patient.

        Optional session_id scopes timeline to a chat session.
        """
        await self.get_patient_detail(clinician_id, patient_id)

        safe_limit = max(1, min(limit, 200))
        query = (
            self.db.table("a2a_tasks")
            .select("*")
            .eq("patient_id", str(patient_id))
            .order("created_at", desc=True)
            .limit(safe_limit)
        )
        if session_id:
            query = query.eq("conversation_session_id", session_id)

        result = await self._execute(query)
        tasks = [row for row in (result.data or []) if isinstance(row, dict)]

        return {
            "patient_id": str(patient_id),
            "session_id": session_id,
            "tasks": tasks,
        }

    # ── Private helpers ──────────────────────────────────────────────────────

    async def _get_assigned_patient_ids(self, clinician_id: UUID) -> list[UUID]:
        """Return list of patient UUIDs assigned to this clinician."""
        rows = await self.care_team_repo.list_assigned_patient_ids(str(clinician_id))
        return [UUID(row["patient_id"]) for row in rows if row.get("patient_id")]

    async def _assert_patient_assignment(self, clinician_id: UUID, patient_id: UUID) -> None:
        """Require an active care-team assignment before clinician access."""
        assignment_rows = await self.care_team_repo.find_active_assignment(
            str(clinician_id),
            str(patient_id),
        )
        if not assignment_rows:
            raise AuthorizationError("You are not assigned to this patient")

    async def _get_document_row(
        self,
        patient_id: UUID,
        document_id: UUID,
        *,
        fields: str = (
            "id, patient_id, uploaded_by_role, review_status, reviewed_by, "
            "reviewed_at, review_note"
        ),
    ) -> dict[str, Any]:
        """Fetch a patient-owned document row or raise NotFound."""
        doc_result = await self._execute(
            self.db.table("documents")
            .select(fields)
            .eq("id", str(document_id))
            .eq("patient_id", str(patient_id))
            .single()
        )
        if not doc_result.data:
            raise NotFoundError("Document", str(document_id))
        return cast(dict[str, Any], doc_result.data)

    async def _set_document_review(
        self,
        *,
        clinician_id: UUID,
        patient_id: UUID,
        document_id: UUID,
        review_status: DocumentReviewStatus,
        review_note: str | None,
    ) -> dict[str, Any]:
        """Persist a shared review decision for a patient-uploaded document."""
        await self._assert_patient_assignment(clinician_id, patient_id)
        document = await self._get_document_row(patient_id, document_id)

        if document.get("uploaded_by_role") != UploaderRole.PATIENT.value:
            raise ValidationError("Only patient-uploaded documents can be reviewed")

        current_status = document.get("review_status")
        if current_status != DocumentReviewStatus.PENDING.value:
            raise ValidationError("Document review has already been completed")

        reviewed_at = datetime.now(UTC).isoformat()
        update_payload = {
            "review_status": review_status.value,
            "reviewed_by": str(clinician_id),
            "reviewed_at": reviewed_at,
            "review_note": review_note.strip() if review_note else None,
        }

        result = await self._execute(
            self.db.table("documents")
            .update(update_payload)
            .eq("id", str(document_id))
            .eq("patient_id", str(patient_id))
        )
        updated_rows = cast(list[dict[str, Any]], result.data or [])
        updated = updated_rows[0] if updated_rows else {**document, **update_payload}

        return {
            "status": "reviewed",
            "document_id": str(document_id),
            "patient_id": str(patient_id),
            "review_status": updated.get("review_status", review_status.value),
            "reviewed_by": updated.get("reviewed_by", str(clinician_id)),
            "reviewed_at": updated.get("reviewed_at", reviewed_at),
            "review_note": updated.get("review_note"),
        }

    async def _attach_document_reviewers(
        self,
        documents: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Hydrate reviewer metadata onto document rows for clinician views."""
        reviewer_ids = sorted(
            {
                str(document["reviewed_by"])
                for document in documents
                if document.get("reviewed_by")
            }
        )
        if not reviewer_ids:
            return documents

        reviewers_result = await self._execute(
            self.db.table("clinicians")
            .select("id, first_name, last_name")
            .in_("id", reviewer_ids)
        )
        reviewers_by_id = {
            str(row["id"]): row
            for row in cast(list[dict[str, Any]], reviewers_result.data or [])
            if row.get("id")
        }

        for document in documents:
            reviewer_id = document.get("reviewed_by")
            document["reviewer"] = (
                reviewers_by_id.get(str(reviewer_id)) if reviewer_id else None
            )

        return documents

    async def _get_pending_medwatch_count(self, patient_ids: list[UUID]) -> int:
        """Count draft/open MedWatch assessments across all assigned patients."""
        if not patient_ids:
            return 0
        result = await self._execute(
            self.db.table("adr_assessments")
            .select("id", count="exact")  # type: ignore[arg-type]
            .in_("patient_id", [str(pid) for pid in patient_ids])
            .in_("status", ["draft", "open"])
        )
        return result.count or 0

    async def _build_adherence_series(self, patient_id: UUID) -> list[dict[str, Any]]:
        """Build a 30-day daily adherence series for Recharts LineChart."""
        cutoff = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        logs = await self._execute(
            self.db.table("adherence_logs")
            .select("status, target_type, logged_at")
            .eq("patient_id", str(patient_id))
            .gte("logged_at", cutoff)
        )
        log_data = cast(list[dict[str, Any]], logs.data or [])

        by_date: dict[str, dict[str, int]] = {}
        for log in log_data:
            try:
                day = log["logged_at"][:10]
            except (KeyError, TypeError):
                continue
            if day not in by_date:
                by_date[day] = {"completed": 0, "total": 0}
            by_date[day]["total"] += 1
            if log.get("status") == "completed":
                by_date[day]["completed"] += 1

        today = datetime.now(UTC).date()
        series = []
        for i in range(29, -1, -1):
            day = (today - timedelta(days=i)).isoformat()
            counts = by_date.get(day, {"completed": 0, "total": 0})
            total = counts["total"]
            completed = counts["completed"]
            score = completed / total if total > 0 else 0.0
            series.append(
                {
                    "date": day,
                    "score": round(score, 3),
                    "completed": completed,
                    "expected": total,
                }
            )

        return series

    async def _compute_obligation_completion_rate(self, patient_id: UUID) -> float:
        """Return 30-day completion rate for obligation adherence logs."""
        cutoff = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        logs = await self._execute(
            self.db.table("adherence_logs")
            .select("status")
            .eq("patient_id", str(patient_id))
            .eq("target_type", "obligation")
            .gte("logged_at", cutoff)
        )
        rows = cast(list[dict[str, Any]], logs.data or [])
        if not rows:
            return 0.0

        completed = sum(1 for row in rows if row.get("status") == "completed")
        return completed / len(rows)

    def _is_invite_expired(self, expires_at: Any, now: datetime) -> bool:
        """Return True when invite expiry is in the past."""
        if not isinstance(expires_at, str):
            return False

        try:
            return datetime.fromisoformat(expires_at.replace("Z", "+00:00")) <= now
        except ValueError:
            logger.warning("Invalid invite_expires_at value on care_teams row")
            return False

    def _derive_invite_lifecycle_state(
        self,
        *,
        status: str,
        has_patient: bool,
        is_expired: bool,
    ) -> str:
        """Map invite row fields to clinician-facing lifecycle state labels."""
        if status == "pending" and not has_patient and not is_expired:
            return "active"
        if status == "active" and has_patient:
            return "claimed"
        if has_patient and status != "pending":
            return "claimed"
        return "inactive"

    def _last_activity_age_days(self, last_activity: str) -> float | None:
        """Parse an activity string like 'Logged medication 2h ago' into days."""
        match = re.search(r"(\d+)([mhd])\s+ago", last_activity)
        if not match:
            return None

        value = int(match.group(1))
        unit = match.group(2)
        if unit == "m":
            return value / (60 * 24)
        if unit == "h":
            return value / 24
        return float(value)

    async def _execute(
        self,
        query: Any,
        *,
        operation: str = "Supabase query",
        retry_transient: bool = False,
    ) -> Any:
        """Run blocking Supabase execute() off the event loop with shared retry semantics."""
        if callable(query) and not hasattr(query, "execute"):
            return await execute_async(
                self,
                query,
                operation=operation,
                retry_transient=retry_transient,
            )
        return await execute_async(
            self,
            lambda _db: query,
            operation=operation,
            retry_transient=False,
        )
