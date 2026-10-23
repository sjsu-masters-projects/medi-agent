/**
 * Patient Portal types — re-exports from @mediagent/shared.
 *
 * Import from here within the patient portal.
 * When the shared package is wired up via workspace references,
 * these re-exports make migration a one-line change.
 */

import type { ChatMessage as SharedChatMessage } from "../../../../packages/shared/src/types";
import type { ChatAttachment } from "./chat-attachments";

export type {
    LocaleMetadata,
    LocaleResourceMap,
    Patient,
    Medication,
    Obligation,
    Document,
    ChatAppointmentProposal,
    Notification,
    Appointment,
    CareTeamMember,
    SymptomReport,
    SymptomIntake,
    IntakeQuestion,
    IntakeAnswer,
    AdherenceLog,
    AdherenceStats,
    FeedTask,
    FeedCarePlanProvenance,
    FeedSummary,
    TodayFeedResponse,
    ReminderDayOfWeek,
    ReminderGuidance,
    ReminderSchedule,
    ReminderTarget,
    Condition,
    Allergy,
    DocumentVisibility,
    UploaderRole,
    ApiErrorResponse,
    PaginatedResponse,
} from "../../../../packages/shared/src/types";

export type {
    CareTeamFilterOption,
    PatientApprovedPlanSummary,
    PatientCondition,
    PlanOwner,
    UploadCareTeamOption,
} from "../../../../packages/shared/src/types/care-team-plans";

export type { ChatAttachment, ChatDocumentResultsAttachment, ChatSymptomOfferAttachment } from "./chat-attachments";

/** A chat message as the patient portal shows it, with any server-built cards under it. */
export interface ChatMessage extends SharedChatMessage {
    /** Absent for messages that carry no card, including every older message. */
    attachments?: ChatAttachment[];
    /** Saved evidence backs this Nora reply, so the Sources line is shown. */
    hasEvidence?: boolean;
    /** Set on a message this tab has sent but the server has not yet confirmed (see `delivery`). */
    clientMessageId?: string;
    /** `pending`: shown the instant it was sent; `failed`: the send was rejected, text kept for retry. */
    delivery?: "pending" | "failed";
}

export {
    Locale,
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    Language,
    LOCALE_METADATA,
    getLocaleMetadata,
    getLocaleLabel,
    getLocaleSelectorLabel,
    getLocaleBadgeLabel,
    getDocumentTypeLabel,
    resolveLocaleResource,
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
    AppointmentType,
    AppointmentStatus,
    AllergySeverity,
} from "../../../../packages/shared/src/types";
