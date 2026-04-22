/**
 * Shared TypeScript types used by both portals.
 * Intended to mirror backend Pydantic schemas in `backend/src/app/models/`.
 * Sync is maintained via project process/tooling outside this file; keep both
 * sides aligned when changing models or API contracts.
 */

// ── Enums (match backend StrEnum values) ──────────

export const Locale = { EN_US: "en-US", ES_MX: "es-MX" } as const;
export type Locale = (typeof Locale)[keyof typeof Locale];

export const DEFAULT_LOCALE: Locale = Locale.EN_US;

const LOCALE_VALUES = new Set<Locale>(Object.values(Locale));
const LOCALE_ALIASES: Record<string, Locale> = {
    en: Locale.EN_US,
    "en-us": Locale.EN_US,
    es: Locale.ES_MX,
    "es-mx": Locale.ES_MX,
};

export function isLocale(value: unknown): value is Locale {
    return typeof value === "string" && LOCALE_VALUES.has(value as Locale);
}

export function normalizeLocale(
    value: unknown,
    fallback: Locale = DEFAULT_LOCALE,
): Locale {
    if (isLocale(value)) {
        return value;
    }

    if (typeof value !== "string") {
        return fallback;
    }

    const normalized = value.trim().toLowerCase().replaceAll("_", "-");
    return LOCALE_ALIASES[normalized] ?? fallback;
}

export function isSpanishLocale(value: unknown): boolean {
    return normalizeLocale(value) === Locale.ES_MX;
}

// Backward-compatible aliases while the codebase transitions from language to locale naming.
export const Language = { EN: Locale.EN_US, ES: Locale.ES_MX } as const;
export type Language = Locale;
export const isLanguage = isLocale;
export const normalizeLanguage = normalizeLocale;
export const isSpanishLanguage = isSpanishLocale;

export const Gender = { MALE: "male", FEMALE: "female", OTHER: "other", PREFER_NOT_TO_SAY: "prefer_not_to_say" } as const;
export type Gender = (typeof Gender)[keyof typeof Gender];

export const ClinicianRole = { PROVIDER: "provider", ADMIN: "admin", NURSE: "nurse" } as const;
export type ClinicianRole = (typeof ClinicianRole)[keyof typeof ClinicianRole];

export const CareTeamStatus = { ACTIVE: "active", INACTIVE: "inactive", TRANSFERRED: "transferred" } as const;
export type CareTeamStatus = (typeof CareTeamStatus)[keyof typeof CareTeamStatus];

export const DocumentParseStatus = {
    NONE: "none",
    PENDING: "pending",
    PROCESSING: "processing",
    COMPLETED: "completed",
    FAILED: "failed",
} as const;
export type DocumentParseStatus = (typeof DocumentParseStatus)[keyof typeof DocumentParseStatus];

export const DocumentType = {
    LAB_REPORT: "lab_report", DISCHARGE_SUMMARY: "discharge_summary", PRESCRIPTION: "prescription",
    DIAGNOSTIC_REPORT: "diagnostic_report", INSURANCE: "insurance", REFERRAL: "referral", OTHER: "other",
} as const;
export type DocumentType = (typeof DocumentType)[keyof typeof DocumentType];

export const DocumentVisibility = { ALL_PROVIDERS: "all_providers", SPECIFIC_PROVIDER: "specific_provider" } as const;
export type DocumentVisibility = (typeof DocumentVisibility)[keyof typeof DocumentVisibility];

export const UploaderRole = { PATIENT: "patient", CLINICIAN: "clinician" } as const;
export type UploaderRole = (typeof UploaderRole)[keyof typeof UploaderRole];

export const PortalUserRole = { PATIENT: "patient", CLINICIAN: "clinician" } as const;
export type PortalUserRole = (typeof PortalUserRole)[keyof typeof PortalUserRole];

export const MedicationRoute = {
    ORAL: "oral", TOPICAL: "topical", IV: "iv", IM: "im",
    SUBCUTANEOUS: "subcutaneous", INHALED: "inhaled", OTHER: "other",
} as const;
export type MedicationRoute = (typeof MedicationRoute)[keyof typeof MedicationRoute];

export const ObligationType = { DIET: "diet", EXERCISE: "exercise", CUSTOM: "custom" } as const;
export type ObligationType = (typeof ObligationType)[keyof typeof ObligationType];

export const AdherenceTargetType = { MEDICATION: "medication", OBLIGATION: "obligation" } as const;
export type AdherenceTargetType = (typeof AdherenceTargetType)[keyof typeof AdherenceTargetType];

