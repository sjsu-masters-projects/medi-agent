import { api, ApiClientError } from "@/services/api";
import type { UploadCareTeamOption } from "@/types";

/** The envelope code of an API error (`{"error": {"code"}}`), or null. */
export function apiErrorCode(error: unknown): string | null {
    if (!(error instanceof ApiClientError)) return null;
    const payload = error.details as { error?: { code?: unknown } } | null | undefined;
    const code = payload?.error?.code;
    return typeof code === "string" ? code : null;
}

/** What the patient picked for an upload: one care team, or "Not sure". */
export type DocumentRoutingChoice = { care_team_id: string } | { not_sure: true };

/**
 * The patient's care teams for the upload picker. Resolves to `null` when the list cannot be
 * read, so the upload falls back to the server's own routing rule instead of being blocked.
 */
export async function fetchUploadCareTeamOptions(token: string): Promise<UploadCareTeamOption[] | null> {
    try {
        const options = await api.get<UploadCareTeamOption[]>("/api/v1/documents/care-team-options", { token });
        return Array.isArray(options) ? options : null;
    } catch {
        return null;
    }
}
