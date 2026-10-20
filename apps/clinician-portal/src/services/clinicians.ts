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
import type {
    MedWatchFormDataV2,
    MedWatchGateIssue,
    MedWatchNameWarning,
} from "@/services/medwatch-form-3500";
import { fetchWithReadRecovery } from "../../../../packages/shared/src/utils/api-transport";

// ── Base config ──────────────────────────────────────────────────────────────

const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
    const token =
        typeof window !== "undefined"
            ? readStoredSession()?.accessToken ?? ""
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
    /** Keep one clinic's patients (a clinic the clinician belongs to). */
    clinicId?: string | null;
}

export interface PatientRiskData {
    patient_id: string;
    first_name: string;
    last_name: string;
    risk_level: RiskLevel;
    adherence_score: number;
    open_adr_count: number;
    active_med_count: number;
    recent_symptom_severity: number | null;
    last_activity: string;
    /** The clinic of the clinician's link to this patient. */
    clinic_id?: string | null;
    clinic_name?: string | null;
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
    /** Absent for AI extraction; `patient_follow_up` for a patient-confirmed answer. */
    source?: string | null;
    /** The information request a patient-confirmed answer responded to. */
    information_request_id?: string | null;
    question: string;
}

export interface ADRReviewQueueItem {
    clinicId?: string | null;
    clinicName?: string | null;
    id: string;
    patientId: string;
    patientFirstName: string;
    patientLastName: string;
    symptomReportId: string;
    symptom: string;
    severity: number | null;
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
    informationRequestId?: string | null;
    informationRequestStatus?: "pending" | "answered" | "cancelled" | null;
    patientResponses: ADRReviewEvidence[];
    patientRespondedAt?: string | null;
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
        clinic_id?: string | null;
        clinic_name?: string | null;
        id: string;
        patient_id: string;
        patient_first_name: string;
        patient_last_name: string;
        symptom_report_id: string;
        symptom: string;
        severity: number | null;
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
        information_request_id?: string | null;
        information_request_status?: "pending" | "answered" | "cancelled" | null;
        patient_responses?: ADRReviewEvidence[];
        patient_responded_at?: string | null;
        created_at: string;
    }>;
    total: number;
}

export type MedWatchDraftStatus = "draft" | "reviewed" | "submitted";

/** Which list the MedWatch page shows (`?state=`). */
export type MedWatchDraftState = "active" | "draft" | "approved" | "submitted" | "discarded";

export type MedWatchFormData = MedWatchFormDataV2;
export type { MedWatchGateIssue, MedWatchNameWarning } from "@/services/medwatch-form-3500";

export interface MedWatchEvidenceReference {
    field_paths: string[];
    source_type: string;
    source_id?: string | null;
    attribution: string;
    excerpt?: string | null;
    citation?: string | null;
}

export type MedWatchSubmissionMethod = "medwatch_online" | "fax" | "mail" | "other";

export const SUBMISSION_METHOD_LABELS: Record<MedWatchSubmissionMethod, string> = {
    medwatch_online: "MedWatch Online",
    fax: "Fax",
    mail: "Mail",
    other: "Other",
};

/** A clinician's record that they submitted the report to FDA outside MediAgent. */
export interface MedWatchSubmissionRecord {
    id: string;
    submittedOn: string;
    method: MedWatchSubmissionMethod;
    methodDetail: string | null;
    fdaReference: string | null;
    recordedBy: string | null;
    recordedByName: string | null;
    createdAt: string;
    amendsId: string | null;
    amendReason: string | null;
}

interface MedWatchSubmissionResponse {
    id: string;
    submitted_on: string;
    method: MedWatchSubmissionMethod;
    method_detail?: string | null;
    fda_reference?: string | null;
    recorded_by?: string | null;
    recorded_by_name?: string | null;
    created_at: string;
    amends_id?: string | null;
    amend_reason?: string | null;
}

export interface MedWatchAttestation {
    version: string;
    text: string;
}

/** The vendored Form 3500 revision and whether it may have been superseded (R15.5). */
export interface Form3500TemplateInfo {
    revision: string;
    expires: string;
    maySuperseded: boolean;
}

