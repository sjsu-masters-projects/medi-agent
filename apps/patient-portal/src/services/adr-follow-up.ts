import { ApiTransportError } from "../../../../packages/shared/src/utils/api-transport";
import { api, ApiClientError } from "@/services/api";

export type PatientADRQuestion =
    | "reappeared_on_rechallenge"
    | "dose_response"
    | "similar_previous_reaction";

export type PatientADRAnswer = "yes" | "no" | "do_not_know";

interface ADRInformationRequestApiRecord {
    id: string;
    adr_assessment_id: string;
    symptom: string;
    symptom_severity: number;
    suspect_medication_name: string;
    requested_information: PatientADRQuestion[];
    patient_message: string;
    current_naranjo_score: number;
    current_causality: string;
    status: "pending";
    created_at: string;
}

export interface ADRInformationRequest {
    id: string;
    assessmentId: string;
    symptom: string;
    symptomSeverity: number;
    suspectMedicationName: string;
    requestedInformation: PatientADRQuestion[];
    patientMessage: string;
    createdAt: string;
}

export interface ADRInformationAnswerInput {
    question: PatientADRQuestion;
    answer: PatientADRAnswer;
    evidence?: string;
}

export interface ADRInformationResponseResult {
    request_id: string;
    adr_assessment_id: string;
    status: "answered";
    naranjo_score: number;
    causality: string;
    responded_at: string;
}

export async function fetchADRInformationRequests(
    token: string,
): Promise<ADRInformationRequest[]> {
    const records = await api.get<ADRInformationRequestApiRecord[]>(
        "/api/v1/patients/me/adr-information-requests",
        { token },
    );
    return records.map((record) => ({
        id: record.id,
        assessmentId: record.adr_assessment_id,
        symptom: record.symptom,
        symptomSeverity: record.symptom_severity,
        suspectMedicationName: record.suspect_medication_name,
        requestedInformation: record.requested_information,
        patientMessage: record.patient_message,
        createdAt: record.created_at,
    }));
}

export async function respondToADRInformationRequest(
    token: string,
    requestId: string,
    answers: ADRInformationAnswerInput[],
): Promise<ADRInformationResponseResult> {
    return api.post<ADRInformationResponseResult>(
        `/api/v1/patients/me/adr-information-requests/${requestId}/respond`,
        { answers, confirmed: true },
        { token },
    );
}

// ── Follow-up overview (any lifecycle state) ────────────────
//
// Mirrors the backend `ADRFollowUpOverviewRead`. It deliberately carries no
// Naranjo score or causality: the patient sees the care team's questions,
// their own answers and the request's status only.

export type ADRFollowUpStatus = "pending" | "answered" | "cancelled";

interface ADRFollowUpResponseApiItem {
    question: PatientADRQuestion;
    answer: PatientADRAnswer;
    evidence?: string | null;
}

interface ADRFollowUpRequestApiRecord {
    id: string;
    adr_assessment_id: string;
    status: ADRFollowUpStatus;
    symptom: string;
    suspect_medication_name: string;
    requested_information: PatientADRQuestion[];
    patient_message: string;
    created_at: string;
    responded_at: string | null;
    closed_at: string | null;
    responses: ADRFollowUpResponseApiItem[];
    replacement_request_id: string | null;
}

interface ADRFollowUpOverviewApiRecord {
    selected: ADRFollowUpRequestApiRecord | null;
    pending: ADRFollowUpRequestApiRecord[];
    recent: ADRFollowUpRequestApiRecord[];
}

export interface ADRFollowUpResponseItem {
    question: PatientADRQuestion;
    answer: PatientADRAnswer;
    evidence?: string;
}

export interface ADRFollowUpRequest {
    id: string;
    assessmentId: string;
    status: ADRFollowUpStatus;
    symptom: string;
    suspectMedicationName: string;
    requestedInformation: PatientADRQuestion[];
    patientMessage: string;
    createdAt: string;
    respondedAt: string | null;
    closedAt: string | null;
    responses: ADRFollowUpResponseItem[];
    replacementRequestId: string | null;
}

