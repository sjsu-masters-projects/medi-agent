import { CLINICIAN_AUTH_STORAGE_KEY, restoreStoredSession, writeStoredSession } from "@/services/auth-session";
import type { ClinicianAuthSession } from "@/store/slices/auth-slice";
import { describe, expect, it, vi } from "vitest";

const session: ClinicianAuthSession = {
    accessToken: "access-token",
    expiresAt: Math.floor(Date.now() / 1000) + 300,
    refreshToken: "refresh-token",
    user: {
        email: "doctor@example.com",
        id: "clinician-1",
        role: "clinician",
    },
};

describe("Clinician auth session", () => {
    it("refreshes expiring clinician sessions", async () => {
        writeStoredSession({ ...session, expiresAt: Math.floor(Date.now() / 1000) + 20 });

        const restored = await restoreStoredSession({
            refreshSession: vi.fn().mockResolvedValue({
                ...session,
                accessToken: "new-access-token",
                expiresAt: Math.floor(Date.now() / 1000) + 900,
            }),
        });

        expect(restored?.accessToken).toBe("new-access-token");
        expect(window.localStorage.getItem(CLINICIAN_AUTH_STORAGE_KEY)).toContain("new-access-token");
    });

    it("clears storage when refresh fails", async () => {
        writeStoredSession({ ...session, expiresAt: Math.floor(Date.now() / 1000) + 20 });

        const restored = await restoreStoredSession({
            refreshSession: vi.fn().mockRejectedValue(new Error("refresh failed")),
        });

        expect(restored).toBeNull();
        expect(window.localStorage.getItem(CLINICIAN_AUTH_STORAGE_KEY)).toBeNull();
    });
});
