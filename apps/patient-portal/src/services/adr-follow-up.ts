import { api } from "@/services/api";

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
