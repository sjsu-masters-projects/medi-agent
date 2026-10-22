/**
 * CON-001 clinician API: reviewed care-handoff summaries.
 *
 * Contract: `.agent/specs/con-001-care-handoff-summary.md`. Every call reads the stored
 * clinician session. The sections are assembled by the server from records the author may
 * see; the client only edits the narrative, notes and title.
 */

import { api } from "@/services/api";
import { readStoredSession } from "@/services/auth-session";

export type HandoffPurpose = "colleague" | "care_team" | "transition";

export interface HandoffSource {
    kind: "record" | "rule";
    table: string | null;
    id: string | null;
    label: string;
    href: string | null;
}

export interface HandoffItem { id: string; text: string; detail: string | null; source: HandoffSource }

export interface HandoffSection {
    key: string;
    title: string;
    status: "available" | "empty" | "unavailable";
    note: string | null;
    items: HandoffItem[];
}

export interface HandoffHeader {
    id: string;
    patient_id: string;
    care_team_id: string;
    author_id: string;
    title: string;
    purpose: HandoffPurpose;
    recipient_label: string | null;
    status: "draft" | "approved";
    current_version: number;
    approved_version: number | null;
    approved_by: string | null;
    approved_at: string | null;
    created_at: string;
    updated_at: string;
}

export interface HandoffEvent {
    event_type: "created" | "edited" | "refreshed" | "approved" | "exported";
    version: number;
    export_format: "print" | "fhir" | null;
    actor_id: string;
    created_at: string;
}

export interface HandoffDetail extends HandoffHeader {
    patient_name: string | null;
    version: {
        version: number;
        sections: HandoffSection[];
        narrative: string | null;
        notes: string | null;
        built_at: string;
        created_by: string;
        created_at: string;
    };
    versions: Array<{ version: number; created_by: string; created_at: string }>;
    events: HandoffEvent[];
}

export interface HandoffExport {
    format: "print" | "fhir";
    summary: HandoffDetail;
    bundle: Record<string, unknown> | null;
}

function token(): string {
    const value = typeof window !== "undefined" ? readStoredSession()?.accessToken : null;
    if (!value) throw new Error("Missing authorization header");
    return value;
}

const root = (patientId: string) => `/api/v1/care-team/clinician/patients/${encodeURIComponent(patientId)}/handoff-summaries`;
const one = (patientId: string, summaryId: string) => `${root(patientId)}/${encodeURIComponent(summaryId)}`;

export function listHandoffSummaries(patientId: string): Promise<HandoffHeader[]> {
    return api.get<HandoffHeader[]>(root(patientId), { token: token() });
}

export function createHandoffSummary(
    patientId: string,
    body: { purpose: HandoffPurpose; recipient_label?: string; title?: string; care_team_id?: string; client_request_id?: string },
): Promise<HandoffHeader> {
    return api.post<HandoffHeader>(root(patientId), body, { token: token() });
}

export function fetchHandoffSummary(patientId: string, summaryId: string, version?: number): Promise<HandoffDetail> {
    const query = version ? `?version=${version}` : "";
    return api.get<HandoffDetail>(`${one(patientId, summaryId)}${query}`, { token: token() });
}

export function saveHandoffSummary(
    patientId: string,
    summaryId: string,
    body: { expected_version: number; narrative: string | null; notes: string | null; title?: string; refresh?: boolean },
): Promise<HandoffDetail> {
    return api.put<HandoffDetail>(one(patientId, summaryId), body, { token: token() });
}

export function approveHandoffSummary(patientId: string, summaryId: string, version: number): Promise<HandoffDetail> {
    return api.post<HandoffDetail>(`${one(patientId, summaryId)}/approve`, { version }, { token: token() });
}

export function exportHandoffSummary(
    patientId: string,
    summaryId: string,
    version: number,
    format: "print" | "fhir",
): Promise<HandoffExport> {
    return api.post<HandoffExport>(`${one(patientId, summaryId)}/export`, { version, format }, { token: token() });
}
