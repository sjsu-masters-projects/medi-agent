/**
 * Patient Portal types — re-exports from @mediagent/shared.
 *
 * Import from here within the patient portal.
 * When the shared package is wired up via workspace references,
 * these re-exports make migration a one-line change.
 */

export type {
    Patient,
    Medication,
    Obligation,
    Document,
    ChatMessage,
    Notification,
    Appointment,
    CareTeamMember,
    SymptomReport,
    AdherenceLog,
    AdherenceStats,
    Condition,
    Allergy,
    ApiErrorResponse,
    PaginatedResponse,
} from "../../../../packages/shared/src/types";

export {
    Language,
    Gender,
    ChatRole,
    DocumentType,
    MedicationRoute,
    ObligationType,
    AdherenceStatus,
    NotificationType,
    AppointmentStatus,
    AllergySeverity,
} from "../../../../packages/shared/src/types";
