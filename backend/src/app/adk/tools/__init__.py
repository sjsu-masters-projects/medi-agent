"""Tools an agent may call, and the scoping that decides what they may reach.

Every tool here is read-only or candidate-only. None writes an approved clinical fact:
that authority lives in `clinical_fact_service.approve` and
`clinical_reconciliation_service.decide`, neither of which is reachable from a tool.
"""

from app.adk.tools.scoping import (
    PATIENT_ID_STATE_KEY,
    PatientScopeError,
    require_patient_id,
)
from app.adk.tools.triage_decision import (
    TRIAGE_DECISION_STATE_KEY,
    VALID_INTENTS,
    VALID_URGENCIES,
    submit_triage_decision,
)

__all__ = [
    "PATIENT_ID_STATE_KEY",
    "TRIAGE_DECISION_STATE_KEY",
    "VALID_INTENTS",
    "VALID_URGENCIES",
    "PatientScopeError",
    "require_patient_id",
    "submit_triage_decision",
]
