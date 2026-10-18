import { api } from "@/services/api";
import { writeStoredSession } from "@/services/auth-session";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { redirectToLogin } = vi.hoisted(() => ({ redirectToLogin: vi.fn() }));
vi.mock("@/services/auth-redirect", () => ({ redirectToLogin }));

const user = { email: "user@example.com", id: "u1", role: "clinician" as const };
const json = (body: unknown, status = 200) =>
    new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" }, status });

describe("Clinician API 401 recovery", () => {
    beforeEach(() => window.localStorage.clear());
    afterEach(() => {
        vi.unstubAllGlobals();
        redirectToLogin.mockReset();
    });

    it("adopts a newer stored session and retries once without refreshing or redirecting", async () => {
        writeStoredSession(
            { accessToken: "newer", expiresAt: 9_999_999_999, refreshToken: "r2", user },
            { signIn: true },
        );
        const fetchMock = vi.fn()
            .mockResolvedValueOnce(json({ detail: "expired" }, 401))
            .mockResolvedValueOnce(json({ ok: true }));
        vi.stubGlobal("fetch", fetchMock);

        await expect(api.get("/api/v1/thing", { token: "stale" })).resolves.toEqual({ ok: true });

        expect(fetchMock).toHaveBeenCalledTimes(2);
        expect(fetchMock.mock.calls[1][1].headers.Authorization).toBe("Bearer newer");
        expect(redirectToLogin).not.toHaveBeenCalled();
    });

    it("does one refresh when the stored token is the one that failed, then retries", async () => {
        writeStoredSession(
            { accessToken: "stale", expiresAt: 9_999_999_999, refreshToken: "r1", user },
            { signIn: true },
        );
        const fetchMock = vi.fn()
            .mockResolvedValueOnce(json({ detail: "expired" }, 401))
            .mockResolvedValueOnce(json({
                tokens: { access_token: "fresh", expires_at: 9_999_999_999, refresh_token: "r2" },
                user,
            }))
            .mockResolvedValueOnce(json({ ok: true }));
        vi.stubGlobal("fetch", fetchMock);

        await expect(api.get("/api/v1/thing", { token: "stale" })).resolves.toEqual({ ok: true });

        expect(fetchMock.mock.calls[1][0]).toContain("/api/v1/auth/refresh");
        expect(fetchMock.mock.calls[2][1].headers.Authorization).toBe("Bearer fresh");
        expect(redirectToLogin).not.toHaveBeenCalled();
    });

    it("redirects when recovery fails, and retries only once", async () => {
        writeStoredSession(
            { accessToken: "stale", expiresAt: 9_999_999_999, refreshToken: "r1", user },
            { signIn: true },
        );
        const fetchMock = vi.fn().mockImplementation(async () => json({ detail: "no" }, 401));
        vi.stubGlobal("fetch", fetchMock);

        await expect(api.get("/api/v1/thing", { token: "stale" })).rejects.toMatchObject({ status: 401 });
        await vi.waitFor(() => expect(redirectToLogin).toHaveBeenCalledWith({ reason: "session_expired" }));
        expect(fetchMock).toHaveBeenCalledTimes(2);
    });
});