interface Form3500TemplateResponse {
    revision: string;
    expires: string;
    may_be_superseded: boolean;
}

/** The pinned template record (backend `assets/fda/TEMPLATE.json`), used when a response omits it. */
export const FORM_3500_TEMPLATE = { revision: "09/2025", expires: "2027-09-30" } as const;

/** Today's calendar date at the clinic (America/Los_Angeles), as `YYYY-MM-DD`. */
export function clinicTodayIso(now: Date = new Date()): string {
    const parts = new Intl.DateTimeFormat("en-CA", {
        timeZone: "America/Los_Angeles",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
    }).formatToParts(now);
    const part = (type: string) => parts.find((entry) => entry.type === type)?.value ?? "";
    return `${part("year")}-${part("month")}-${part("day")}`;
}

export function form3500TemplateInfo(
    template?: Form3500TemplateResponse | null,
    now: Date = new Date(),
): Form3500TemplateInfo {
    if (template) {
        return {
            revision: template.revision,
            expires: template.expires,
            maySuperseded: template.may_be_superseded,
        };
    }
    return {
        ...FORM_3500_TEMPLATE,
        maySuperseded: clinicTodayIso(now) > FORM_3500_TEMPLATE.expires,
    };
}

export interface MedWatchDraft {
    clinicId?: string | null;
    clinicName?: string | null;
    id: string;
    adrAssessmentId: string;
    patientId: string;
    formData: MedWatchFormData;
    sourceEvidence: MedWatchEvidenceReference[];
    clinicianEditedFields: string[];
    status: MedWatchDraftStatus;
    createdBy?: string | null;
    approvedBy?: string | null;
    approvedAt?: string | null;
    approvalNote?: string | null;
    revision: number;
    exportVersion: string;
    createdAt: string;
    updatedAt: string;
    missingForApproval: MedWatchGateIssue[];
    nameWarnings: MedWatchNameWarning[];
    currentSubmission: MedWatchSubmissionRecord | null;
    /** Every submission record for the draft, newest first (original and amendments). */
    submissionHistory: MedWatchSubmissionRecord[];
    attestation: MedWatchAttestation | null;
    template: Form3500TemplateInfo;
    /** False when an approved draft cannot be filled into the PDF (an incomplete earlier draft). */
    pdfAvailable: boolean;
    discardedAt: string | null;
    discardReason: string | null;
}

interface MedWatchDraftResponse {
    clinic_id?: string | null;
    clinic_name?: string | null;
    id: string;
    adr_assessment_id: string;
    patient_id: string;
    form_data: MedWatchFormData;
    source_evidence: MedWatchEvidenceReference[];
    clinician_edited_fields: string[];
    status: MedWatchDraftStatus;
    created_by?: string | null;
    approved_by?: string | null;
    approved_at?: string | null;
    approval_note?: string | null;
    revision: number;
    export_version: string;
    created_at: string;
    updated_at: string;
    missing_for_approval?: MedWatchGateIssue[];
    name_warnings?: MedWatchNameWarning[];
    current_submission?: MedWatchSubmissionResponse | null;
    submission_history?: MedWatchSubmissionResponse[];
    attestation?: MedWatchAttestation | null;
    template?: Form3500TemplateResponse | null;
    pdf_available?: boolean;
    discarded_at?: string | null;
    discard_reason?: string | null;
}

export interface MedWatchDraftExport {
    filename: string;
    media_type: string;
    content: Record<string, unknown>;
}

function mapSubmission(record: MedWatchSubmissionResponse): MedWatchSubmissionRecord {
    return {
        id: record.id,
        submittedOn: record.submitted_on,
        method: record.method,
        methodDetail: record.method_detail ?? null,
        fdaReference: record.fda_reference ?? null,
        recordedBy: record.recorded_by ?? null,
        recordedByName: record.recorded_by_name ?? null,
        createdAt: record.created_at,
        amendsId: record.amends_id ?? null,
        amendReason: record.amend_reason ?? null,
    };
}

