/**
 * Clinician API service functions.
 *
 * All calls go through the base fetch wrapper with JWT auth headers.
 * Functions return typed data or throw on HTTP errors.
 */

import {
    ChatRole,
    type ADRStatus,
    type ClinicianMessage,
    type ClinicianPatientDocument,
    type DocumentReviewQueueItem,
    type DocumentReviewStatus,
    type DocumentReviewer,
    type DocumentType,
    type Medication,
    MessageChannel,
    type NaranjoCausality,
    type ReminderSchedule,
    type SymptomReport,
    type UploaderRole,
} from "@/types";
import { readStoredSession } from "@/services/auth-session";
import { ApiClientError } from "@/services/api";
import { fetchWithReadRecovery } from "../../../../packages/shared/src/utils/api-transport";

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

    const response = await fetchWithReadRecovery(`${API_BASE}${path}`, {
        ...options,
        headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
            ...options.headers,
        },
    });

    if (!response.ok) {
        const errorBody = await response.json().catch(() => ({}));
        throw new ApiClientError(
            errorBody?.error?.message ?? `API error ${response.status}`,
            response.status,
            errorBody,
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
    pending_adr_reviews: number;
    medwatch_pending: number;
}

export interface ADRReviewEvidence {
    answer: string;
    evidence?: string | null;
    question: string;
}

export interface ADRReviewQueueItem {
    id: string;
    patientId: string;
    patientFirstName: string;
    patientLastName: string;
    symptomReportId: string;
    symptom: string;
    severity: number;
    onset?: string | null;
    symptomCreatedAt: string;
    suspectMedicationId: string;
    suspectMedicationName: string;
    naranjoScore: number;
    causality: NaranjoCausality;
    naranjoAnswers: Record<string, string>;
    naranjoAssessment: {
        missing_questions?: string[];
        items?: Array<{ answer: string; points: number; question: string }>;
    };
    evidence: ADRReviewEvidence[];
    status: ADRStatus;
    lastReviewAction?: ADRReviewAction | null;
    reviewNote?: string | null;
    requestedInformation: string[];
    reviewedBy?: string | null;
    reviewedAt?: string | null;
    createdAt: string;
}

export type ADRReviewAction = "mark_reviewed" | "dismiss" | "request_information";

export interface ADRReviewDecisionInput {
    action: ADRReviewAction;
    note?: string;
    requestedInformation?: string[];
}

export interface ADRReviewDecisionResult {
    id: string;
    patientId: string;
    status: ADRStatus;
    lastReviewAction: ADRReviewAction;
    reviewNote?: string | null;
    requestedInformation: string[];
    reviewedBy: string;
    reviewedAt: string;
    dismissReason?: string | null;
    updatedAt: string;
}

interface ADRReviewQueueResponse {
    items: Array<{
        id: string;
        patient_id: string;
        patient_first_name: string;
        patient_last_name: string;
        symptom_report_id: string;
        symptom: string;
        severity: number;
        onset?: string | null;
        symptom_created_at: string;
        suspect_medication_id: string;
        suspect_medication_name: string;
        naranjo_score: number;
        causality: NaranjoCausality;
        naranjo_answers: Record<string, string>;
        naranjo_assessment: ADRReviewQueueItem["naranjoAssessment"];
        evidence: ADRReviewEvidence[];
        status: ADRStatus;
        last_review_action?: ADRReviewAction | null;
        review_note?: string | null;
        requested_information?: string[];
        reviewed_by?: string | null;
        reviewed_at?: string | null;
        created_at: string;
    }>;
    total: number;
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
    adherence_barriers?: Array<{
        target_type: string;
        target_id: string;
        barrier_code: string;
        notes?: string | null;
        logged_at: string;
    }>;
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

export interface ClinicianDocumentSource {
    file_name: string;
    file_url: string;
    mime_type: string;
    preview_url?: string | null;
    preview_mime_type?: string | null;
    preview_status?: string | null;
}

export interface ExtractedDocumentFact {
    id: string;
    fact_type: string;
    value: Record<string, unknown>;
    confidence_score?: number | null;
    confidence_band?: string;
    uncertainty?: string[];
    review_state: string;
    citations?: Array<{ excerpt?: string; location?: { page?: number } }>;
}

export interface CarePlanItem {
    id: string;
    source_fact_id?: string | null;
    category: string;
    title: string;
    instructions: string;
    frequency: string;
    schedule: Record<string, unknown>;
    medication: Record<string, unknown>;
    confidence_score?: number | null;
    uncertainty: string[];
    conflict: Record<string, unknown>;
    blocker_reason?: string | null;
    reviewed_locale?: string | null;
    is_removed: boolean;
    imported_evidence?: boolean;
    overlapping_item_ids?: string[];
    source?: {
        document_id?: string;
        file_name?: string | null;
        excerpt?: string;
        location?: { page?: number };
    } | null;
    sources?: Array<{
        document_id?: string;
        file_name?: string | null;
        excerpt?: string;
        location?: { page?: number };
    }>;
}

export interface CarePlanVersion {
    id: string;
    patient_id: string;
    version_number: number;
    status: "draft" | "approved" | "superseded" | "rejected" | "generation_failed";
    generated_at?: string | null;
    generation_error_code?: string | null;
    approved_at?: string | null;
    items: CarePlanItem[];
}

export interface CarePlanReviewContext {
    latest: CarePlanVersion | null;
    active: CarePlanVersion | null;
    patient_locale: string;
    active_medications: Array<{
        id: string;
        name: string;
        dosage: string;
        frequency: string;
        route: string;
        instructions?: string | null;
        care_plan_item_id?: string | null;
    }>;
}

export interface CarePlanGeneration {
    id: string;
    patient_id: string;
    status: "pending" | "processing" | "retry" | "completed" | "failed";
    attempts: number;
    requested_at: string;
    next_attempt_at?: string | null;
    completed_at?: string | null;
    failure_code?: string | null;
    plan_version_id?: string | null;
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
        parse_failure_code?: string;
        parse_attempts?: number;
        ai_summary?: string;
        summary_status?: string;
        summary_failure_code?: string;
        summary_attempts?: number;
        summary_next_attempt_at?: string;
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
    parse_failure_code?: string;
    parse_attempts?: number;
    ai_summary?: string;
    summary_status?: string;
    summary_failure_code?: string;
    summary_attempts?: number;
    summary_next_attempt_at?: string;
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
        parseFailureCode: document.parse_failure_code,
        parseAttempts: document.parse_attempts,
        aiSummary: document.ai_summary,
        summaryStatus: document.summary_status,
        summaryFailureCode: document.summary_failure_code,
        summaryAttempts: document.summary_attempts,
        summaryNextAttemptAt: document.summary_next_attempt_at,
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
        parseFailureCode: item.parse_failure_code,
        parseAttempts: item.parse_attempts,
        aiSummary: item.ai_summary,
        summaryStatus: item.summary_status,
        summaryFailureCode: item.summary_failure_code,
        summaryAttempts: item.summary_attempts,
        summaryNextAttemptAt: item.summary_next_attempt_at,
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

/** Fetch evidence-backed ADR assessments for the clinician's assigned patients. */
export async function fetchADRReviewQueue(): Promise<ADRReviewQueueItem[]> {
    const data = await apiFetch<ADRReviewQueueResponse>(
        "/api/v1/clinicians/me/adr-assessments?status=draft",
    );
    return data.items.map((item) => ({
        id: item.id,
        patientId: item.patient_id,
        patientFirstName: item.patient_first_name,
        patientLastName: item.patient_last_name,
        symptomReportId: item.symptom_report_id,
        symptom: item.symptom,
        severity: item.severity,
        onset: item.onset,
        symptomCreatedAt: item.symptom_created_at,
        suspectMedicationId: item.suspect_medication_id,
        suspectMedicationName: item.suspect_medication_name,
        naranjoScore: item.naranjo_score,
        causality: item.causality,
        naranjoAnswers: item.naranjo_answers,
        naranjoAssessment: item.naranjo_assessment,
        evidence: item.evidence,
        status: item.status,
        lastReviewAction: item.last_review_action,
        reviewNote: item.review_note,
        requestedInformation: item.requested_information ?? [],
        reviewedBy: item.reviewed_by,
        reviewedAt: item.reviewed_at,
        createdAt: item.created_at,
    }));
}

/** Persist an assigned clinician's auditable action on a draft ADR assessment. */
export async function reviewADRAssessment(
    assessmentId: string,
    input: ADRReviewDecisionInput,
): Promise<ADRReviewDecisionResult> {
    const result = await apiFetch<{
        id: string;
        patient_id: string;
        status: ADRStatus;
        last_review_action: ADRReviewAction;
        review_note?: string | null;
        requested_information: string[];
        reviewed_by: string;
        reviewed_at: string;
        dismiss_reason?: string | null;
        updated_at: string;
    }>(`/api/v1/clinicians/me/adr-assessments/${assessmentId}/review`, {
        method: "POST",
        body: JSON.stringify({
            action: input.action,
            note: input.note,
            requested_information: input.requestedInformation ?? [],
        }),
    });
    return {
        id: result.id,
        patientId: result.patient_id,
        status: result.status,
        lastReviewAction: result.last_review_action,
        reviewNote: result.review_note,
        requestedInformation: result.requested_information,
        reviewedBy: result.reviewed_by,
        reviewedAt: result.reviewed_at,
        dismissReason: result.dismiss_reason,
        updatedAt: result.updated_at,
    };
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

export async function retryClinicianDocumentIngestion(
    patientId: string,
    documentId: string,
): Promise<ClinicianPatientDocument> {
    const document = await apiFetch<PatientDeepDiveResponse["documents"][number]>(
        `/api/v1/documents/patients/${patientId}/${documentId}/ingestion/retry`,
        { method: "POST" },
    );
    return normalizePatientDocument(document);
}

/**
 * Requeue only the patient explanation.
 *
 * This re-reads candidates that already exist: it does not re-run OCR, propose a
 * clinical fact again, or change the document's parse state or stored source.
 */
export async function retryClinicianDocumentSummary(
    patientId: string,
    documentId: string,
): Promise<ClinicianPatientDocument> {
    const document = await apiFetch<PatientDeepDiveResponse["documents"][number]>(
        `/api/v1/documents/patients/${patientId}/${documentId}/summary/retry`,
        { method: "POST" },
    );
    return normalizePatientDocument(document);
}

/** Fetch a short-lived source URL only when an assigned clinician opens a document. */
export async function fetchClinicianDocumentSource(
    patientId: string,
    documentId: string,
): Promise<ClinicianDocumentSource> {
    return apiFetch<ClinicianDocumentSource>(
        `/api/v1/documents/patients/${patientId}/${documentId}/source`,
    );
}

/** List grounded facts for one document; this is a read-only review surface. */
export async function fetchExtractedDocumentFacts(
    patientId: string,
    documentId: string,
): Promise<ExtractedDocumentFact[]> {
    return apiFetch<ExtractedDocumentFact[]>(
        `/api/v1/clinicians/me/patients/${patientId}/documents/${documentId}/facts`,
    );
}

export async function fetchClinicianCarePlan(patientId: string): Promise<CarePlanVersion | null> {
    return apiFetch<CarePlanVersion | null>(`/api/v1/care-plans/clinician/patients/${patientId}`);
}

export async function fetchClinicianCarePlanReviewContext(
    patientId: string,
): Promise<CarePlanReviewContext> {
    return apiFetch<CarePlanReviewContext>(
        `/api/v1/care-plans/clinician/patients/${patientId}/review-context`,
    );
}

export async function fetchClinicianCarePlanGeneration(
    patientId: string,
): Promise<CarePlanGeneration | null> {
    return apiFetch<CarePlanGeneration | null>(
        `/api/v1/care-plans/clinician/patients/${patientId}/generation`,
    );
}

export interface CarePlanTodayPreview {
    plan_id: string;
    version_number: number;
    generated_at: string;
    feed: {
        date: string;
        timezone: string;
        tasks: Array<{
            id: string;
            name: string;
            description: string | null;
            frequency: string;
            status: "pending" | "completed" | "skipped" | "missed";
            scheduled_at: string | null;
            requires_schedule_configuration: boolean;
            care_plan: { version_number: number; category: string } | null;
        }>;
    };
}

export async function fetchCarePlanTodayPreview(
    patientId: string,
    planId: string,
): Promise<CarePlanTodayPreview> {
    return apiFetch(`/api/v1/care-plans/clinician/patients/${patientId}/${planId}/today-preview`);
}

export async function updateClinicianCarePlan(
    patientId: string,
    planId: string,
    items: Array<{
        id: string;
        title: string;
        instructions: string;
        frequency: string;
        schedule: Record<string, unknown>;
        medication: Record<string, unknown>;
        is_removed: boolean;
        clinician_confirmed: boolean;
        language_verified: boolean;
        verified_locale: "en-US" | "es-MX" | null;
    }>,
): Promise<CarePlanVersion> {
    return apiFetch<CarePlanVersion>(`/api/v1/care-plans/clinician/patients/${patientId}/${planId}`, {
        method: "PUT",
        body: JSON.stringify({ items }),
    });
}

export async function approveClinicianCarePlan(
    patientId: string,
    planId: string,
    note: string,
): Promise<{ status: string }> {
    return apiFetch(`/api/v1/care-plans/clinician/patients/${patientId}/${planId}/approve`, {
        method: "POST",
        body: JSON.stringify({ note }),
    });
}

export async function retryClinicianCarePlanGeneration(patientId: string): Promise<{ status: string }> {
    return apiFetch(`/api/v1/care-plans/clinician/patients/${patientId}/retry-generation`, {
        method: "POST",
    });
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

// ── Clinician messages ────────────────────────────────────────────────────────

interface ClinicianMessageResponse {
    id: string;
    clinician_id: string;
    patient_id: string;
    channel: string;
    subject?: string | null;
    body: string;
    is_read: boolean;
    created_at: string;
}

interface ClinicianMessageInboxResponse extends ClinicianMessageResponse {
    patient_first_name?: string | null;
    patient_last_name?: string | null;
}

export interface ClinicianMessageInboxItem extends ClinicianMessage {
    patientFirstName?: string | null;
    patientLastName?: string | null;
}

function normalizeClinicianMessage(msg: ClinicianMessageResponse): ClinicianMessage {
    return {
        id: msg.id,
        clinicianId: msg.clinician_id,
        patientId: msg.patient_id,
        channel: msg.channel as typeof MessageChannel[keyof typeof MessageChannel],
        subject: msg.subject ?? undefined,
        body: msg.body,
        isRead: msg.is_read,
        createdAt: msg.created_at,
    };
}

function normalizeInboxItem(msg: ClinicianMessageInboxResponse): ClinicianMessageInboxItem {
    return {
        ...normalizeClinicianMessage(msg),
        patientFirstName: msg.patient_first_name,
        patientLastName: msg.patient_last_name,
    };
}

/** List messages sent to a specific patient. */
export async function fetchPatientMessages(patientId: string): Promise<ClinicianMessage[]> {
    const data = await apiFetch<ClinicianMessageResponse[]>(
        `/api/v1/clinicians/me/patients/${patientId}/messages`,
    );
    return data.map(normalizeClinicianMessage);
}

/** List all messages sent by this clinician (inbox). */
export async function fetchAllSentMessages(): Promise<ClinicianMessageInboxItem[]> {
    const data = await apiFetch<ClinicianMessageInboxResponse[]>(
        "/api/v1/clinicians/me/messages",
    );
    return data.map(normalizeInboxItem);
}

/** Send an in-app message to an assigned patient. */
export async function sendPatientMessage(
    patientId: string,
    body: string,
    subject?: string,
): Promise<ClinicianMessage> {
    const msg = await apiFetch<ClinicianMessageResponse>(
        `/api/v1/clinicians/me/patients/${patientId}/message`,
        {
            method: "POST",
            body: JSON.stringify({ body, subject: subject || null }),
        },
    );
    return normalizeClinicianMessage(msg);
}
