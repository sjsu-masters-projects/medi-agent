import { describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock("@/services/api", () => ({ api }));

import {
    apiErrorCode,
    clinicErrorMessage,
    isClinicRequiredError,
    leaveClinic,
    renameClinic,
    setDefaultClinic,
    withClinic,
} from "@/services/clinics";

function apiError(message: string, code: string) {
    return Object.assign(new Error(message), { details: { error: { code } }, status: 422 });
}

describe("clinic helpers", () => {
    it("adds the clinic to a request path only when one is chosen", () => {
        expect(withClinic("/api/v1/staff/", null)).toBe("/api/v1/staff/");
        expect(withClinic("/api/v1/staff/", "clinic 1")).toBe("/api/v1/staff/?clinic_id=clinic%201");
        expect(withClinic("/api/v1/staff/m1?x=1", "c")).toBe("/api/v1/staff/m1?x=1&clinic_id=c");
    });

    it("reads the error code from the API envelope", () => {
        expect(apiErrorCode(apiError("x", "CLINIC_REQUIRED"))).toBe("CLINIC_REQUIRED");
        expect(apiErrorCode(new Error("plain"))).toBeNull();
        expect(apiErrorCode("text")).toBeNull();
        expect(isClinicRequiredError(apiError("x", "CLINIC_REQUIRED"))).toBe(true);
        expect(isClinicRequiredError(apiError("x", "OTHER"))).toBe(false);
    });

    it.each([
        ["ACCOUNT_EXISTS", /sign in to add this clinic/i],
        ["MEMBERSHIP_INACTIVE", /invite you again/i],
        ["NO_ACTIVE_CLINIC", /not active at any clinic/i],
        ["SIGN_IN_TO_ACCEPT", /sign in first, then open the invitation link again/i],
        ["CLINIC_CODE_INVALID", /could not find that clinic code/i],
    ])("explains %s in plain language", (code, expected) => {
        expect(clinicErrorMessage(apiError("server text", code), "fallback")).toMatch(expected);
    });

    it("falls back to the server message, then the fallback", () => {
        expect(clinicErrorMessage(new Error("Server said no"), "fallback")).toBe("Server said no");
        expect(clinicErrorMessage(null, "fallback")).toBe("fallback");
    });
});

describe("clinic membership actions", () => {
    it("sends make default, leave and rename to the clinic-scoped endpoints", async () => {
        api.put.mockResolvedValue({});
        api.post.mockResolvedValue({});
        await setDefaultClinic("t", "c 1");
        await leaveClinic("t", "c 1");
        await renameClinic("t", "c 1", "New name");
        expect(api.put).toHaveBeenCalledWith("/api/v1/clinicians/me/default-clinic", { clinic_id: "c 1" }, { token: "t" });
        expect(api.post).toHaveBeenCalledWith("/api/v1/clinicians/me/clinics/c%201/leave", {}, { token: "t" });
        expect(api.put).toHaveBeenCalledWith("/api/v1/clinicians/me/clinics/c%201", { display_name: "New name" }, { token: "t" });
    });

    it.each([
        ["LAST_CLINIC", /only clinic/i],
        ["SOLE_ADMIN", /only admin here/i],
        ["CLINIC_NAME_TAKEN", /already uses that name/i],
    ])("explains %s", (code, expected) => {
        expect(clinicErrorMessage(apiError("server text", code), "fallback")).toMatch(expected);
    });
});