function mapMedWatchDraft(draft: MedWatchDraftResponse): MedWatchDraft {
    const current = draft.current_submission ? mapSubmission(draft.current_submission) : null;
    const history = (draft.submission_history ?? []).map(mapSubmission);
    return {
        clinicId: draft.clinic_id ?? null,
        clinicName: draft.clinic_name ?? null,
        id: draft.id,
        adrAssessmentId: draft.adr_assessment_id,
        patientId: draft.patient_id,
        formData: draft.form_data,
        sourceEvidence: draft.source_evidence,
        clinicianEditedFields: draft.clinician_edited_fields,
        status: draft.status,
        createdBy: draft.created_by,
        approvedBy: draft.approved_by,
        approvedAt: draft.approved_at,
        approvalNote: draft.approval_note,
        revision: draft.revision,
        exportVersion: draft.export_version,
        createdAt: draft.created_at,
        updatedAt: draft.updated_at,
        missingForApproval: draft.missing_for_approval ?? [],
        nameWarnings: draft.name_warnings ?? [],
        currentSubmission: current,
        submissionHistory: history.length > 0 ? history : current ? [current] : [],
        attestation: draft.attestation ?? null,
        template: form3500TemplateInfo(draft.template),
        pdfAvailable: draft.pdf_available ?? true,
        discardedAt: draft.discarded_at ?? null,
        discardReason: draft.discard_reason ?? null,
    };
}

// ── Form 3500 preview (GET /medwatch-drafts/{id}/preview) ───────────────────────

/** Where a previewed value came from. Only `ai_extracted` may carry the AI chip. */
export type Form3500ProvenanceKind =
    | "record"
    | "ai_extracted"
    | "patient_confirmed"
    | "clinician_edited";

export interface Form3500Provenance {
    kind: Form3500ProvenanceKind;
    sourceType: string | null;
    attribution: string | null;
    citation: string | null;
}

interface Form3500ProvenanceResponse {
    kind?: Form3500ProvenanceKind | null;
    source_type?: string | null;
    attribution?: string | null;
    citation?: string | null;
}

export interface Form3500PreviewItem {
    item: string;
    label: string;
    path: string;
    value: string | null;
    provenance: Form3500Provenance[];
    /** Gate codes that block approval on this item (the same rule approval enforces). */
    missingForApproval: string[];
}

export interface Form3500PreviewSection {
    id: string;
    title: string;
    notCompletedByMediAgent: boolean;
    items: Form3500PreviewItem[];
}

export interface Form3500Preview {
    draftId: string;
    status: MedWatchDraftStatus;
    sections: Form3500PreviewSection[];
    missingForApproval: MedWatchGateIssue[];
    mediagentReview: {
        naranjoScore: number | null;
        causality: string | null;
        reportabilityRationale: string;
    };
    legacy: Record<string, string>;
    template: Form3500TemplateInfo;
}

interface Form3500PreviewResponse {
    draft_id: string;
    status: MedWatchDraftStatus;
    sections: Array<{
        section: string;
        title: string;
        completion: "mediagent" | "not_completed_by_mediagent";
        items?: Array<{
            item: string;
            label: string;
            path: string;
            value?: string | null;
            provenance?: Form3500ProvenanceResponse[];
            missing_for_approval?: string[];
        }>;
    }>;
    missing_for_approval?: MedWatchGateIssue[];
    mediagent_review?: {
        naranjo_score?: number | null;
        causality?: string | null;
        reportability_rationale?: string | null;
    };
    legacy?: Record<string, string>;
    template?: Form3500TemplateResponse | null;
}

/** Classify a provenance entry; an entry is AI-extracted only when its source says so. */
export function provenanceKind(entry: Form3500ProvenanceResponse): Form3500ProvenanceKind {
    if (entry.kind) return entry.kind;
    const source = (entry.source_type ?? "").toLowerCase();
    if (source === "patient_follow_up" || source.startsWith("patient_confirmed")) {
        return "patient_confirmed";
    }
    if (source.includes("ai_extract")) return "ai_extracted";
    if (source.startsWith("clinician_edit")) return "clinician_edited";
    return "record";
}

