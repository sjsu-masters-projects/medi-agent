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

from app.core.exceptions import AuthorizationError, NotFoundError

logger = logging.getLogger(__name__)


class ClinicianService:
    """Clinician-scoped operations. All methods require the clinician's user ID."""

    def __init__(self, db: Client) -> None:
        self.db = db

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

        result = await self._execute(
            self.db.table("clinicians").update(clean).eq("id", str(clinician_id))
        )
        if not result.data:
            raise NotFoundError("Clinician", str(clinician_id))
        return result.data[0]

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
        assignment = await self._execute(
            self.db.table("care_teams")
            .select("id")
            .eq("clinician_id", str(clinician_id))
            .eq("patient_id", str(patient_id))
            .eq("status", "active")
        )
        if not assignment.data:
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

        result = await self._execute(
            self.db.table("care_teams").insert(
                {
                    "clinician_id": str(clinician_id),
                    "invite_code": code,
                    "status": "pending",
                    "role": "provider",
                }
            )
        )
        if not result.data:
            raise Exception("Failed to generate invite code")

        return {
            "invite_code": code,
            "care_team_id": cast(list[dict[str, Any]], result.data)[0]["id"],
        }

    # ── Dashboard ────────────────────────────────────────

    async def get_dashboard_data(
        self,
        clinician_id: UUID,
        *,
        sort_by: str = "risk",
        sort_order: str = "desc",
        risk_filter: str | None = None,
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
        for pid, result in zip(patient_ids, risk_results, strict=False):
            if isinstance(result, BaseException):
                logger.warning(
                    "Failed to compute risk for patient_id=%s",
                    pid,
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

    async def get_patient_deep_dive(self, clinician_id: UUID, patient_id: UUID) -> Any:
        """Aggregate all patient data for the Patient Deep Dive view.

        Security: verifies care_team assignment before fetching.
        """
        assignment = await self._execute(
            self.db.table("care_teams")
            .select("id")
            .eq("clinician_id", str(clinician_id))
            .eq("patient_id", str(patient_id))
            .eq("status", "active")
        )
        if not assignment.data:
            raise AuthorizationError("You are not assigned to this patient")

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
                "created_at, uploaded_by_role, clinician_annotation"
            )
            .eq("patient_id", pid)
            .order("created_at", desc=True)
        )
        documents = cast(list[dict[str, Any]], docs.data or [])

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
                "Failed to compute risk for deep dive patient_id=%s", patient_id, exc_info=exc
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

    async def set_patient_obligation(
        self, clinician_id: UUID, patient_id: UUID, obligation_data: dict[str, Any]
    ) -> Any:
        """Create an obligation for a patient on behalf of a clinician."""
        assignment = await self._execute(
            self.db.table("care_teams")
            .select("id")
            .eq("clinician_id", str(clinician_id))
            .eq("patient_id", str(patient_id))
            .eq("status", "active")
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

        result = await self._execute(self.db.table("obligations").insert(row))
        if not result.data:
            raise Exception("Failed to create obligation")

        return cast(list[dict[str, Any]], result.data)[0]

    async def save_document_annotation(
        self, clinician_id: UUID, patient_id: UUID, document_id: UUID, annotation_text: str
    ) -> Any:
        """Save clinician annotation on a document.

        Security: verifies both care_team assignment AND document belongs to patient.
        """
        assignment = await self._execute(
            self.db.table("care_teams")
            .select("id")
            .eq("clinician_id", str(clinician_id))
            .eq("patient_id", str(patient_id))
            .eq("status", "active")
        )
        if not assignment.data:
            raise AuthorizationError("You are not assigned to this patient")

        doc_check = await self._execute(
            self.db.table("documents")
            .select("id")
            .eq("id", str(document_id))
            .eq("patient_id", str(patient_id))
        )
        if not doc_check.data:
            raise NotFoundError("Document", str(document_id))

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

    # ── Private helpers ──────────────────────────────────────────────────────

    async def _get_assigned_patient_ids(self, clinician_id: UUID) -> list[UUID]:
        """Return list of patient UUIDs assigned to this clinician."""
        result = await self._execute(
            self.db.table("care_teams")
            .select("patient_id")
            .eq("clinician_id", str(clinician_id))
            .eq("status", "active")
        )
        rows = cast(list[dict[str, Any]], result.data or [])
        return [UUID(row["patient_id"]) for row in rows if row.get("patient_id")]

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

    async def _execute(self, query: Any) -> Any:
        """Run blocking Supabase execute() off the event loop."""
        return await asyncio.to_thread(query.execute)
