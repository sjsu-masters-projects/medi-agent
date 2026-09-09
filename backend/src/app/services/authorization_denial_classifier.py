"""Classify why a care-team authorization check failed.

Enforcement only needs to know that no active assignment exists. The audit trail needs
to know which kind of failure it was: a clinician reaching across clinics is a different
signal from one who simply is not on a patient's care team, and only the first suggests
probing.

A patient has no clinic column of its own; the clinic is derived from the clinicians on
the patient's active care team. That means classification costs two extra reads, which is
acceptable on a path that should be rare — and if it were not rare, that is exactly what
the audit trail exists to reveal.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, cast

from supabase import Client

from app.core.authorization_reasons import (
    ASSIGNMENT_EXISTS_FOR_DIFFERENT_PATIENT_ONLY,
    NO_CARE_TEAM_ASSIGNMENT,
    NO_CARE_TEAM_ASSIGNMENT_CROSS_CLINIC,
    SAME_CLINIC_BUT_NO_CARE_TEAM_ASSIGNMENT,
)

logger = logging.getLogger(__name__)


async def classify_care_team_denial(
    db: Client,
    clinician_id: str,
    patient_id: str,
) -> str:
    """Return the reason code for a failed care-team authorization check.

    Never raises: an unclassifiable denial still has to be recorded, so any failure
    degrades to the generic `NO_CARE_TEAM_ASSIGNMENT` rather than losing the event.
    """
    try:
        actor_clinic = await _actor_clinic_id(db, clinician_id)
        patient_clinics = await _patient_clinic_ids(db, patient_id)

        # Cross-clinic first: it is the strongest signal and outranks the actor holding
        # assignments elsewhere.
        if actor_clinic and patient_clinics and actor_clinic not in patient_clinics:
            return NO_CARE_TEAM_ASSIGNMENT_CROSS_CLINIC

        if await _has_any_active_assignment(db, clinician_id):
            return ASSIGNMENT_EXISTS_FOR_DIFFERENT_PATIENT_ONLY

        if actor_clinic and actor_clinic in patient_clinics:
            return SAME_CLINIC_BUT_NO_CARE_TEAM_ASSIGNMENT

        return NO_CARE_TEAM_ASSIGNMENT
    except Exception:
        logger.warning(
            "Could not classify care-team denial for clinician=%s patient=%s",
            clinician_id,
            patient_id,
            exc_info=True,
        )
        return NO_CARE_TEAM_ASSIGNMENT


async def _actor_clinic_id(db: Client, clinician_id: str) -> str | None:
    result = await asyncio.to_thread(
        db.table("clinicians").select("clinic_id").eq("id", clinician_id).limit(1).execute
    )
    rows = cast(list[dict[str, Any]], result.data or [])
    return str(rows[0]["clinic_id"]) if rows and rows[0].get("clinic_id") else None


async def _patient_clinic_ids(db: Client, patient_id: str) -> set[str]:
    """Clinics reachable through the patient's active care team."""
    result = await asyncio.to_thread(
        db.table("care_teams")
        .select("clinicians(clinic_id)")
        .eq("patient_id", patient_id)
        .eq("status", "active")
        .execute
    )
    clinics: set[str] = set()
    for row in cast(list[dict[str, Any]], result.data or []):
        clinician = cast(dict[str, Any], row.get("clinicians") or {})
        clinic_id = clinician.get("clinic_id")
        if clinic_id:
            clinics.add(str(clinic_id))
    return clinics


async def _has_any_active_assignment(db: Client, clinician_id: str) -> bool:
    result = await asyncio.to_thread(
        db.table("care_teams")
        .select("id")
        .eq("clinician_id", clinician_id)
        .eq("status", "active")
        .limit(1)
        .execute
    )
    return bool(result.data)
