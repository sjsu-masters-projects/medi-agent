"""Risk score calculation service.

Calculates a patient's composite risk level (🟢 low / 🟡 medium / 🔴 high)
from three independent signals:

1. Adherence score (from adherence_logs over 30-day window)
2. Open ADR assessments (adr_assessments where status='open' or 'draft')
3. Recent symptom severity (max severity in last 7 days from symptom_reports)

Algorithm:
    HIGH   → adherence < 0.60  OR  open_adr_count >= 1  OR  max_severity >= 8
    MEDIUM → adherence 0.60-0.79  OR  max_severity >= 5
    LOW    → adherence >= 0.80  AND  no open ADRs  AND  max_severity < 5
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from supabase import Client

from app.models.dashboard import PatientRiskData, RiskLevel

logger = logging.getLogger(__name__)

# Risk thresholds — see module docstring for rationale
_HIGH_ADHERENCE_THRESHOLD = 0.60
_MEDIUM_ADHERENCE_THRESHOLD = 0.80
_HIGH_SEVERITY_THRESHOLD = 8
_MEDIUM_SEVERITY_THRESHOLD = 5
_RECENT_SYMPTOM_DAYS = 7


class RiskScoreService:
    """Computes patient risk scores from adherence, ADR, and symptom data.

    Single responsibility: risk calculation only.
    All scoring thresholds are module-level constants for easy auditing.
    """

    def __init__(self, db: Client) -> None:
        self.db = db

    def calculate_risk_level(
        self,
        adherence_score: float,
        open_adr_count: int,
        recent_symptom_severity: int,
    ) -> RiskLevel:
        """Pure function — derive risk level from three signals.

        Args:
            adherence_score: 0.0–1.0 (from AdherenceService)
            open_adr_count: number of unresolved ADR assessments
            recent_symptom_severity: max severity (1–10) in last 7 days

        Returns:
            "high", "medium", or "low"
        """
        # HIGH: any single critical signal triggers high risk
        if (
            adherence_score < _HIGH_ADHERENCE_THRESHOLD
            or open_adr_count >= 1
            or recent_symptom_severity >= _HIGH_SEVERITY_THRESHOLD
        ):
            return "high"

        # MEDIUM: borderline adherence or significant symptom severity
        if (
            adherence_score < _MEDIUM_ADHERENCE_THRESHOLD
            or recent_symptom_severity >= _MEDIUM_SEVERITY_THRESHOLD
        ):
            return "medium"

        return "low"

    async def get_patient_risk(self, patient_id: UUID) -> PatientRiskData:
        """Fetch signals from DB and compute risk level for a single patient.

        Makes three focused DB queries:
        1. Patient name / basic profile
        2. Adherence score (last 30 days)
        3. ADR assessments (open/draft)
        4. Recent symptom reports (last 7 days)
        5. Active medication count
        """
        # ── 1. Patient profile ─────────────────────────
        patient_row = (
            self.db.table("patients")
            .select("id, first_name, last_name, email")
            .eq("id", str(patient_id))
            .single()
            .execute()
        )
        patient = cast(dict[str, Any], patient_row.data or {})
        first_name = patient.get("first_name", "Unknown")
        last_name = patient.get("last_name", "")

        # ── 2. Adherence score ─────────────────────────
        adherence_score = await self._fetch_adherence_score(patient_id)

        # ── 3. Open ADR count ──────────────────────────
        open_adr_count = await self._fetch_open_adr_count(patient_id)

        # ── 4. Recent symptom severity ─────────────────
        recent_symptom_severity = await self._fetch_recent_symptom_severity(patient_id)

        # ── 5. Active med count ────────────────────────
        active_med_count = await self._fetch_active_med_count(patient_id)

        # ── 6. Compute risk ────────────────────────────
        risk_level = self.calculate_risk_level(
            adherence_score, open_adr_count, recent_symptom_severity
        )

        # ── 7. Build last activity string ──────────────
        last_activity = await self._fetch_last_activity(patient_id)

        return PatientRiskData(
            patient_id=patient_id,
            first_name=first_name,
            last_name=last_name,
            risk_level=risk_level,
            adherence_score=adherence_score,
            open_adr_count=open_adr_count,
            active_med_count=active_med_count,
            recent_symptom_severity=recent_symptom_severity,
            last_activity=last_activity,
        )

    # ── Private helpers ──────────────────────────────────────────────────────

    async def _fetch_adherence_score(self, patient_id: UUID) -> float:
        """Return 30-day overall adherence score (0.0–1.0)."""
        cutoff = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        logs = (
            self.db.table("adherence_logs")
            .select("status")
            .eq("patient_id", str(patient_id))
            .gte("logged_at", cutoff)
            .execute()
        )
        log_data = cast(list[dict[str, Any]], logs.data or [])
        if not log_data:
            return 0.0

        completed = sum(1 for log in log_data if log.get("status") == "completed")
        total = len(log_data)
        return completed / total if total > 0 else 0.0

    async def _fetch_open_adr_count(self, patient_id: UUID) -> int:
        """Count ADR assessments that need clinician review."""
        result = (
            self.db.table("adr_assessments")
            .select("id", count="exact")
            .eq("patient_id", str(patient_id))
            .in_("status", ["open", "draft"])
            .execute()
        )
        return result.count or 0

    async def _fetch_recent_symptom_severity(self, patient_id: UUID) -> int:
        """Return max symptom severity in last 7 days (0 if none)."""
        cutoff = (datetime.now(UTC) - timedelta(days=_RECENT_SYMPTOM_DAYS)).isoformat()
        result = (
            self.db.table("symptom_reports")
            .select("severity")
            .eq("patient_id", str(patient_id))
            .gte("created_at", cutoff)
            .execute()
        )
        rows = cast(list[dict[str, Any]], result.data or [])
        if not rows:
            return 0
        return max(int(row.get("severity", 0)) for row in rows)

    async def _fetch_active_med_count(self, patient_id: UUID) -> int:
        """Count active medications."""
        result = (
            self.db.table("medications")
            .select("id", count="exact")
            .eq("patient_id", str(patient_id))
            .eq("is_active", True)
            .execute()
        )
        return result.count or 0

    async def _fetch_last_activity(self, patient_id: UUID) -> str:
        """Return a human-readable last activity string."""
        # Check most recent adherence log
        logs = (
            self.db.table("adherence_logs")
            .select("logged_at, status, target_type")
            .eq("patient_id", str(patient_id))
            .order("logged_at", desc=True)
            .limit(1)
            .execute()
        )
        log_rows = cast(list[dict[str, Any]], logs.data or [])

        # Check most recent symptom report
        symptoms = (
            self.db.table("symptom_reports")
            .select("created_at, symptom")
            .eq("patient_id", str(patient_id))
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        symptom_rows = cast(list[dict[str, Any]], symptoms.data or [])

        latest_log_time: datetime | None = None
        latest_symptom_time: datetime | None = None

        if log_rows:
            try:
                latest_log_time = datetime.fromisoformat(
                    log_rows[0]["logged_at"].replace("Z", "+00:00")
                )
            except (ValueError, KeyError) as exc:
                logger.debug("Unable to parse latest adherence log timestamp: %s", exc)

        if symptom_rows:
            try:
                latest_symptom_time = datetime.fromisoformat(
                    symptom_rows[0]["created_at"].replace("Z", "+00:00")
                )
            except (ValueError, KeyError) as exc:
                logger.debug("Unable to parse latest symptom report timestamp: %s", exc)

        now = datetime.now(UTC)

        if latest_symptom_time and (
            not latest_log_time or latest_symptom_time > latest_log_time
        ):
            symptom_name = symptom_rows[0].get("symptom", "symptom") if symptom_rows else "symptom"
            delta = now - latest_symptom_time
            return f"Reported '{symptom_name}' {_humanize_delta(delta)}"

        if latest_log_time:
            delta = now - latest_log_time
            log_type = log_rows[0].get("target_type", "medication") if log_rows else "medication"
            return f"Logged {log_type} {_humanize_delta(delta)}"

        return "No recent activity"


def _humanize_delta(delta: timedelta) -> str:
    """Convert timedelta to a human-readable string like '2h ago'."""
    seconds = int(delta.total_seconds())
    if seconds < 3600:
        minutes = max(1, seconds // 60)
        return f"{minutes}m ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours}h ago"
    days = seconds // 86400
    return f"{days}d ago"