export const AdherenceStatus = { TAKEN: "taken", COMPLETED: "completed", SKIPPED: "skipped", MISSED: "missed" } as const;
export type AdherenceStatus = (typeof AdherenceStatus)[keyof typeof AdherenceStatus];

export const FeedTaskType = { MEDICATION: "medication", OBLIGATION: "obligation" } as const;
export type FeedTaskType = (typeof FeedTaskType)[keyof typeof FeedTaskType];

export const FeedTaskStatus = {
    PENDING: "pending",
    COMPLETED: "completed",
    SKIPPED: "skipped",
    MISSED: "missed",
} as const;
export type FeedTaskStatus = (typeof FeedTaskStatus)[keyof typeof FeedTaskStatus];

export const NaranjoCausality = { DEFINITE: "Definite", PROBABLE: "Probable", POSSIBLE: "Possible", DOUBTFUL: "Doubtful" } as const;
export type NaranjoCausality = (typeof NaranjoCausality)[keyof typeof NaranjoCausality];

export const ADRStatus = { DRAFT: "draft", REVIEWED: "reviewed", SUBMITTED: "submitted", DISMISSED: "dismissed" } as const;
export type ADRStatus = (typeof ADRStatus)[keyof typeof ADRStatus];

export const MedWatchStatus = { DRAFT: "draft", REVIEWED: "reviewed", SUBMITTED: "submitted" } as const;
export type MedWatchStatus = (typeof MedWatchStatus)[keyof typeof MedWatchStatus];

export const AppointmentType = {
    FOLLOW_UP: "follow_up", INITIAL: "initial", ROUTINE: "routine", URGENT: "urgent", PRE_OP: "pre_op",
} as const;
export type AppointmentType = (typeof AppointmentType)[keyof typeof AppointmentType];

export const AppointmentStatus = {
    SCHEDULED: "scheduled", COMPLETED: "completed", CANCELLED: "cancelled", NO_SHOW: "no_show",
} as const;
export type AppointmentStatus = (typeof AppointmentStatus)[keyof typeof AppointmentStatus];

export const ChatRole = { USER: "user", ASSISTANT: "assistant", SYSTEM: "system" } as const;
export type ChatRole = (typeof ChatRole)[keyof typeof ChatRole];

export const NotificationType = {
    MED_REMINDER: "med_reminder", MISSED_DOSE: "missed_dose", APPOINTMENT: "appointment",
    DOCTOR_MESSAGE: "doctor_message", ADR_ALERT: "adr_alert", OBLIGATION_REMINDER: "obligation_reminder",
} as const;
export type NotificationType = (typeof NotificationType)[keyof typeof NotificationType];

export const MessageChannel = { IN_APP: "in_app", EMAIL: "email" } as const;
export type MessageChannel = (typeof MessageChannel)[keyof typeof MessageChannel];

export const AllergySeverity = { MILD: "mild", MODERATE: "moderate", SEVERE: "severe" } as const;
export type AllergySeverity = (typeof AllergySeverity)[keyof typeof AllergySeverity];


// ── API Envelopes ─────────────────────────────────

export interface ApiErrorResponse {
    error: { code: string; message: string };
}

export interface PaginatedResponse<T> {
    data: T[];
    nextCursor: string | null;
    hasMore: boolean;
    totalCount?: number;
}


// ── Domain Types ──────────────────────────────────

export interface Patient {
    id: string;
    email: string;
    firstName: string;
    lastName: string;
    dateOfBirth: string;
    gender?: Gender;
    preferredLanguage: Language;
    phone?: string;
    avatarUrl?: string;
    createdAt: string;
    updatedAt?: string;
}

export interface Clinician {
    id: string;
    email: string;
    firstName: string;
    lastName: string;
    specialty: string;
    clinicName: string;
    npiNumber?: string;
    role: ClinicianRole;
    avatarUrl?: string;
    createdAt: string;
    updatedAt?: string;
}

export interface CareTeamMember {
    id: string;
    patientId: string;
    clinicianId: string;
    clinicianFirstName: string;
    clinicianLastName: string;
    role: string;
    specialtyContext?: string;
    clinicName?: string;
    status: CareTeamStatus;
    createdAt: string;
}

export interface Medication {
    id: string;
    patientId: string;
    name: string;
    genericName?: string;
    rxcui?: string;
    dosage: string;
    frequency: string;
    route: MedicationRoute;
    prescribedByCareTeamId?: string;
    prescribedByName?: string;
    startDate?: string;
    endDate?: string;
    instructions?: string;
    sourceDocumentId?: string;
    isActive: boolean;
    createdAt: string;
}