function mapPreview(preview: Form3500PreviewResponse): Form3500Preview {
    return {
        draftId: preview.draft_id,
        status: preview.status,
        sections: preview.sections.map((section) => ({
            id: section.section,
            title: section.title,
            notCompletedByMediAgent: section.completion === "not_completed_by_mediagent",
            items: (section.items ?? []).map((item) => ({
                item: item.item,
                label: item.label,
                path: item.path,
                value: item.value ?? null,
                provenance: (item.provenance ?? []).map((entry) => ({
                    kind: provenanceKind(entry),
                    sourceType: entry.source_type ?? null,
                    attribution: entry.attribution ?? null,
                    citation: entry.citation ?? null,
                })),
                missingForApproval: item.missing_for_approval ?? [],
            })),
        })),
        missingForApproval: preview.missing_for_approval ?? [],
        mediagentReview: {
            naranjoScore: preview.mediagent_review?.naranjo_score ?? null,
            causality: preview.mediagent_review?.causality ?? null,
            reportabilityRationale: preview.mediagent_review?.reportability_rationale ?? "",
        },
        legacy: preview.legacy ?? {},
        template: form3500TemplateInfo(preview.template),
    };
}

// ── MedWatch error codes ──────────────────────────────────────────────────────

/**
 * A MedWatch request failure. It carries the server's error code and HTTP status only;
 * the server's message text is never shown, so the portal owns every visible sentence.
 */
export class MedWatchRequestError extends Error {
    readonly code: string;
    readonly status: number;

    constructor(code: string, status: number) {
        super(medWatchErrorMessage(code, status));
        this.name = "MedWatchRequestError";
        this.code = code;
        this.status = status;
    }
}

const MEDWATCH_ERROR_MESSAGES: Record<string, string> = {
    MEDWATCH_APPROVAL_INCOMPLETE:
        "Approval is blocked until the missing items are complete. Refresh to see the current list.",
    MEDWATCH_LEGACY_DRAFT_INCOMPLETE:
        "This earlier draft cannot be downloaded as Form 3500. Discard it and prepare a new draft.",
    FORM_3500_TEMPLATE_MISMATCH:
        "The Form 3500 template failed its integrity check, so no PDF was produced. Contact support.",
    FORM_3500_RENDER_FAILED: "The Form 3500 PDF could not be produced. Try again.",
    NETWORK: "Could not connect. Check your connection and try again.",
};

export function medWatchErrorMessage(code: string, status: number): string {
    if (MEDWATCH_ERROR_MESSAGES[code]) return MEDWATCH_ERROR_MESSAGES[code];
    if (status === 409) {
        return "This draft changed since you opened it. Refresh, then try again.";
    }
    if (status === 403) return "You are no longer assigned to this patient.";
    if (status === 404) return "This MedWatch draft is no longer available.";
    if (status === 422) {
        return "This action is not allowed for the draft in its current state, or a value is invalid.";
    }
    return "Unable to complete this action. Try again.";
}

function toMedWatchError(error: unknown): MedWatchRequestError {
    if (error instanceof MedWatchRequestError) return error;
    if (error instanceof ApiClientError) {
        const details = error.details as { error?: { code?: unknown } } | null;
        const code = typeof details?.error?.code === "string" ? details.error.code : "";
        return new MedWatchRequestError(code, error.status);
    }
    return new MedWatchRequestError("NETWORK", 0);
}

async function medwatchCall<T>(request: () => Promise<T>): Promise<T> {
    try {
        return await request();
    } catch (error) {
        throw toMedWatchError(error);
    }
}

const MEDWATCH_BASE = "/api/v1/clinicians/me/medwatch-drafts";

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
    /** The clinic of the clinician's link to this patient. */
    clinic_id?: string | null;
    clinic_name?: string | null;
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
    /** LOC-003: English display fields when the source is Spanish. */
    display_value?: Record<string, unknown> | null;
    /** LOC-003: Language the fact was originally extracted in. */
    display_locale?: string | null;
    confidence_score?: number | null;
    confidence_band?: string;
    uncertainty?: string[];
    review_state: string;
    citations?: Array<{ excerpt?: string; location?: { page?: number } }>;
}

