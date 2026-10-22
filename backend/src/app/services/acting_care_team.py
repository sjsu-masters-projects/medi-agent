"""The care team a clinician acts for when they hold several links to one patient."""

from __future__ import annotations

from typing import Any

from app.core import authorization_reasons as reasons
from app.core.exceptions import AuthorizationError, ValidationError
from app.services.care_team_access import PatientAccess

CARE_TEAM_REQUIRED = "CARE_TEAM_REQUIRED"


def acting_care_team(access: PatientAccess, requested: Any = None) -> str:
    """The exact link a new record is stamped with.

    A named link must be one of the clinician's own active links to the patient. With no name,
    a clinician with one link acts for it; with several, the caller must choose.
    """
    if not access:
        raise AuthorizationError(
            "You are not assigned to this patient",
            reason_code=reasons.NO_CARE_TEAM_ASSIGNMENT,
            actor_id=access.clinician_id,
            actor_role="clinician",
            target_type="patient",
            target_id=access.patient_id,
        )
    if requested:
        if not access.owns(requested):
            raise AuthorizationError(
                "You are not assigned to this patient",
                reason_code=reasons.NO_CARE_TEAM_ASSIGNMENT,
                actor_id=access.clinician_id,
                actor_role="clinician",
                target_type="patient",
                target_id=access.patient_id,
            )
        return str(requested)
    if len(access.team_ids) > 1:
        raise ValidationError(
            "Choose which of your care teams this is for.", code=CARE_TEAM_REQUIRED
        )
    return next(iter(access.team_ids))