export interface ADRFollowUpOverview {
    selected: ADRFollowUpRequest | null;
    pending: ADRFollowUpRequest[];
    recent: ADRFollowUpRequest[];
}

/** Select one request by ID, the newest request for an assessment, or neither. */
export type ADRFollowUpSelector =
    | { requestId: string; assessmentId?: never }
    | { assessmentId: string; requestId?: never }
    | { requestId?: never; assessmentId?: never };

function mapFollowUpResponse(item: ADRFollowUpResponseApiItem): ADRFollowUpResponseItem {
    const mapped: ADRFollowUpResponseItem = { question: item.question, answer: item.answer };
    if (typeof item.evidence === "string") {
        mapped.evidence = item.evidence;
    }
    return mapped;
}

function mapFollowUpRequest(record: ADRFollowUpRequestApiRecord): ADRFollowUpRequest {
    return {
        id: record.id,
        assessmentId: record.adr_assessment_id,
        status: record.status,
        symptom: record.symptom,
        suspectMedicationName: record.suspect_medication_name,
        requestedInformation: record.requested_information ?? [],
        patientMessage: record.patient_message,
        createdAt: record.created_at,
        respondedAt: record.responded_at ?? null,
        closedAt: record.closed_at ?? null,
        responses: (record.responses ?? []).map(mapFollowUpResponse),
        replacementRequestId: record.replacement_request_id ?? null,
    };
}

export async function fetchADRFollowUpOverview(
    token: string,
    selector: ADRFollowUpSelector = {},
): Promise<ADRFollowUpOverview> {
    const query = new URLSearchParams();
    if (selector.requestId) {
        query.set("request_id", selector.requestId);
    } else if (selector.assessmentId) {
        query.set("assessment_id", selector.assessmentId);
    }
    const search = query.toString();
    const record = await api.get<ADRFollowUpOverviewApiRecord>(
        `/api/v1/patients/me/adr-information-requests/overview${search ? `?${search}` : ""}`,
        { token },
    );
    return {
        selected: record.selected ? mapFollowUpRequest(record.selected) : null,
        pending: (record.pending ?? []).map(mapFollowUpRequest),
        recent: (record.recent ?? []).map(mapFollowUpRequest),
    };
}

// ── Error classification ────────────────────────────────────

export type ADRFollowUpErrorClass = "closed" | "notFound" | "unavailable" | "other";

const UNAVAILABLE_STATUSES = new Set([0, 502, 503, 504]);

/** Read `details.error.code` from the backend envelope `{ error: { code, message } }`. */
function readErrorCode(details: unknown): string | null {
    if (typeof details !== "object" || details === null) return null;
    const envelope = (details as { error?: unknown }).error;
    if (typeof envelope !== "object" || envelope === null) return null;
    const code = (envelope as { code?: unknown }).code;
    return typeof code === "string" ? code : null;
}

function isTimeoutError(error: unknown): boolean {
    return (
        typeof error === "object" &&
        error !== null &&
        (error as { name?: unknown }).name === "TimeoutError"
    );
}

/**
 * Map a failed follow-up call to a class the form renders with localized copy.
 * Total: never throws and never exposes the server message.
 */
export function classifyADRFollowUpError(error: unknown): ADRFollowUpErrorClass {
    try {
        if (error instanceof ApiClientError) {
            const code = readErrorCode(error.details);
            if (error.status === 404 || code === "NOT_FOUND") return "notFound";
            if (error.status === 422 && code === "ADR_REQUEST_CLOSED") return "closed";
            if (UNAVAILABLE_STATUSES.has(error.status)) return "unavailable";
            return "other";
        }
        // Network failure after the client's read retry, or a timed-out signal.
        if (error instanceof ApiTransportError || isTimeoutError(error)) return "unavailable";
        return "other";
    } catch {
        return "other";
    }
}
