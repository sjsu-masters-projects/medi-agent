/**
 * Clinician API service functions.
 *
 * All calls go through the base fetch wrapper with JWT auth headers.
 * Functions return typed data or throw on HTTP errors.
 */

import type { Medication, SymptomReport } from "@/types";
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
    risk_level: RiskLevel;
    adherence_score: number;
    medications: Medication[];
    adherence_series: AdherenceDataPoint[];
    symptom_reports: SymptomReport[];
    chat_messages: Array<{ role: string; content: string; created_at: string }>;
    conditions: Array<{ name?: string; icd10_code?: string; created_at?: string }>;
    allergies: Array<{ allergen: string; severity?: string }>;
    documents: Array<{
        id: string;
        file_name: string;
        document_type: string;
        parse_status: string;
        ai_summary?: string;
        created_at: string;
        uploaded_by_role: string;
        clinician_annotation?: string;
    }>;
    latest_soap_note?: SoapNoteResponse;
    obligations?: Array<{
        id: string;
        obligation_type: string;
        description: string;
        frequency: string;
        is_active: boolean;
        created_at?: string;
    }>;
    obligation_completion_rate?: number;
}

export interface ObligationSetPayload {
    obligation_type: "diet" | "exercise" | "custom";
    description: string;
    frequency: string;
    notes?: string;
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

/** Fetch full patient deep dive data (all sub-resources). */
export async function fetchPatientDeepDive(patientId: string): Promise<PatientDeepDive> {
    const data = await apiFetch<PatientDeepDive>(
        `/api/v1/clinicians/me/patients/${patientId}/deep-dive`,
    );

    return {
        ...data,
        medications: (data.medications ?? []).map((m) =>
            normalizeMedication(m as unknown as Record<string, unknown>),
        ),
        symptom_reports: (data.symptom_reports ?? []).map((s) =>
            normalizeSymptomReport(s as unknown as Record<string, unknown>),
        ),
    };
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
