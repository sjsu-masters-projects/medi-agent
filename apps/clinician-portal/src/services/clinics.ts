import { api } from "@/services/api";
import type { ClinicianRole } from "@/types";

/** A clinic the signed-in clinician belongs to, with the role held there. */
export interface ClinicMembershipSummary {
    clinic_code: string;
    clinic_id: string;
    clinic_name: string;
    role: ClinicianRole;
    status: "active" | "suspended";
}

export interface ClinicMembershipsResponse {
    clinics: ClinicMembershipSummary[];
    default_clinic_id: string | null;
}

export interface JoinClinicResponse {
    clinic_code: string;
    clinic_id: string;
    clinic_name: string;
    clinic_status: "active" | "suspended";
    role: ClinicianRole;
    status: "joined" | "already_member";
}

export function fetchMyClinics(token: string): Promise<ClinicMembershipsResponse> {
    return api.get<ClinicMembershipsResponse>("/api/v1/clinicians/me/clinics", { token });
}

/** Add a clinic to the signed-in account with an open clinic code (Provider or Nurse only). */
export function joinClinicByCode(
    token: string,
    clinicCode: string,
    role: "provider" | "nurse",
): Promise<JoinClinicResponse> {
    return api.post<JoinClinicResponse>(
        "/api/v1/clinicians/me/clinics",
        { clinic_code: clinicCode, role },
        { token },
    );
}

export interface DefaultClinicResponse {
    clinic_id: string;
    default_clinic_id: string;
    role: ClinicianRole;
}

export interface LeaveClinicResponse {
    clinic_id: string;
    default_clinic_id: string | null;
    links_ended: number;
    status: "left";
}

export interface RenameClinicResponse {
    clinic_id: string;
    clinic_name: string;
}

/** Make a clinic the preselected one. Ends no membership. */
export function setDefaultClinic(token: string, clinicId: string): Promise<DefaultClinicResponse> {
    return api.put<DefaultClinicResponse>(
        "/api/v1/clinicians/me/default-clinic",
        { clinic_id: clinicId },
        { token },
    );
}

/** Leave a clinic. The caller's own patient links and unused invite codes there end with it. */
export function leaveClinic(token: string, clinicId: string): Promise<LeaveClinicResponse> {
    return api.post<LeaveClinicResponse>(
        `/api/v1/clinicians/me/clinics/${encodeURIComponent(clinicId)}/leave`,
        {},
        { token },
    );
}

/** An admin edits the display name of their clinic. */
export function renameClinic(
    token: string,
    clinicId: string,
    displayName: string,
): Promise<RenameClinicResponse> {
    return api.put<RenameClinicResponse>(
        `/api/v1/clinicians/me/clinics/${encodeURIComponent(clinicId)}`,
        { display_name: displayName },
        { token },
    );
}

/** The clinic of the signed-in clinician's care-team link, on a list item. */
export interface ClinicTag {
    clinic_id?: string | null;
    clinic_name?: string | null;
}

/** The stable error code from the API envelope, if the error is an API error. */
export function apiErrorCode(error: unknown): string | null {
    // Duck-typed on the API error's `details`, so this does not depend on the error class.
    if (typeof error !== "object" || error === null || !("details" in error)) {
        return null;
    }
    const code = (error.details as { error?: { code?: unknown } } | null)?.error?.code;
    return typeof code === "string" ? code : null;
}

/** True when a clinic-scoped action needs the clinician to choose one of several clinics. */
export function isClinicRequiredError(error: unknown): boolean {
    return apiErrorCode(error) === "CLINIC_REQUIRED";
}

/** Append the chosen clinic to a clinic-scoped request path. */
export function withClinic(path: string, clinicId: string | null): string {
    if (!clinicId) {
        return path;
    }
    return `${path}${path.includes("?") ? "&" : "?"}clinic_id=${encodeURIComponent(clinicId)}`;
}

const CLINIC_ERROR_COPY: Record<string, string> = {
    ACCOUNT_EXISTS: "This email already has a MediAgent account. Sign in to add this clinic to it.",
    CLINIC_CODE_INACTIVE: "That clinic code is no longer active. Ask the clinic for a current code.",
    CLINIC_CODE_INVALID: "We could not find that clinic code. Check it and try again.",
    CLINIC_NAME_TAKEN: "Another clinic already uses that name.",
    CLINIC_REQUIRED: "Choose which clinic this applies to.",
    INVALID_NAME: "Enter a clinic name of 2 to 120 characters.",
    LAST_CLINIC: "This is your only clinic, so you cannot leave it.",
    SOLE_ADMIN: "You are the only admin here. Make someone else an admin before you leave.",
    INVALID_ROLE: "Choose Provider or Nurse / MA. Clinic admin access comes only from an invitation.",
    MEMBERSHIP_INACTIVE: "Your access to this clinic was ended. Ask that clinic's admin to invite you again.",
    MFA_CODE_REQUIRED: "Enter the 6-digit code from your authenticator app.",
    NO_ACTIVE_CLINIC: "Your account is not active at any clinic. Ask a clinic admin to invite you.",
    SIGN_IN_TO_ACCEPT: "Sign in first, then open the invitation link again.",
};

/** Plain-language copy for the clinic-related error codes; the server message otherwise. */
export function clinicErrorMessage(error: unknown, fallback: string): string {
    const code = apiErrorCode(error);
    if (code && CLINIC_ERROR_COPY[code]) {
        return CLINIC_ERROR_COPY[code];
    }
    if (error instanceof Error && error.message) {
        return error.message;
    }
    return fallback;
}
