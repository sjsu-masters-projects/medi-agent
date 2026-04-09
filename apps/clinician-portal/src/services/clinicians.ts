/**
 * Clinician API service functions.
 *
 * All calls go through the base fetch wrapper with JWT auth headers.
 * Functions return typed data or throw on HTTP errors.
 */

import type {
    AdherenceStats,
    Appointment,
    Document,
    Medication,
    SymptomReport,
} from "@/types";

// ── Base config ──────────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
    // The auth token is stored in localStorage (set by Supabase Auth on login)
    const token =
        typeof window !== "undefined" ? localStorage.getItem("access_token") ?? "" : "";

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

export interface PatientRiskData {
    patient_id: string;
    first_name: string;
    last_name: string;
    risk_level: "low" | "medium" | "high";
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
    risk_level: "low" | "medium" | "high";
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
}

export interface ObligationSetPayload {
    obligation_type: string;
    description: string;
    frequency: string;
    notes?: string;
}

// ── API functions ─────────────────────────────────────────────────────────────

/** Fetch aggregated risk dashboard for all assigned patients. */
export async function fetchDashboard(): Promise<DashboardResponse> {
    return apiFetch<DashboardResponse>("/api/v1/clinicians/me/dashboard");
}

/** Fetch full patient deep dive data (all sub-resources). */
export async function fetchPatientDeepDive(patientId: string): Promise<PatientDeepDive> {
    return apiFetch<PatientDeepDive>(`/api/v1/clinicians/me/patients/${patientId}/deep-dive`);
}

/** Trigger Summarization Agent to generate a SOAP note. */
export async function generateSoapNote(
    patientId: string,
    lookbackDays = 30,
): Promise<{ status: string; soap_note_id?: string; soap_note: SoapNote }> {
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
