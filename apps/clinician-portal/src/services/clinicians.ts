/**
 * Clinician API service functions.
 *
 * All calls go through the base fetch wrapper with JWT auth headers.
 * Functions return typed data or throw on HTTP errors.
 */

import {
    ChatRole,
    type ClinicianPatientDocument,
    type DocumentReviewQueueItem,
    type DocumentReviewStatus,
    type DocumentReviewer,
    type DocumentType,
    type Medication,
    type ReminderSchedule,
    type SymptomReport,
    type UploaderRole,
} from "@/types";
import { readStoredSession } from "@/services/auth-session";

// ── Base config ──────────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
    const token =
        typeof window !== "undefined"
            ? readStoredSession()?.accessToken ?? localStorage.getItem("access_token") ?? ""
            : "";

    if (!token) {
        throw new Error("Missing authorization header");
    }

    const response = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
            ...options.headers,
        },
    });

    if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw new Error(
            errorBody?.error?.message ?? `API error ${response.status}: ${path}`,
        );
    }

    return response.json() as Promise<T>;
}

// ── Dashboard types ──────────────────────────────────────────────────────────

export type RiskLevel = "low" | "medium" | "high" | "unknown";
export type DashboardSortBy = "risk" | "adherence" | "last_activity" | "med_count";
export type DashboardSortOrder = "asc" | "desc";

export interface DashboardQueryParams {
    sortBy?: DashboardSortBy;
    sortOrder?: DashboardSortOrder;
    riskFilter?: RiskLevel;
    minMedCount?: number;
    maxLastActivityDays?: number;
    page?: number;
    pageSize?: number;
}

export interface PatientRiskData {
    patient_id: string;
    first_name: string;
    last_name: string;
    risk_level: RiskLevel;
    adherence_score: number;
    open_adr_count: number;
    active_med_count: number;
    recent_symptom_severity: number;
    last_activity: string;
}

export interface DashboardResponse {
    patients: PatientRiskData[];
    total: number;
    high_risk: number;
    medium_risk: number;
    low_risk: number;
    medwatch_pending: number;
}

export interface SoapNote {
    subjective: string;
    objective: string;
    assessment: string;
    plan: string;
}

export interface SoapNoteResponse {
    id?: string;
    patient_id?: string;
    clinician_id?: string;
    subjective: string;
    objective: string;
    assessment: string;
    plan: string;
    generated_at?: string;
    model_used?: string;
}

export interface AdherenceDataPoint {
    date: string;
    score: number;
    completed: number;
    expected: number;
}

export interface PatientDeepDive {
    patient_id: string;
    first_name: string;
    last_name: string;
    email: string;
    date_of_birth?: string;
    avatar_url?: string;
    timezone?: string;
    risk_level: RiskLevel;
    adherence_score: number;
    medications: Medication[];
    adherence_series: AdherenceDataPoint[];
    symptom_reports: SymptomReport[];
    chat_messages: Array<{
        role: typeof ChatRole[keyof typeof ChatRole];
        content: string;
        created_at: string;
        audio_url?: string;
    }>;
    conditions: Array<{ name?: string; icd10_code?: string; created_at?: string }>;
    allergies: Array<{ allergen: string; severity?: string }>;
    documents: ClinicianPatientDocument[];
    latest_soap_note?: SoapNoteResponse;
    obligations?: Array<{
        id: string;
        obligation_type: string;
        description: string;
        frequency: string;
        notes?: string;
        reminder_schedule?: ReminderSchedule | null;
        is_active: boolean;
        created_at?: string;
    }>;
    obligation_completion_rate?: number;
}

export interface DocumentReviewActionResponse {
    status: string;
    document_id: string;
    patient_id: string;
    review_status: DocumentReviewStatus;
    reviewed_by: string;
    reviewed_at: string;
    review_note?: string;
}

type ApiMedicationRecord = Partial<Medication> & Record<string, unknown>;
type ApiSymptomReportRecord = Partial<SymptomReport> & Record<string, unknown>;
interface ApiChatMessageRecord {
    role: string;
    content: string;
    created_at: string;
    audio_url?: string;
}