export type CarePlanLocale = "en-US" | "es-MX";
export type CarePlanWording = { title: string; instructions: string; frequency: string };
/** Where each language's wording came from: the source, an AI draft, or a clinician edit. */
export type CarePlanWordingOrigin = "source" | "ai_draft" | "clinician_edited";

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
    source_locale?: CarePlanLocale | null;
    /** DV-004: language of the source evidence (fact/document), not the authored wording. */
    source_evidence_locale?: CarePlanLocale | null;
    wording?: Partial<Record<CarePlanLocale, CarePlanWording>>;
    wording_origin?: Partial<Record<CarePlanLocale, CarePlanWordingOrigin>>;
    wording_verified?: boolean;
    is_removed: boolean;
    imported_evidence?: boolean;
    overlapping_item_ids?: string[];
    source?: {
        upload_review_status?: string | null;
        document_id?: string;
        file_name?: string | null;
        excerpt?: string;
        location?: { page?: number };
    } | null;
    sources?: Array<{
        upload_review_status?: string | null;
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
        display_title?: Partial<Record<"en-US" | "es-MX", string>> | null;
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
    clinic_id?: string | null;
    clinic_name?: string | null;
    id: string;
    patient_id: string;
    patient_first_name: string;
    patient_last_name: string;
    file_name: string;
    display_title?: Partial<Record<"en-US" | "es-MX", string>> | null;
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
        severity: typeof raw.severity === "number" ? raw.severity : null,
        confirmationState: raw.confirmation_state === "patient_confirmed" ? "patient_confirmed" : "legacy_unconfirmed",
        confirmedAt: typeof raw.confirmed_at === "string" ? raw.confirmed_at : undefined,
        confirmedSummary: typeof (raw.confirmed_content as Record<string, unknown> | undefined)?.summary === "string"
            ? String((raw.confirmed_content as Record<string, unknown>).summary) : undefined,
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
        displayTitle: document.display_title ?? undefined,
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
): ClinicReviewQueueItem {
    return {
        clinicId: item.clinic_id ?? null,
        clinicName: item.clinic_name ?? null,
        id: item.id,
        patientId: item.patient_id,
        patientFirstName: item.patient_first_name,
        patientLastName: item.patient_last_name,
        fileName: item.file_name,
        displayTitle: item.display_title ?? undefined,
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
    if (params?.clinicId) search.set("clinic_id", params.clinicId);

    const qs = search.toString();
    return apiFetch<DashboardResponse>(`/api/v1/clinicians/me/dashboard${qs ? `?${qs}` : ""}`);
}

type ADRReviewResponseItem = ADRReviewQueueResponse["items"][number];

function mapADRReviewItem(item: ADRReviewResponseItem): ADRReviewQueueItem {
    return {
        clinicId: item.clinic_id ?? null,
        clinicName: item.clinic_name ?? null,
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
        informationRequestId: item.information_request_id,
        informationRequestStatus: item.information_request_status,
        patientResponses: item.patient_responses ?? [],
        patientRespondedAt: item.patient_responded_at,
        createdAt: item.created_at,
    };
}

export interface ADRReviewQueueFilter {
    /** `draft` (the default) is the open queue; `all` lists every status. */
    status?: ADRStatus | "all";
    patientId?: string;
    clinicId?: string | null;
}

/** Fetch evidence-backed ADR assessments for the clinician's assigned patients. */
export async function fetchADRReviewQueue(
    filter: ADRReviewQueueFilter = {},
): Promise<ADRReviewQueueItem[]> {
    const search = new URLSearchParams({ status: filter.status ?? "draft", limit: "200" });
    if (filter.patientId) search.set("patient_id", filter.patientId);
    if (filter.clinicId) search.set("clinic_id", filter.clinicId);
    const data = await apiFetch<ADRReviewQueueResponse>(
        `/api/v1/clinicians/me/adr-assessments?${search.toString()}`,
    );
    return data.items.map(mapADRReviewItem);
}

/** One assessment of any status; an unknown or unassigned id is a 404. */
export async function fetchADRAssessment(assessmentId: string): Promise<ADRReviewQueueItem> {
    return mapADRReviewItem(
        await apiFetch<ADRReviewResponseItem>(
            `/api/v1/clinicians/me/adr-assessments/${encodeURIComponent(assessmentId)}`,
        ),
    );
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

/** Convert a reviewed ADR decision into an editable, never-submitted MedWatch draft. */
export async function createMedWatchDraft(
    assessmentId: string,
    reportabilityRationale: string,
): Promise<MedWatchDraft> {
    const result = await apiFetch<MedWatchDraftResponse>(
        `/api/v1/clinicians/me/adr-assessments/${assessmentId}/medwatch-draft`,
        {
            method: "POST",
            body: JSON.stringify({
                decision: "prepare_draft",
                reportability_rationale: reportabilityRationale,
            }),
        },
    );
    return mapMedWatchDraft(result);
}

/** Fetch the active (default), submitted or discarded drafts for assigned patients. */
export async function fetchMedWatchDrafts(
    state: MedWatchDraftState = "active",
    clinicId?: string | null,
): Promise<MedWatchDraft[]> {
    const clinic = clinicId ? `&clinic_id=${encodeURIComponent(clinicId)}` : "";
    const result = await apiFetch<{
        items: MedWatchDraftResponse[];
        total: number;
    }>(`${MEDWATCH_BASE}?state=${encodeURIComponent(state)}${clinic}`);
    return result.items.map(mapMedWatchDraft);
}

/** One draft the clinician can read; an unknown or unassigned id is a 404. */
export async function fetchMedWatchDraft(draftId: string): Promise<MedWatchDraft> {
    return medwatchCall(async () =>
        mapMedWatchDraft(
            await apiFetch<MedWatchDraftResponse>(`${MEDWATCH_BASE}/${encodeURIComponent(draftId)}`),
        ),
    );
}

/** Save all editable fields using optimistic revision control. */
export async function updateMedWatchDraft(
    draftId: string,
    formData: MedWatchFormData,
    expectedRevision: number,
): Promise<MedWatchDraft> {
    return medwatchCall(async () =>
        mapMedWatchDraft(
            await apiFetch<MedWatchDraftResponse>(`${MEDWATCH_BASE}/${draftId}`, {
                method: "PUT",
                body: JSON.stringify({
                    form_data: formData,
                    expected_revision: expectedRevision,
                }),
            }),
        ),
    );
}

export interface MedWatchApprovalInput {
    approvalNote: string;
    expectedRevision: number;
    /** The attestation version the clinician was shown (from the draft). */
    attestationVersion: string;
    nonSeriousAttested: boolean;
    acknowledgedWarnings: MedWatchNameWarning[];
}

/** Record explicit clinician sign-off. This does not file the draft externally. */
export async function approveMedWatchDraft(
    draftId: string,
    input: MedWatchApprovalInput,
): Promise<MedWatchDraft> {
    return medwatchCall(async () =>
        mapMedWatchDraft(
            await apiFetch<MedWatchDraftResponse>(`${MEDWATCH_BASE}/${draftId}/approve`, {
                method: "POST",
                body: JSON.stringify({
                    approval_note: input.approvalNote,
                    expected_revision: input.expectedRevision,
                    attested: true,
                    attestation_version: input.attestationVersion,
                    non_serious_attested: input.nonSeriousAttested,
                    acknowledged_warnings: input.acknowledgedWarnings.map((warning) => ({
                        path: warning.path,
                        kind: warning.kind,
                    })),
                }),
            }),
        ),
    );
}

/** Export an approved JSON artifact. The backend never submits it to the FDA. */
export async function exportMedWatchDraft(
    draftId: string,
): Promise<MedWatchDraftExport> {
    return medwatchCall(() => apiFetch<MedWatchDraftExport>(`${MEDWATCH_BASE}/${draftId}/export`));
}

/** Read-only Form 3500 layout of a draft in any status. */
export async function fetchForm3500Preview(draftId: string): Promise<Form3500Preview> {
    return medwatchCall(async () =>
        mapPreview(await apiFetch<Form3500PreviewResponse>(`${MEDWATCH_BASE}/${draftId}/preview`)),
    );
}

export interface Form3500PdfDownload {
    blob: Blob;
    filename: string;
}

/** The fallback equals the server's name: `fda-3500-<first 8 of id>-not-submitted.pdf`. */
export function form3500PdfFilename(draftId: string, contentDisposition?: string | null): string {
    const match = /filename="?([^";]+)"?/i.exec(contentDisposition ?? "");
    const name = match?.[1]?.trim();
    // Keep only a plain file name; never a path from the header.
    if (name && /^[\w.-]+\.pdf$/i.test(name)) return name;
    return `fda-3500-${draftId.slice(0, 8)}-not-submitted.pdf`;
}