export interface Obligation {
    id: string;
    patientId: string;
    obligationType: ObligationType;
    description: string;
    frequency: string;
    setByCareTeamId?: string;
    isActive: boolean;
    createdAt: string;
}

export interface Document {
    id: string;
    patientId: string;
    uploadedBy: string;
    uploadedByRole: UploaderRole;
    documentType: DocumentType;
    fileName: string;
    fileUrl: string;
    mimeType: string;
    fileSizeBytes: number;
    parsed: boolean;
    aiSummary?: string;
    parseStatus: DocumentParseStatus;
    parseError?: string;
    parseAttempts: number;
    sourceClinic?: string;
    visibility: DocumentVisibility;
    createdAt: string;
}

export interface AdherenceLog {
    id: string;
    patientId: string;
    targetType: AdherenceTargetType;
    targetId: string;
    status: AdherenceStatus;
    scheduledTime?: string;
    notes?: string;
    loggedAt: string;
}

export interface AdherenceStats {
    patientId: string;
    overallScore: number;
    medicationScore: number;
    obligationScore: number;
    currentStreakDays: number;
    periodDays: number;
    totalExpected: number;
    totalCompleted: number;
}

export interface FeedProvider {
    id: string;
    name: string;
    specialty: string;
    clinicName: string;
}

export interface FeedTask {
    id: string;
    type: FeedTaskType;
    targetId: string;
    name: string;
    description?: string;
    frequency: string;
    scheduledTime?: string;
    status: FeedTaskStatus;
    completedAt?: string;
    provider?: FeedProvider;
}

export interface FeedSummary {
    total: number;
    completed: number;
    pending: number;
    skipped: number;
    missed: number;
}

export interface TodayFeedResponse {
    date: string;
    timezone: string;
    tasks: FeedTask[];
    summary: FeedSummary;
}

export interface SymptomReport {
    id: string;
    patientId: string;
    symptom: string;
    severity: number;
    onset?: string;
    duration?: string;
    relatedMedicationId?: string;
    relatedMedicationName?: string;
    bodyArea?: string;
    aiAssessment?: string;
    flaggedForAdr: boolean;
    notes?: string;
    createdAt: string;
}

export interface ADRAssessment {
    id: string;
    patientId: string;
    symptomReportId: string;
    suspectMedicationId: string;
    suspectMedicationName: string;
    naranjoScore: number;
    causality: NaranjoCausality;
    thinkingChain?: string;
    status: ADRStatus;
    reviewedBy?: string;
    reviewedAt?: string;
    dismissReason?: string;
    createdAt: string;
}

export interface MedWatchDraft {
    id: string;
    adrAssessmentId: string;
    patientId: string;
    formData: Record<string, unknown>;
    deIdentified: boolean;
    status: MedWatchStatus;
    submittedAt?: string;
    createdAt: string;
}

export interface Appointment {
    id: string;
    patientId: string;
    careTeamId: string;
    clinicianName?: string;
    scheduledAt: string;
    durationMinutes: number;
    appointmentType: AppointmentType;
    location?: string;
    reason?: string;
    notes?: string;
    status: AppointmentStatus;
    sourceDocumentId?: string;
    createdAt: string;
}

export interface ChatMessage {
    id: string;
    patientId: string;
    content: string;
    role: ChatRole;
    intent?: string;
    language: Language;
    audioUrl?: string;
    createdAt: string;
}

export interface Notification {
    id: string;
    patientId: string;
    notificationType: NotificationType;
    title: string;
    body: string;
    actionUrl?: string;
    isRead: boolean;
    createdAt: string;
}

export interface Condition {
    id: string;
    patientId: string;
    name: string;
    icd10Code?: string;
    status: string;
    notes?: string;
    createdAt: string;
}

export interface Allergy {
    id: string;
    patientId: string;
    allergen: string;
    reaction?: string;
    severity: AllergySeverity;
    createdAt: string;
}

export interface ClinicianMessage {
    id: string;
    clinicianId: string;
    patientId: string;
    channel: MessageChannel;
    subject?: string;
    body: string;
    isRead: boolean;
    createdAt: string;
}

// ── Patient Summary (clinician dashboard view) ────

export interface PatientSummary {
    id: string;
    firstName: string;
    lastName: string;
    riskLevel: "low" | "medium" | "high";
    adherenceScore: number;
    activeMedCount: number;
    lastActivity: string;
    openAdrCount: number;
}
