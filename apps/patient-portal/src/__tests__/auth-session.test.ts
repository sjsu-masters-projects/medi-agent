import {
    PATIENT_AUTH_STORAGE_KEY,
    clearStoredSession,
    isSessionExpiring,
    restoreStoredSession,
    writeStoredSession,
} from "@/services/auth-session";
import type { PatientAuthSession } from "@/store/slices/auth-slice";
import { describe, expect, it, vi } from "vitest";

const session: PatientAuthSession = {
    accessToken: "access-token",
    expiresAt: Math.floor(Date.now() / 1000) + 300,
    refreshToken: "refresh-token",
    user: {
        email: "patient@example.com",
        id: "patient-1",
        role: "patient",
    },
};

describe("patient auth session", () => {
    it("detects expiring sessions", () => {
        expect(isSessionExpiring(Math.floor(Date.now() / 1000) + 30)).toBe(true);
        expect(isSessionExpiring(Math.floor(Date.now() / 1000) + 600)).toBe(false);
    });

    it("refreshes and persists an expiring session", async () => {
        writeStoredSession({ ...session, expiresAt: Math.floor(Date.now() / 1000) + 10 });
        const refreshSession = vi.fn().mockResolvedValue({
            ...session,
            accessToken: "new-access-token",
            expiresAt: Math.floor(Date.now() / 1000) + 900,
        });

        const restored = await restoreStoredSession({ refreshSession });

        expect(refreshSession).toHaveBeenCalledWith("refresh-token");
        expect(restored?.accessToken).toBe("new-access-token");
        expect(window.localStorage.getItem(PATIENT_AUTH_STORAGE_KEY)).toContain("new-access-token");
    });

    it("clears storage when refresh fails", async () => {
        writeStoredSession({ ...session, expiresAt: Math.floor(Date.now() / 1000) + 10 });

        const restored = await restoreStoredSession({
            refreshSession: vi.fn().mockRejectedValue(new Error("refresh failed")),
        });

        expect(restored).toBeNull();
        expect(window.localStorage.getItem(PATIENT_AUTH_STORAGE_KEY)).toBeNull();
    });

    it("clears invalid sessions", () => {
        window.localStorage.setItem(PATIENT_AUTH_STORAGE_KEY, JSON.stringify({ token: "bad" }));
        clearStoredSession();
        expect(window.localStorage.getItem(PATIENT_AUTH_STORAGE_KEY)).toBeNull();
    });
});