/**
 * The watermarked "DRAFT - not for submission" Form 3500 for the preview step. It is not an
 * export: the server records nothing, so it can be fetched again freely.
 */
export async function fetchForm3500PreviewPdf(draftId: string): Promise<Blob> {
    const token =
        typeof window !== "undefined"
            ? readStoredSession()?.accessToken ?? ""
            : "";
    if (!token) throw new MedWatchRequestError("AUTHENTICATION_ERROR", 401);
    let response: Response;
    try {
        response = await fetch(`${API_BASE}${MEDWATCH_BASE}/${draftId}/preview.pdf`, {
            headers: { Accept: "application/pdf", Authorization: `Bearer ${token}` },
        });
    } catch {
        throw new MedWatchRequestError("NETWORK", 0);
    }
    if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as { error?: { code?: unknown } };
        const code = typeof body?.error?.code === "string" ? body.error.code : "";
        throw new MedWatchRequestError(code, response.status);
    }
    return response.blob();
}

/**
 * Download the official Form 3500 PDF filled from the approved revision. Each successful
 * download is audited by the server, so the request is sent once and never replayed.
 */
export async function downloadForm3500Pdf(draftId: string): Promise<Form3500PdfDownload> {
    const token =
        typeof window !== "undefined"
            ? readStoredSession()?.accessToken ?? ""
            : "";
    if (!token) throw new MedWatchRequestError("AUTHENTICATION_ERROR", 401);
    let response: Response;
    try {
        response = await fetch(`${API_BASE}${MEDWATCH_BASE}/${draftId}/export.pdf`, {
            headers: { Accept: "application/pdf", Authorization: `Bearer ${token}` },
        });
    } catch {
        throw new MedWatchRequestError("NETWORK", 0);
    }
    if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as {
            error?: { code?: unknown };
        };
        const code = typeof body?.error?.code === "string" ? body.error.code : "";
        throw new MedWatchRequestError(code, response.status);
    }
    return {
        blob: await response.blob(),
        filename: form3500PdfFilename(draftId, response.headers.get("Content-Disposition")),
    };
}

