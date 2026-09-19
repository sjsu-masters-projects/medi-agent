"""Follow-up worker: symptom capture and the reply the patient reads.

Collects and schedules follow-up only — it cannot alter a medication or approve a
clinical fact, which is the authority boundary recorded in `.agent/ARCHITECTURE.md`.

Framework-free on purpose, for the same reason `app.safety` is: the agent runtime is
being replaced, and a symptom report written to a patient's record should not depend on
which runtime happened to be in fashion when it was captured.
"""

from app.followup.followup_copy import FOLLOWUP_COPY
from app.followup.models import SymptomExtractionResult
from app.followup.service import SEVERE_THRESHOLD, SymptomAnalysis, analyse_symptom

__all__ = [
    "FOLLOWUP_COPY",
    "SEVERE_THRESHOLD",
    "SymptomAnalysis",
    "SymptomExtractionResult",
    "analyse_symptom",
]