interface PatientDeepDiveResponse
    extends Omit<PatientDeepDive, "medications" | "symptom_reports" | "chat_messages" | "documents"> {
    medications: ApiMedicationRecord[];
    symptom_reports: ApiSymptomReportRecord[];
    chat_messages: ApiChatMessageRecord[];
    documents: Array<{
        id: string;
        file_name: string;
        document_type: DocumentType;
        parse_status: string;
        ai_summary?: string;
        created_at: string;
        uploaded_by_role: UploaderRole;
        clinician_annotation?: string;
        review_status?: DocumentReviewStatus;
        reviewed_by?: string;
        reviewed_at?: string;
        review_note?: string;
        reviewer?: {
            id: string;
            first_name?: string;
            last_name?: string;
        } | null;
    }>;
}

interface DocumentReviewQueueItemResponse {
    id: string;
    patient_id: string;
    patient_first_name: string;
    patient_last_name: string;
    file_name: string;
    document_type: DocumentType;
    parse_status: string;
    ai_summary?: string;
    source_clinic?: string;
    created_at: string;
    uploaded_by_role: UploaderRole;
    review_status: DocumentReviewStatus;
}

export interface ObligationSetPayload {
    obligation_type: "diet" | "exercise" | "custom";
    description: string;
    frequency: string;
    notes?: string;
}

function normalizeReminderSchedule(raw: unknown): ReminderSchedule | null {
    if (!raw || typeof raw !== "object") {
        return null;
    }

    const schedule = raw as Record<string, unknown>;
    return {
        id: String(schedule.id ?? ""),
        patientId: String(schedule.patientId ?? schedule.patient_id ?? ""),
        targetType: String(schedule.targetType ?? schedule.target_type ?? "") as ReminderSchedule["targetType"],
        targetId: String(schedule.targetId ?? schedule.target_id ?? ""),
        timezone: String(schedule.timezone ?? "UTC"),
        timesOfDay: Array.isArray(schedule.timesOfDay)
            ? schedule.timesOfDay.map((value) => String(value))
            : Array.isArray(schedule.times_of_day)
              ? schedule.times_of_day.map((value) => String(value))
              : [],
        daysOfWeek: Array.isArray(schedule.daysOfWeek)
            ? schedule.daysOfWeek.map((value) => String(value) as ReminderSchedule["daysOfWeek"][number])
            : Array.isArray(schedule.days_of_week)
              ? schedule.days_of_week.map((value) => String(value) as ReminderSchedule["daysOfWeek"][number])
              : [],
        isEnabled: Boolean(schedule.isEnabled ?? schedule.is_enabled ?? true),
        createdAt: String(schedule.createdAt ?? schedule.created_at ?? ""),
        updatedAt:
            typeof schedule.updatedAt === "string"
                ? schedule.updatedAt
                : typeof schedule.updated_at === "string"
                  ? schedule.updated_at
                  : undefined,
    };
}

function normalizeMedication(raw: Record<string, unknown>): Medication {
    return {
        id: String(raw.id ?? ""),
        patientId: String(raw.patientId ?? raw.patient_id ?? ""),
        name: String(raw.name ?? ""),
        genericName:
            typeof raw.genericName === "string"
                ? raw.genericName
                : typeof raw.generic_name === "string"
                  ? raw.generic_name
                  : undefined,
        dosage: String(raw.dosage ?? ""),
        frequency: String(raw.frequency ?? ""),
        route: String(raw.route ?? "oral") as Medication["route"],
        prescribedByCareTeamId:
            typeof raw.prescribedByCareTeamId === "string"
                ? raw.prescribedByCareTeamId
                : typeof raw.prescribed_by_care_team_id === "string"
                  ? raw.prescribed_by_care_team_id
                  : undefined,
        prescribedByName:
            typeof raw.prescribedByName === "string"
                ? raw.prescribedByName
                : typeof raw.prescribed_by_name === "string"
                  ? raw.prescribed_by_name
                  : undefined,
        isActive: Boolean(raw.isActive ?? raw.is_active ?? true),
        reminderSchedule: normalizeReminderSchedule(raw.reminderSchedule ?? raw.reminder_schedule),
        createdAt: String(raw.createdAt ?? raw.created_at ?? ""),
    };
}

