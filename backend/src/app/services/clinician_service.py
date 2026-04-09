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

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.core.exceptions import AuthorizationError, NotFoundError

logger = logging.getLogger(__name__)


class ClinicianService:
    """Clinician-scoped operations. All methods require the clinician's user ID."""

    def __init__(self, db: Client) -> None:
        self.db = db

    # ── Profile ─────────────────────────────────────

    async def get_profile(self, clinician_id: UUID) -> Any:
        """Fetch the clinician's own profile."""
        result = (
            self.db.table("clinicians").select("*").eq("id", str(clinician_id)).single().execute()
        )
        if not result.data:
            raise NotFoundError("Clinician", str(clinician_id))
        return result.data

    async def update_profile(self, clinician_id: UUID, updates: dict[str, Any]) -> Any:
        """Partial update for the clinician's own profile."""
        clean = {key: value for key, value in updates.items() if value is not None}
        if not clean:
            return await self.get_profile(clinician_id)

        result = self.db.table("clinicians").update(clean).eq("id", str(clinician_id)).execute()
        if not result.data:
            raise NotFoundError("Clinician", str(clinician_id))
        return result.data[0]

    # ── Patient List ────────────────────────────────────

    async def get_patients(self, clinician_id: UUID) -> Any:
        """List all patients assigned to this clinician via active care teams."""
        result = (
            self.db.table("care_teams")
            .select("*, patients(id, email, first_name, last_name, date_of_birth, avatar_url)")
            .eq("clinician_id", str(clinician_id))
            .eq("status", "active")
            .execute()
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
        assignment = (
            self.db.table("care_teams")
            .select("id")
            .eq("clinician_id", str(clinician_id))
            .eq("patient_id", str(patient_id))
            .eq("status", "active")
            .execute()
        )
        if not assignment.data:
            raise AuthorizationError("You are not assigned to this patient")

        result = self.db.table("patients").select("*").eq("id", str(patient_id)).single().execute()
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

        result = (
            self.db.table("care_teams")
            .insert(
                {
                    "clinician_id": str(clinician_id),
                    "invite_code": code,
                    "status": "pending",
                    "role": "provider",
                }
            )
            .execute()
        )
        if not result.data:
            raise Exception("Failed to generate invite code")

        return {
            "invite_code": code,
            "care_team_id": cast(list[dict[str, Any]], result.data)[0]["id"],
        }

    # ── Dashboard ────────────────────────────────────────

    async def get_dashboard_data(self, clinician_id: UUID) -> Any:
        """Aggregate risk data for all assigned patients.

        Delegates per-patient risk calculation to RiskScoreService.
        Returns DashboardResponse-compatible dict.
        """
        from app.services.risk_score_service import RiskScoreService

        risk_service = RiskScoreService(self.db)
        patient_ids = await self._get_assigned_patient_ids(clinician_id)
        medwatch_count = await self._get_pending_medwatch_count(patient_ids)

        risk_data = []
        for pid in patient_ids:
            try:
                patient_risk = await risk_service.get_patient_risk(pid)
                risk_data.append(patient_risk.model_dump())
            except Exception:
                logger.warning("Failed to compute risk for patient %s", pid)

        high = sum(1 for p in risk_data if p["risk_level"] == "high")
        medium = sum(1 for p in risk_data if p["risk_level"] == "medium")
        low_count = sum(1 for p in risk_data if p["risk_level"] == "low")

        return {
            "patients": risk_data,
            "total": len(risk_data),
            "high_risk": high,
            "medium_risk": medium,
            "low_risk": low_count,
            "medwatch_pending": medwatch_count,
        }

    async def get_patient_deep_dive(self, clinician_id: UUID, patient_id: UUID) -> Any:
        """Aggregate all patient data for the Patient Deep Dive view.

        Security: verifies care_team assignment before fetching.
        """
        assignment = (
            self.db.table("care_teams")
            .select("id")
            .eq("clinician_id", str(clinician_id))
            .eq("patient_id", str(patient_id))
            .eq("status", "active")
            .execute()
        )
        if not assignment.data:
            raise AuthorizationError("You are not assigned to this patient")

        pid = str(patient_id)

        patient_row = self.db.table("patients").select("*").eq("id", pid).single().execute()
        if not patient_row.data:
            raise NotFoundError("Patient", pid)
        patient = cast(dict[str, Any], patient_row.data)

        meds = (
            self.db.table("medications").select("*").eq("patient_id", pid).eq("is_active", True).execute()
        )
        medications = cast(list[dict[str, Any]], meds.data or [])

        adherence_series = await self._build_adherence_series(patient_id)

        symptoms = (
            self.db.table("symptom_reports")
            .select("*")
            .eq("patient_id", pid)
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )
        symptom_reports = cast(list[dict[str, Any]], symptoms.data or [])

        chats = (
            self.db.table("chat_messages")
            .select("role, content, created_at, audio_url")
            .eq("patient_id", pid)
            .order("created_at", desc=True)
            .limit(30)
            .execute()
        )
        chat_messages = cast(list[dict[str, Any]], chats.data or [])

        conds = self.db.table("conditions").select("*").eq("patient_id", pid).execute()
        conditions = cast(list[dict[str, Any]], conds.data or [])

        allergies_res = self.db.table("allergies").select("*").eq("patient_id", pid).execute()
        allergies = cast(list[dict[str, Any]], allergies_res.data or [])

        docs = (
            self.db.table("documents")
            .select(
                "id, file_name, document_type, parse_status, ai_summary, "
                "created_at, uploaded_by_role, clinician_annotation"
            )
            .eq("patient_id", pid)
            .order("created_at", desc=True)
            .execute()
        )
        documents = cast(list[dict[str, Any]], docs.data or [])

        soap_res = (
            self.db.table("soap_notes")
            .select("*")
            .eq("patient_id", pid)
            .order("generated_at", desc=True)
            .limit(1)
            .execute()
        )
        soap_rows = cast(list[dict[str, Any]], soap_res.data or [])
        latest_soap_note = soap_rows[0] if soap_rows else None

        from app.services.risk_score_service import RiskScoreService

        risk_service = RiskScoreService(self.db)
        try:
            risk_data = await risk_service.get_patient_risk(patient_id)
            risk_level = risk_data.risk_level
            adherence_score = risk_data.adherence_score
        except Exception:
            risk_level = "low"
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
        }

    async def set_patient_obligation(
        self, clinician_id: UUID, patient_id: UUID, obligation_data: dict[str, Any]
    ) -> Any:
        """Create an obligation for a patient on behalf of a clinician."""
        assignment = (
            self.db.table("care_teams")
            .select("id")
            .eq("clinician_id", str(clinician_id))
            .eq("patient_id", str(patient_id))
            .eq("status", "active")
            .execute()
        )
        if not assignment.data:
            raise AuthorizationError("You are not assigned to this patient")

        care_team_id = cast(list[dict[str, Any]], assignment.data)[0]["id"]

        row = {
            "patient_id": str(patient_id),
            "set_by_care_team_id": care_team_id,
            "obligation_type": obligation_data["obligation_type"],
            "description": obligation_data["description"],
            "frequency": obligation_data["frequency"],
            "notes": obligation_data.get("notes"),
            "is_active": True,
        }

        result = self.db.table("obligations").insert(row).execute()
        if not result.data:
            raise Exception("Failed to create obligation")

        return cast(list[dict[str, Any]], result.data)[0]

    async def save_document_annotation(
        self, clinician_id: UUID, patient_id: UUID, document_id: UUID, annotation_text: str
    ) -> Any:
        """Save clinician annotation on a document.

        Security: verifies both care_team assignment AND document belongs to patient.
        """
        assignment = (
            self.db.table("care_teams")
            .select("id")
            .eq("clinician_id", str(clinician_id))
            .eq("patient_id", str(patient_id))
            .eq("status", "active")
            .execute()
        )
        if not assignment.data:
            raise AuthorizationError("You are not assigned to this patient")

        doc_check = (
            self.db.table("documents")
            .select("id")
            .eq("id", str(document_id))
            .eq("patient_id", str(patient_id))
            .execute()
        )
        if not doc_check.data:
            raise NotFoundError("Document", str(document_id))

        self.db.table("documents").update(
            {
                "clinician_annotation": annotation_text,
                "annotation_by": str(clinician_id),
            }
        ).eq("id", str(document_id)).execute()

        return {"status": "saved", "document_id": str(document_id)}

    # ── Private helpers ──────────────────────────────────────────────────────

    async def _get_assigned_patient_ids(self, clinician_id: UUID) -> list[UUID]:
        """Return list of patient UUIDs assigned to this clinician."""
        result = (
            self.db.table("care_teams")
            .select("patient_id")
            .eq("clinician_id", str(clinician_id))
            .eq("status", "active")
            .execute()
        )
        rows = cast(list[dict[str, Any]], result.data or [])
        return [UUID(row["patient_id"]) for row in rows if row.get("patient_id")]

    async def _get_pending_medwatch_count(self, patient_ids: list[UUID]) -> int:
        """Count draft/open MedWatch assessments across all assigned patients."""
        if not patient_ids:
            return 0
        result = (
            self.db.table("adr_assessments")
            .select("id", count="exact")
            .in_("patient_id", [str(pid) for pid in patient_ids])
            .in_("status", ["draft", "open"])
            .execute()
        )
        return result.count or 0

    async def _build_adherence_series(self, patient_id: UUID) -> list[dict[str, Any]]:
        """Build a 30-day daily adherence series for Recharts LineChart."""
        cutoff = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        logs = (
            self.db.table("adherence_logs")
            .select("status, target_type, logged_at")
            .eq("patient_id", str(patient_id))
            .gte("logged_at", cutoff)
            .execute()
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
