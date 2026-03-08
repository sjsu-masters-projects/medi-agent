/**
 * Clinician Portal types — re-exports from @mediagent/shared.
 *
 * Import from here within the clinician portal.
 */

export type {
    Clinician,
    Patient,
    PatientSummary,
    Medication,
    Document,
    ChatMessage,
    ADRAssessment,
    MedWatchDraft,
    Notification,
    Appointment,
    CareTeamMember,
    SymptomReport,
    AdherenceStats,
    ClinicianMessage,
    Condition,
    Allergy,
    ApiErrorResponse,
    PaginatedResponse,
} from "../../../../packages/shared/src/types";

export {
    Language,
    ClinicianRole,
    NaranjoCausality,
    ADRStatus,
    MedWatchStatus,
    AppointmentStatus,
    NotificationType,
    MessageChannel,
    DocumentType,
    AllergySeverity,
} from "../../../../packages/shared/src/types";
