/**
 * PLAN-002 / CLN-003 G-H clinician API: plans per care team, cross-plan conflicts, review
 * items, unowned plans, the shared clinical summary and document claims.
 *
 * Contract: `docs/features/care-plans-and-today.md#api-contract`.
 * Every function reads the stored clinician session, so a caller never handles a token.
 */

import { api, ApiClientError } from "@/services/api";
import { readStoredSession } from "@/services/auth-session";
import type {
    AdoptPlanRequest,
    ClinicianCareTeamOption,
    ClinicianPlanList,
    CrossPlanConflict,
    CrossPlanResolutionRequest,
    CrossPlanReview,
    DocumentClaimResult,
    PublishCarePlanRequest,
    PublishCarePlanResult,
    RetireItemsRequest,
    ReviewItemList,
    SharedClinicalSummary,
    UnownedPlanActivities,
} from "@/types";

function token(): string {
    const value = typeof window !== "undefined" ? readStoredSession()?.accessToken : null;
    if (!value) {
        throw new Error("Missing authorization header");
    }
    return value;
}

const plansRoot = "/api/v1/care-plans/clinician";

// ── Error helpers ────────────────────────────────────────────────────────────────────────

/** The `error.code` of an API error response, or null. */
export function errorCode(error: unknown): string | null {
    if (!(error instanceof ApiClientError)) return null;
    const payload = error.details as { error?: { code?: unknown } } | null | undefined;
    return typeof payload?.error?.code === "string" ? payload.error.code : null;
}

/** The `error.details` object of an API error response, or null. */
export function errorDetails<T = Record<string, unknown>>(error: unknown): T | null {
    if (!(error instanceof ApiClientError)) return null;
    const payload = error.details as { error?: { details?: unknown } } | null | undefined;
    const details = payload?.error?.details;
    return details && typeof details === "object" ? (details as T) : null;
}

/** The conflicts a 409 CROSS_PLAN_CONFLICT carries, or null for any other error. */
export function crossPlanConflictsFrom(error: unknown): CrossPlanConflict[] | null {
    if (errorCode(error) !== "CROSS_PLAN_CONFLICT") return null;
    const conflicts = errorDetails<{ conflicts?: unknown }>(error)?.conflicts;
    return Array.isArray(conflicts) ? (conflicts as CrossPlanConflict[]) : [];
}

/** A fresh idempotency key: one per publish attempt, reused when the same attempt is retried. */
export function newIdempotencyKey(): string {
    if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
    return `publish-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

// ── Plans of one patient ─────────────────────────────────────────────────────────────────

export function fetchPatientPlans(patientId: string): Promise<ClinicianPlanList> {
    return api.get<ClinicianPlanList>(`${plansRoot}/patients/${encodeURIComponent(patientId)}/plans`, { token: token() });
}

export function fetchCareTeamOptions(patientId: string): Promise<ClinicianCareTeamOption[]> {
    return api.get<ClinicianCareTeamOption[]>(
        `${plansRoot}/patients/${encodeURIComponent(patientId)}/care-team-options`,
        { token: token() },
    );
}

// ── Cross-plan conflicts and publication ─────────────────────────────────────────────────

export function fetchCrossPlanReview(patientId: string, versionId: string): Promise<CrossPlanReview> {
    return api.get<CrossPlanReview>(
        `${plansRoot}/patients/${encodeURIComponent(patientId)}/${encodeURIComponent(versionId)}/cross-plan-review`,
        { token: token() },
    );
}

export function resolveConflict(
    patientId: string,
    versionId: string,
    fingerprint: string,
    body: CrossPlanResolutionRequest,
): Promise<{ fingerprint: string; resolution: string; replayed: boolean }> {
    return api.post(
        `${plansRoot}/patients/${encodeURIComponent(patientId)}/${encodeURIComponent(versionId)}/conflicts/${encodeURIComponent(fingerprint)}/resolution`,
        body,
        { token: token() },
    );
}

export function publishCarePlan(
    patientId: string,
    versionId: string,
    body: PublishCarePlanRequest,
): Promise<PublishCarePlanResult> {
    return api.post<PublishCarePlanResult>(
        `${plansRoot}/patients/${encodeURIComponent(patientId)}/${encodeURIComponent(versionId)}/approve`,
        body,
        { token: token() },
    );
}

// ── Review items, adoption and retirement ────────────────────────────────────────────────

export function fetchReviewItems(status: "open" | "resolved" | "withdrawn" = "open"): Promise<ReviewItemList> {
    return api.get<ReviewItemList>(`${plansRoot}/review-items?status=${status}`, { token: token() });
}

export function replyToReviewItem(itemId: string, note?: string): Promise<{ id: string; status: string; replayed: boolean }> {
    return api.post(`${plansRoot}/review-items/${encodeURIComponent(itemId)}/reply`, note ? { note } : {}, { token: token() });
}

/** The asking clinician closes the other team's reply: accept it, or keep both with a reason. */
export function resolveConflictReply(
    itemId: string, action: "accept" | "keep_both", reason?: string,
): Promise<{ id: string; status: string; replayed: boolean; still_blocking?: boolean }> {
    return api.post(`${plansRoot}/review-items/${encodeURIComponent(itemId)}/resolve`, { action, ...(reason ? { reason } : {}) }, { token: token() });
}

export function fetchUnownedActivities(patientId: string, carePlanId: string): Promise<UnownedPlanActivities> {
    return api.get<UnownedPlanActivities>(
        `${plansRoot}/patients/${encodeURIComponent(patientId)}/plans/${encodeURIComponent(carePlanId)}/activities`,
        { token: token() },
    );
}

export function adoptCarePlan(carePlanId: string, body: AdoptPlanRequest): Promise<unknown> {
    return api.post(`${plansRoot}/plans/${encodeURIComponent(carePlanId)}/adopt`, body, { token: token() });
}

export function retireCarePlanItems(carePlanId: string, body: RetireItemsRequest): Promise<unknown> {
    return api.post(`${plansRoot}/plans/${encodeURIComponent(carePlanId)}/retire-items`, body, { token: token() });
}

// ── Shared clinical core and documents ───────────────────────────────────────────────────

export function takeRecord(record: "adr_assessment" | "medwatch_draft", recordId: string, careTeamId: string): Promise<unknown> {
    return api.post(`${plansRoot}/records/${record}/${encodeURIComponent(recordId)}/take`, { care_team_id: careTeamId }, { token: token() });
}

export function fetchSharedSummary(patientId: string): Promise<SharedClinicalSummary> {
    return api.get<SharedClinicalSummary>(
        `/api/v1/care-team/clinician/patients/${encodeURIComponent(patientId)}/shared-summary`,
        { token: token() },
    );
}

export function claimDocument(documentId: string, careTeamId: string): Promise<DocumentClaimResult> {
    return api.post<DocumentClaimResult>(
        `/api/v1/documents/${encodeURIComponent(documentId)}/claim`,
        { care_team_id: careTeamId },
        { token: token() },
    );
}
