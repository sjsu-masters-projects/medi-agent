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
    FeedTask,
    FeedSummary,
    TodayFeedResponse,
    Condition,
    Allergy,
    DocumentVisibility,
    UploaderRole,
    ApiErrorResponse,
    PaginatedResponse,
} from "../../../../packages/shared/src/types";

export {
    Locale,
    DEFAULT_LOCALE,
    Language,
    isLocale,
    isSpanishLocale,
    normalizeLocale,
    isLanguage,
    isSpanishLanguage,
    normalizeLanguage,
    Gender,
    ChatRole,
    DocumentParseStatus,
    DocumentType,
    PortalUserRole,
    FeedTaskStatus,
    FeedTaskType,
    MedicationRoute,
    ObligationType,
    AdherenceStatus,
    NotificationType,
    AppointmentStatus,
    AllergySeverity,
} from "../../../../packages/shared/src/types";