function normalizeSymptomReport(raw: Record<string, unknown>): SymptomReport {
    return {
        id: String(raw.id ?? ""),
        patientId: String(raw.patientId ?? raw.patient_id ?? ""),
        symptom: String(raw.symptom ?? ""),
        severity: Number(raw.severity ?? 0),
        onset: typeof raw.onset === "string" ? raw.onset : undefined,
        duration: typeof raw.duration === "string" ? raw.duration : undefined,
        relatedMedicationId:
            typeof raw.relatedMedicationId === "string"
                ? raw.relatedMedicationId
                : typeof raw.related_medication_id === "string"
                  ? raw.related_medication_id
                  : undefined,
        relatedMedicationName:
            typeof raw.relatedMedicationName === "string"
                ? raw.relatedMedicationName
                : typeof raw.related_medication_name === "string"
                  ? raw.related_medication_name
                  : undefined,
        bodyArea:
            typeof raw.bodyArea === "string"
                ? raw.bodyArea
                : typeof raw.body_area === "string"
                  ? raw.body_area
                  : undefined,
        aiAssessment:
            typeof raw.aiAssessment === "string"
                ? raw.aiAssessment
                : typeof raw.ai_assessment === "string"
                  ? raw.ai_assessment
                  : undefined,
        flaggedForAdr: Boolean(raw.flaggedForAdr ?? raw.flagged_for_adr ?? false),
        notes: typeof raw.notes === "string" ? raw.notes : undefined,
        createdAt: String(raw.createdAt ?? raw.created_at ?? ""),
    };
}

function normalizeChatRole(role: string): typeof ChatRole[keyof typeof ChatRole] {
    switch (role) {
        case ChatRole.USER:
            return ChatRole.USER;
        case ChatRole.ASSISTANT:
            return ChatRole.ASSISTANT;
        default:
            return ChatRole.SYSTEM;
    }
}

function normalizeReviewer(
    reviewer: PatientDeepDiveResponse["documents"][number]["reviewer"],
): DocumentReviewer | null {
    if (!reviewer) {
        return null;
    }

    return {
        id: reviewer.id,
        firstName: reviewer.first_name,
        lastName: reviewer.last_name,
    };
}

function normalizePatientDocument(
    document: PatientDeepDiveResponse["documents"][number],
): ClinicianPatientDocument {
    return {
        id: document.id,
        fileName: document.file_name,
        documentType: document.document_type,
        parseStatus: document.parse_status,
        aiSummary: document.ai_summary,
        createdAt: document.created_at,
        uploadedByRole: document.uploaded_by_role,
        clinicianAnnotation: document.clinician_annotation,
        reviewStatus: document.review_status,
        reviewedBy: document.reviewed_by,
        reviewedAt: document.reviewed_at,
        reviewNote: document.review_note,
        reviewer: normalizeReviewer(document.reviewer),
    };
}

function normalizeDocumentReviewQueueItem(
    item: DocumentReviewQueueItemResponse,
): DocumentReviewQueueItem {
    return {
        id: item.id,
        patientId: item.patient_id,
        patientFirstName: item.patient_first_name,
        patientLastName: item.patient_last_name,
        fileName: item.file_name,
        documentType: item.document_type,
        parseStatus: item.parse_status,
        aiSummary: item.ai_summary,
        sourceClinic: item.source_clinic,
        createdAt: item.created_at,
        uploadedByRole: item.uploaded_by_role,
        reviewStatus: item.review_status,
    };
}

// ── API functions ─────────────────────────────────────────────────────────────

/** Fetch aggregated risk dashboard for all assigned patients. */
export async function fetchDashboard(params?: DashboardQueryParams): Promise<DashboardResponse> {
    const search = new URLSearchParams();
    if (params?.sortBy) search.set("sort_by", params.sortBy);
    if (params?.sortOrder) search.set("sort_order", params.sortOrder);
    if (params?.riskFilter) search.set("risk_filter", params.riskFilter);
    if (params?.minMedCount !== undefined) search.set("min_med_count", String(params.minMedCount));
    if (params?.maxLastActivityDays !== undefined) {
        search.set("max_last_activity_days", String(params.maxLastActivityDays));
    }
    if (params?.page !== undefined) search.set("page", String(params.page));
    if (params?.pageSize !== undefined) search.set("page_size", String(params.pageSize));

    const qs = search.toString();
    return apiFetch<DashboardResponse>(`/api/v1/clinicians/me/dashboard${qs ? `?${qs}` : ""}`);
}

