"""Centralized enums — single source of truth for all categorical values."""

from enum import StrEnum

# ── Users ──────────────────────────────────────────


class Language(StrEnum):
    EN = "en-US"
    ES = "es-MX"

    @classmethod
    def _missing_(cls, value: object) -> "Language | None":
        if not isinstance(value, str):
            return None

        normalized = value.strip().lower().replace("_", "-")
        aliases = {
            "en": cls.EN,
            "en-us": cls.EN,
            "es": cls.ES,
            "es-mx": cls.ES,
        }
        return aliases.get(normalized)

    @property
    def is_spanish(self) -> bool:
        return self is Language.ES


def coerce_language(value: object, fallback: Language = Language.EN) -> Language:
    try:
        return value if isinstance(value, Language) else Language(value)
    except ValueError:
        return fallback


# Locale-first aliases for future expansion.
Locale = Language
coerce_locale = coerce_language


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"
    PREFER_NOT_TO_SAY = "prefer_not_to_say"


class ClinicianRole(StrEnum):
    PROVIDER = "provider"
    ADMIN = "admin"
    NURSE = "nurse"


class ClinicStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


# ── Care Team ─────────────────────────────────────


class CareTeamStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    TRANSFERRED = "transferred"


# ── Documents ──────────────────────────────────────


class DocumentType(StrEnum):
    LAB_REPORT = "lab_report"
    DISCHARGE_SUMMARY = "discharge_summary"
    PRESCRIPTION = "prescription"
    DIAGNOSTIC_REPORT = "diagnostic_report"
    INSURANCE = "insurance"
    REFERRAL = "referral"
    OTHER = "other"


class DocumentVisibility(StrEnum):
    ALL_PROVIDERS = "all_providers"
    SPECIFIC_PROVIDER = "specific_provider"


class UploaderRole(StrEnum):
    PATIENT = "patient"
    CLINICIAN = "clinician"


# ── Medications ────────────────────────────────────


class MedicationRoute(StrEnum):
    ORAL = "oral"
    TOPICAL = "topical"
    IV = "iv"
    IM = "im"
    SUBCUTANEOUS = "subcutaneous"
    INHALED = "inhaled"
    OTHER = "other"


# ── Obligations ────────────────────────────────────


class ObligationType(StrEnum):
    DIET = "diet"
    EXERCISE = "exercise"
    CUSTOM = "custom"


# ── Adherence ──────────────────────────────────────


class AdherenceTargetType(StrEnum):
    MEDICATION = "medication"
    OBLIGATION = "obligation"


class AdherenceStatus(StrEnum):
    TAKEN = "taken"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    MISSED = "missed"


# ── ADR / Pharmacovigilance ───────────────────────


class NaranjoCausality(StrEnum):
    DEFINITE = "Definite"
    PROBABLE = "Probable"
    POSSIBLE = "Possible"
    DOUBTFUL = "Doubtful"


class ADRStatus(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    SUBMITTED = "submitted"
    DISMISSED = "dismissed"


class MedWatchStatus(StrEnum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    SUBMITTED = "submitted"


# ── Appointments ───────────────────────────────────


class AppointmentType(StrEnum):
    FOLLOW_UP = "follow_up"
    INITIAL = "initial"
    ROUTINE = "routine"
    URGENT = "urgent"
    PRE_OP = "pre_op"


class AppointmentStatus(StrEnum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


# ── Chat ───────────────────────────────────────────


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# ── Notifications ──────────────────────────────────


class NotificationType(StrEnum):
    MED_REMINDER = "med_reminder"
    MISSED_DOSE = "missed_dose"
    APPOINTMENT = "appointment"
    DOCTOR_MESSAGE = "doctor_message"
    ADR_ALERT = "adr_alert"
    OBLIGATION_REMINDER = "obligation_reminder"


# ── Clinician Messages ────────────────────────────


class MessageChannel(StrEnum):
    IN_APP = "in_app"
    EMAIL = "email"


# ── Allergy ────────────────────────────────────────


class AllergySeverity(StrEnum):
    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"
