import { api } from "@/services/api";
import type { Locale } from "@/types";

export type SymptomReportStatus = "reported" | "shared" | "reviewed";
export type SymptomEventKind =
  | "reported"
  | "shared_with_care_team"
  | "flagged_urgent"
  | "reviewed";

export interface SymptomReportEvent {
  kind: SymptomEventKind;
  at: string;
  actor_name: string | null;
}

export interface SymptomReportAnswer {
  question_id: string;
  label: string;
  state: "answered" | "unknown" | "declined";
  display: string;
  wording: string | null;
}

export interface SymptomReportSummary {
  id: string;
  symptom: string;
  severity: number | null;
  onset: string | null;
  duration: string | null;
  confirmed_at: string;
  locale: Locale;
  status: SymptomReportStatus;
  events: SymptomReportEvent[];
}

export interface SymptomReportDetail extends SymptomReportSummary {
  body_area: string | null;
  answers: SymptomReportAnswer[];
}

export interface SymptomReportList {
  items: SymptomReportSummary[];
  has_more: boolean;
}

export function fetchSymptomHistory(token: string, signal?: AbortSignal) {
  return api.get<SymptomReportList>("/api/v1/patients/me/symptom-history", {
    token,
    signal,
    cache: "no-store",
  });
}

export function fetchSymptomReport(token: string, id: string, signal?: AbortSignal) {
  return api.get<SymptomReportDetail>(
    `/api/v1/patients/me/symptom-history/${encodeURIComponent(id)}`,
    { token, signal, cache: "no-store" },
  );
}