/** Fetch one patient's latest risk radar snapshot. */
export async function fetchPatientRiskSnapshot(patientId: string): Promise<PatientRiskData> {
    return apiFetch<PatientRiskData>(`/api/v1/clinicians/me/patients/${patientId}/risk`);
}

/** Fetch full patient deep dive data (all sub-resources). */
export async function fetchPatientDeepDive(patientId: string): Promise<PatientDeepDive> {
    const data = await apiFetch<PatientDeepDiveResponse>(
        `/api/v1/clinicians/me/patients/${patientId}/deep-dive`,
    );

    return {
        ...data,
        timezone: data.timezone,
        medications: (data.medications ?? []).map((medication) => normalizeMedication(medication)),
        obligations: (data.obligations ?? []).map((obligation) => ({
            ...obligation,
            notes:
                typeof obligation.notes === "string"
                    ? obligation.notes
                    : undefined,
            reminder_schedule: normalizeReminderSchedule(obligation.reminder_schedule),
        })),
        symptom_reports: (data.symptom_reports ?? []).map((report) =>
            normalizeSymptomReport(report),
        ),
        chat_messages: (data.chat_messages ?? []).map((message) => ({
            ...message,
            role: normalizeChatRole(message.role),
        })),
        documents: (data.documents ?? []).map((document) => normalizePatientDocument(document)),
    };
}

export async function fetchDocumentReviewQueue(): Promise<DocumentReviewQueueItem[]> {
    const data = await apiFetch<DocumentReviewQueueItemResponse[]>(
        "/api/v1/clinicians/me/document-review-queue",
    );
    return data.map((item) => normalizeDocumentReviewQueueItem(item));
}

export async function approveDocumentReview(
    patientId: string,
    documentId: string,
): Promise<DocumentReviewActionResponse> {
    return apiFetch(
        `/api/v1/clinicians/me/patients/${patientId}/documents/${documentId}/approve`,
        { method: "POST" },
    );
}

export async function rejectDocumentReview(
    patientId: string,
    documentId: string,
    reviewNote?: string,
): Promise<DocumentReviewActionResponse> {
    return apiFetch(
        `/api/v1/clinicians/me/patients/${patientId}/documents/${documentId}/reject`,
        {
            method: "POST",
            body: JSON.stringify({ review_note: reviewNote ?? null }),
        },
    );
}

/** Trigger Summarization Agent to generate a SOAP note. */
export async function generateSoapNote(
    patientId: string,
    lookbackDays = 30,
): Promise<{ status: string; soap_note_id?: string; soap_note: SoapNoteResponse }> {
    return apiFetch(`/api/v1/clinicians/me/patients/${patientId}/soap-note`, {
        method: "POST",
        body: JSON.stringify({ lookback_days: lookbackDays }),
    });
}

/** Set a diet/exercise/custom obligation for a patient. */
export async function setPatientObligation(
    patientId: string,
    payload: ObligationSetPayload,
): Promise<unknown> {
    return apiFetch(`/api/v1/clinicians/me/patients/${patientId}/obligations`, {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

/** Save clinician annotation on a document. */
export async function annotateDocument(
    patientId: string,
    documentId: string,
    annotationText: string,
): Promise<{ status: string; document_id: string }> {
    return apiFetch(
        `/api/v1/clinicians/me/patients/${patientId}/documents/${documentId}/annotate`,
        {
            method: "POST",
            body: JSON.stringify({ annotation_text: annotationText }),
        },
    );
}

/** Get all patients (patient list page). */
export async function fetchMyPatients(): Promise<PatientRiskData[]> {
    return apiFetch<PatientRiskData[]>("/api/v1/clinicians/me/patients");
}
