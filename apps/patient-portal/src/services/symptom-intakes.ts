import { api } from "@/services/api";
import type { SymptomIntake } from "@/types";

const root = "/api/v1/patients/me/symptom-intakes";
export function fetchActiveIntake(token: string, sessionId = "default", signal?: AbortSignal) {
    return api.get<SymptomIntake | null>(`${root}/active?session_id=${encodeURIComponent(sessionId)}`, { token, signal, cache: "no-store" });
}
export function fetchIntake(token: string, id: string, signal?: AbortSignal) {
    return api.get<SymptomIntake>(`${root}/${id}`, { token, signal, cache: "no-store" });
}
export function startIntake(token: string, sourceMessageId: string, sessionId = "default", signal?: AbortSignal) {
    return api.post<SymptomIntake>(root, { source_message_id: sourceMessageId, session_id: sessionId }, { token, signal });
}
export function mutateIntake(token: string, id: string, action: string, payload: unknown, signal?: AbortSignal) {
    return api.post<SymptomIntake>(`${root}/${id}/${action}`, payload, { token, signal });
}
