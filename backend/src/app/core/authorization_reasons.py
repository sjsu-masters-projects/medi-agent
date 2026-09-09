"""Reason codes for authorization denials.

Every denial is recorded with one of these codes so a refused access attempt can be
counted and investigated, not merely blocked. The codes are the contract declared by
`negative_access_cases` in the canonical synthetic fixture; keep the two in step.

`AUTHORIZATION_ERROR` remains the response `code` for every denial. These values travel
alongside it as `reason_code`, so a denial stays opaque to the caller in the ways that
matter while remaining precise in the audit trail.
"""

from __future__ import annotations

from typing import Final

# Care-team authorization
NO_CARE_TEAM_ASSIGNMENT: Final = "NO_CARE_TEAM_ASSIGNMENT"
NO_CARE_TEAM_ASSIGNMENT_CROSS_CLINIC: Final = "NO_CARE_TEAM_ASSIGNMENT_CROSS_CLINIC"
SAME_CLINIC_BUT_NO_CARE_TEAM_ASSIGNMENT: Final = "SAME_CLINIC_BUT_NO_CARE_TEAM_ASSIGNMENT"
ASSIGNMENT_EXISTS_FOR_DIFFERENT_PATIENT_ONLY: Final = "ASSIGNMENT_EXISTS_FOR_DIFFERENT_PATIENT_ONLY"

# Role and scope
ROLE_LACKS_CLINICAL_SCOPE: Final = "ROLE_LACKS_CLINICAL_SCOPE"
PATIENT_SCOPE_SELF_ONLY: Final = "PATIENT_SCOPE_SELF_ONLY"
PROXY_SCOPED_TO_SINGLE_PATIENT: Final = "PROXY_SCOPED_TO_SINGLE_PATIENT"
ADMIN_SCOPE_ONLY: Final = "ADMIN_SCOPE_ONLY"
UNSUPPORTED_ROLE: Final = "UNSUPPORTED_ROLE"

# Session and step-up
MFA_REQUIRED: Final = "MFA_REQUIRED"

# Approval policy
SELF_APPROVAL_FORBIDDEN: Final = "SELF_APPROVAL_FORBIDDEN"
MODEL_PROPOSER_FORBIDDEN: Final = "MODEL_PROPOSER_FORBIDDEN"

# SMART / interoperability
SMART_HANDOFF_INVALID: Final = "SMART_HANDOFF_INVALID"
SMART_HANDOFF_OTHER_CLINICIAN: Final = "SMART_HANDOFF_OTHER_CLINICIAN"

# Internal transport
CRON_AUTH_INVALID: Final = "CRON_AUTH_INVALID"

# Fallback for a denial that has not yet been classified.
UNSPECIFIED: Final = "UNSPECIFIED"

ALL_REASON_CODES: Final[frozenset[str]] = frozenset(
    {
        NO_CARE_TEAM_ASSIGNMENT,
        NO_CARE_TEAM_ASSIGNMENT_CROSS_CLINIC,
        SAME_CLINIC_BUT_NO_CARE_TEAM_ASSIGNMENT,
        ASSIGNMENT_EXISTS_FOR_DIFFERENT_PATIENT_ONLY,
        ROLE_LACKS_CLINICAL_SCOPE,
        PATIENT_SCOPE_SELF_ONLY,
        PROXY_SCOPED_TO_SINGLE_PATIENT,
        ADMIN_SCOPE_ONLY,
        UNSUPPORTED_ROLE,
        MFA_REQUIRED,
        SELF_APPROVAL_FORBIDDEN,
        MODEL_PROPOSER_FORBIDDEN,
        SMART_HANDOFF_INVALID,
        SMART_HANDOFF_OTHER_CLINICIAN,
        CRON_AUTH_INVALID,
        UNSPECIFIED,
    }
)
