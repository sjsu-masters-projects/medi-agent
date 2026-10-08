import { ApiClientError, api } from "@/services/api";
import { ApiTransportError, fetchWithReadRecovery, getTransportErrorMessage } from "../../../../packages/shared/src/utils/api-transport";
import { waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { redirectToLogin } = vi.hoisted(() => ({
    redirectToLogin: vi.fn(),
}));

vi.mock("@/services/auth-redirect", () => ({
    redirectToLogin,
}));

describe("API client error mapping", () => {
    afterEach(() => {
        vi.useRealTimers();
        redirectToLogin.mockReset();
        vi.unstubAllGlobals();
    });

    it("recovers a failed read once, without changing authentication", async () => {
        const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError("Failed to fetch"))
            .mockResolvedValueOnce(new Response('{"ok":true}', { headers: { "Content-Type": "application/json" } }));
        vi.stubGlobal("fetch", fetchMock);
        await expect(api.get("/api/v1/feed/today", { token: "synthetic-token" })).resolves.toEqual({ ok: true });
        expect(fetchMock).toHaveBeenCalledTimes(2);
        expect(fetchMock.mock.calls[1][1].headers.Authorization).toBe("Bearer synthetic-token");
        expect(redirectToLogin).not.toHaveBeenCalled();
    });

    it("bounds read recovery and never exposes the raw transport error", async () => {
        const fetchMock = vi.fn().mockRejectedValue(new TypeError("private URL and token"));
        vi.stubGlobal("fetch", fetchMock);
        await expect(api.get("/api/v1/feed/today")).rejects.toMatchObject({
            name: "ApiTransportError", outcomeUnknown: false, retryCount: 1,
        });
        expect(fetchMock).toHaveBeenCalledTimes(2);
        expect(redirectToLogin).not.toHaveBeenCalled();
    });

    it.each(["post", "put", "delete"] as const)("does not replay a failed %s", async (method) => {
        const fetchMock = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
        vi.stubGlobal("fetch", fetchMock);
        await expect(api[method]("/api/v1/test")).rejects.toMatchObject({
            name: "ApiTransportError", outcomeUnknown: true, retryCount: 0,
            message: expect.stringContaining("Refresh before trying again"),
        });
        expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it.each([401, 403, 404, 503])("does not replay an HTTP %s response", async (status) => {
        const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status, headers: { "Content-Type": "application/json" } }));
        vi.stubGlobal("fetch", fetchMock);
        await expect(api.get("/api/v1/test")).rejects.toMatchObject({ status });
        expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it("never retries an aborted request", async () => {
        const fetchMock = vi.fn().mockRejectedValue(new DOMException("Aborted", "AbortError"));
        vi.stubGlobal("fetch", fetchMock);
        await expect(api.get("/api/v1/test")).rejects.toMatchObject({ name: "AbortError" });
        expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it("cancels the retry delay when the caller aborts", async () => {
        vi.useFakeTimers();
        const controller = new AbortController();
        const fetchMock = vi.fn().mockRejectedValue(new TypeError("offline"));
        vi.stubGlobal("fetch", fetchMock);
        const pending = api.get("/api/v1/test", { signal: controller.signal });
        const assertion = expect(pending).rejects.toMatchObject({ name: "AbortError" });
        await Promise.resolve();
        controller.abort();
        await assertion;
        expect(fetchMock).toHaveBeenCalledTimes(1);
        expect(vi.getTimerCount()).toBe(0);
    });

    it("uses the same bounded policy for HEAD and localizes safe errors", async () => {
        const fetchMock = vi.fn().mockRejectedValue(new TypeError("offline"));
        vi.stubGlobal("fetch", fetchMock);
        await expect(fetchWithReadRecovery("/api/v1/test", { method: "HEAD" })).rejects.toBeInstanceOf(ApiTransportError);
        expect(fetchMock).toHaveBeenCalledTimes(2);
        expect(getTransportErrorMessage(true, "es-MX")).toContain("Actualiza");
        expect(getTransportErrorMessage(false, "es-MX")).toContain("conexión");
    });

    it("maps FastAPI validation errors to user-friendly field messages", async () => {
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue(
                new Response(
                    JSON.stringify({
                        detail: [
                            {
                                ctx: { min_length: 6 },
                                input: "78008",
                                loc: ["body", "clinic_code"],
                                msg: "String should have at least 6 characters",
                                type: "string_too_short",
                            },
                        ],
                    }),
                    {
                        headers: {
                            "Content-Type": "application/json",
                        },
                        status: 422,
                    },
                ),
            ),
        );

        await expect(api.post("/api/v1/clinics/resolve-code", { clinic_code: "78008" })).rejects.toThrow(
            "Clinic code should have at least 6 characters",
        );
    });

    it("throws ApiClientError with status metadata", async () => {
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue(
                new Response(
                    JSON.stringify({
                        message: "Unauthorized",
                    }),
                    {
                        headers: {
                            "Content-Type": "application/json",
                        },
                        status: 401,
                    },
                ),
            ),
        );

        try {
            await api.post("/api/v1/auth/login", { email: "demo@x.com", password: "bad" });
            throw new Error("Expected request to fail");
        } catch (error) {
            expect(error).toBeInstanceOf(ApiClientError);
            expect((error as ApiClientError).status).toBe(401);
            expect((error as ApiClientError).message).toBe("Unauthorized");
        }
    });

    it("clears stale authenticated sessions by redirecting to login on 401", async () => {
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue(
                new Response(
                    JSON.stringify({
                        error: {
                            code: "AUTHENTICATION_ERROR",
                            message: "Unauthorized",
                        },
                    }),
                    {
                        headers: {
                            "Content-Type": "application/json",
                        },
                        status: 401,
                    },
                ),
            ),
        );

        await expect(api.get("/api/v1/clinicians/me/dashboard", { token: "expired-token" })).rejects.toThrow(
            "Unauthorized",
        );

        await waitFor(() => {
            expect(redirectToLogin).toHaveBeenCalledWith({ reason: "session_expired" });
        });
    });
});