export interface MedWatchDiscardInput {
    reason: string;
    expectedRevision: number;
}

/** Discard a draft with a reason; the ADR assessment returns to review. */
export async function discardMedWatchDraft(
    draftId: string,
    input: MedWatchDiscardInput,
): Promise<void> {
    await medwatchCall(() =>
        apiFetch<unknown>(`${MEDWATCH_BASE}/${draftId}/discard`, {
            method: "POST",
            body: JSON.stringify({
                reason: input.reason,
                expected_revision: input.expectedRevision,
            }),
        }),
    );
}

export interface MedWatchSubmissionInput {
    submittedOn: string;
    method: MedWatchSubmissionMethod;
    methodDetail: string;
    fdaReference: string;
}

function submissionBody(input: MedWatchSubmissionInput) {
    return {
        submitted_on: input.submittedOn,
        method: input.method,
        method_detail: input.method === "other" ? input.methodDetail.trim() : null,
        fda_reference: input.fdaReference.trim() || null,
    };
}

/** Record that the clinician submitted the approved report to FDA outside MediAgent. */
export async function recordMedWatchSubmission(
    draftId: string,
    input: MedWatchSubmissionInput & { expectedRevision: number },
): Promise<void> {
    await medwatchCall(() =>
        apiFetch<unknown>(`${MEDWATCH_BASE}/${draftId}/submission`, {
            method: "POST",
            body: JSON.stringify({
                ...submissionBody(input),
                attested: true,
                expected_revision: input.expectedRevision,
            }),
        }),
    );
}

