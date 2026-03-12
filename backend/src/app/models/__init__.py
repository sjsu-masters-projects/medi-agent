"""All Pydantic schemas — import from here."""

# Enums (single source of truth for categorical values)
from app.models.adherence import AdherenceLog, AdherenceLogRead, AdherenceStats
from app.models.adr import ADRAssessmentRead, MedWatchDraft
from app.models.appointment import AppointmentCreate, AppointmentRead, AppointmentUpdate
from app.models.care_team import CareTeamCreate, CareTeamRead
from app.models.chat import ChatMessage, ChatMessageCreate
from app.models.clinician import ClinicianCreate, ClinicianRead, ClinicianUpdate
from app.models.clinician_message import ClinicianMessageCreate, ClinicianMessageRead

# Schemas
from app.models.common import ErrorResponse, PaginatedResponse, SuccessResponse, TimestampMixin
from app.models.condition import AllergyCreate, AllergyRead, ConditionCreate, ConditionRead
from app.models.document import DocumentRead, DocumentUpload
from app.models.enums import (
    AdherenceStatus,
    AdherenceTargetType,
    ADRStatus,
    AllergySeverity,
    AppointmentStatus,
    AppointmentType,
    CareTeamStatus,
    ChatRole,
    ClinicianRole,
    DocumentType,
    DocumentVisibility,
    Gender,
    Language,
    MedicationRoute,
    MedWatchStatus,
    MessageChannel,
    NaranjoCausality,
    NotificationType,
    ObligationType,
    UploaderRole,
)
from app.models.medication import MedicationCreate, MedicationRead, MedicationUpdate
from app.models.notification import NotificationCreate, NotificationRead
from app.models.obligation import ObligationCreate, ObligationRead, ObligationUpdate
from app.models.patient import PatientCreate, PatientRead, PatientUpdate
from app.models.symptom import SymptomReportCreate, SymptomReportRead

__all__ = [
    # Enums
    "ADRStatus",
    "AdherenceStatus",
    "AdherenceTargetType",
    "AllergySeverity",
    "AppointmentStatus",
    "AppointmentType",
    "CareTeamStatus",
    "ChatRole",
    "ClinicianRole",
    "DocumentType",
    "DocumentVisibility",
    "Gender",
    "Language",
    "MedWatchStatus",
    "MedicationRoute",
    "MessageChannel",
    "NaranjoCausality",
    "NotificationType",
    "ObligationType",
    "UploaderRole",
    # Common
    "ErrorResponse",
    "PaginatedResponse",
    "SuccessResponse",
    "TimestampMixin",
    # Patient
    "PatientCreate",
    "PatientRead",
    "PatientUpdate",
    # Clinician
    "ClinicianCreate",
    "ClinicianRead",
    "ClinicianUpdate",
    # Care Team
    "CareTeamCreate",
    "CareTeamRead",
    # Conditions & Allergies
    "ConditionCreate",
    "ConditionRead",
    "AllergyCreate",
    "AllergyRead",
    # Document
    "DocumentRead",
    "DocumentUpload",
    # Medication
    "MedicationCreate",
    "MedicationRead",
    "MedicationUpdate",
    # Obligation
    "ObligationCreate",
    "ObligationRead",
    "ObligationUpdate",
    # Adherence
    "AdherenceLog",
    "AdherenceLogRead",
    "AdherenceStats",
    # Symptom
    "SymptomReportCreate",
    "SymptomReportRead",
    # ADR
    "ADRAssessmentRead",
    "MedWatchDraft",
    # Appointment
    "AppointmentCreate",
    "AppointmentRead",
    "AppointmentUpdate",
    # Chat
    "ChatMessage",
    "ChatMessageCreate",
    # Notification
    "NotificationCreate",
    "NotificationRead",
    # Clinician Messages
    "ClinicianMessageCreate",
    "ClinicianMessageRead",
]
