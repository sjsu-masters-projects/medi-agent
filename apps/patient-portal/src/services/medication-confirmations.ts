import { ApiTransportError } from "../../../../packages/shared/src/utils/api-transport";
import { api, ApiClientError } from "@/services/api";

export type MedicationAnswer = "yes" | "stopped" | "changed" | "unsure";

export interface MedicationQuestion {
  id: string;
  medicationName: string;
  dosage: string | null;
  /** The cadence as recorded; shown as written when no reviewed label exists. */
  frequency: string | null;
  frequencyLabelEn: string | null;
  frequencyLabelEs: string | null;
  status: "open" | "answered" | "expired";
  answer: MedicationAnswer | null;
  answerNote: string | null;
  expiresAt: string;
  clinicianName: string | null;
  specialty: string | null;
  clinicName: string | null;
}

interface MedicationQuestionApiRecord {
  id: string;
  medication_name: string;
  dosage?: string | null;
  frequency?: string | null;
  frequency_label_en?: string | null;
  frequency_label_es?: string | null;
  status: "open" | "answered" | "expired";
  answer?: MedicationAnswer | null;
  answer_note?: string | null;
  expires_at: string;
  clinician_name?: string | null;
  specialty?: string | null;
  clinic_name?: string | null;
}

function mapQuestion(record: MedicationQuestionApiRecord): MedicationQuestion {
  return {
    id: record.id,
    medicationName: record.medication_name,
    dosage: record.dosage ?? null,
    frequency: record.frequency ?? null,
    frequencyLabelEn: record.frequency_label_en ?? null,
    frequencyLabelEs: record.frequency_label_es ?? null,
    status: record.status,
    answer: record.answer ?? null,
    answerNote: record.answer_note ?? null,
    expiresAt: record.expires_at,
    clinicianName: record.clinician_name ?? null,
    specialty: record.specialty ?? null,
    clinicName: record.clinic_name ?? null,
  };
}

export async function fetchMedicationQuestions(token: string): Promise<MedicationQuestion[]> {
  const records = await api.get<MedicationQuestionApiRecord[]>(
    "/api/v1/patients/me/medication-confirmations",
    { token },
  );
  return (Array.isArray(records) ? records : []).map(mapQuestion);
}

export async function answerMedicationQuestion(
  token: string,
  questionId: string,
  answer: MedicationAnswer,
  note?: string,
): Promise<MedicationQuestion> {
  const record = await api.post<MedicationQuestionApiRecord>(
    `/api/v1/patients/me/medication-confirmations/${encodeURIComponent(questionId)}/answer`,
    { answer, note: note?.trim() || undefined },
    { token },
  );
  return mapQuestion(record);
}

export type MedicationAnswerErrorClass = "answered" | "expired" | "notFound" | "unavailable" | "other";

function readErrorCode(details: unknown): string | null {
  if (typeof details !== "object" || details === null) return null;
  const envelope = (details as { error?: unknown }).error;
  if (typeof envelope !== "object" || envelope === null) return null;
  const code = (envelope as { code?: unknown }).code;
  return typeof code === "string" ? code : null;
}

/** Map a failed answer to a class the card renders with localized copy; never throws. */
export function classifyMedicationAnswerError(error: unknown): MedicationAnswerErrorClass {
  try {
    if (error instanceof ApiClientError) {
      const code = readErrorCode(error.details);
      if (error.status === 404) return "notFound";
      if (error.status === 409 || code === "MEDCONFIRM_ALREADY_ANSWERED") return "answered";
      if (code === "MEDCONFIRM_EXPIRED") return "expired";
      if ([0, 502, 503, 504].includes(error.status)) return "unavailable";
      return "other";
    }
    if (error instanceof ApiTransportError) return "unavailable";
    return "other";
  } catch {
    return "other";
  }
}