/** Correct the current submission record; the original stays in the history. */
export async function amendMedWatchSubmission(
    draftId: string,
    input: MedWatchSubmissionInput & { amendsId: string; reason: string },
): Promise<void> {
    await medwatchCall(() =>
        apiFetch<unknown>(`${MEDWATCH_BASE}/${draftId}/submission/amend`, {
            method: "POST",
            body: JSON.stringify({
                amends_id: input.amendsId,
                ...submissionBody(input),
                reason: input.reason.trim(),
            }),
        }),
    );
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

/** A pending upload with the clinic of the clinician's link to its patient. */
export type ClinicReviewQueueItem = DocumentReviewQueueItem & {
    clinicId?: string | null;
    clinicName?: string | null;
};

export async function fetchDocumentReviewQueue(
    clinicId?: string | null,
): Promise<ClinicReviewQueueItem[]> {
    const clinic = clinicId ? `?clinic_id=${encodeURIComponent(clinicId)}` : "";
    const data = await apiFetch<DocumentReviewQueueItemResponse[]>(
        `/api/v1/clinicians/me/document-review-queue${clinic}`,
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
        wording: Partial<Record<CarePlanLocale, CarePlanWording>>;
        wording_verified: boolean;
        source_locale: CarePlanLocale | null;
    }>,
): Promise<CarePlanVersion> {
    return apiFetch<CarePlanVersion>(`/api/v1/care-plans/clinician/patients/${patientId}/${planId}`, {
        method: "PUT",
        body: JSON.stringify({ items }),
    });
}

/** Redraft the other language of one draft item from its saved source wording. */
export async function translateClinicianCarePlanItem(
    patientId: string,
    planId: string,
    itemId: string,
    fromLocale: CarePlanLocale,
): Promise<CarePlanVersion> {
    return apiFetch<CarePlanVersion>(
        `/api/v1/care-plans/clinician/patients/${patientId}/${planId}/items/${itemId}/translate`,
        { method: "POST", body: JSON.stringify({ from_locale: fromLocale }) },
    );
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

// ── LOC-003: Back-translation ─────────────────────────────────────────────

export interface BackTranslationResult {
    back_translation: { title: string; instructions: string; frequency: string };
    guards: { numbers_match: boolean; medication_names_match: boolean };
}

/** LOC-003: Fetch an English back-translation of the Spanish wording for verification. */
export async function fetchBackTranslation(
    patientId: string,
    planId: string,
    itemId: string,
): Promise<BackTranslationResult> {
    return apiFetch<BackTranslationResult>(
        `/api/v1/care-plans/clinician/patients/${patientId}/${planId}/items/${itemId}/back-translate`,
    );
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
    clinic_id?: string | null;
    clinic_name?: string | null;
    patient_first_name?: string | null;
    patient_last_name?: string | null;
}

export interface ClinicianMessageInboxItem extends ClinicianMessage {
    clinicId?: string | null;
    clinicName?: string | null;
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
        clinicId: msg.clinic_id ?? null,
        clinicName: msg.clinic_name ?? null,
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
export async function fetchAllSentMessages(
    clinicId?: string | null,
): Promise<ClinicianMessageInboxItem[]> {
    const clinic = clinicId ? `?clinic_id=${encodeURIComponent(clinicId)}` : "";
    const data = await apiFetch<ClinicianMessageInboxResponse[]>(
        `/api/v1/clinicians/me/messages${clinic}`,
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
