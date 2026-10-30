import { ApiClientError, api } from "@/services/api";
import { ApiTransportError, READ_ATTEMPT_TIMEOUT_MS, fetchWithReadRecovery, getTransportErrorMessage } from "../../../../packages/shared/src/utils/api-transport";
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

    it.each([401, 403, 404, 500])("does not replay an HTTP %s response", async (status) => {
        const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status, headers: { "Content-Type": "application/json" } }));
        vi.stubGlobal("fetch", fetchMock);
        await expect(api.get("/api/v1/test")).rejects.toMatchObject({ status });
        expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it.each([502, 503, 504])("replays a read once after a gateway %s and returns the recovered result", async (status) => {
        const fetchMock = vi.fn()
            .mockResolvedValueOnce(new Response("", { status }))
            .mockResolvedValueOnce(new Response('{"ok":true}', { headers: { "Content-Type": "application/json" } }));
        vi.stubGlobal("fetch", fetchMock);
        await expect(api.get("/api/v1/test")).resolves.toEqual({ ok: true });
        expect(fetchMock).toHaveBeenCalledTimes(2);
    });

    it("surfaces a persistent gateway error after one replay and never replays a write", async () => {
        const fetchMock = vi.fn().mockImplementation(async () => new Response("{}", { status: 502, headers: { "Content-Type": "application/json" } }));
        vi.stubGlobal("fetch", fetchMock);
        await expect(api.get("/api/v1/test")).rejects.toMatchObject({ status: 502 });
        expect(fetchMock).toHaveBeenCalledTimes(2);
        fetchMock.mockClear();
        await expect(api.post("/api/v1/test")).rejects.toMatchObject({ status: 502 });
        expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    it("times out a hung read, replays it once, then reports a connection error instead of loading forever", async () => {
        vi.useFakeTimers();
        const fetchMock = vi.fn().mockImplementation(
            (_url: string, init: RequestInit) =>
                new Promise((_resolve, reject) => {
                    init.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
                }),
        );
        vi.stubGlobal("fetch", fetchMock);
        const pending = api.get("/api/v1/test");
        const assertion = expect(pending).rejects.toMatchObject({ name: "ApiTransportError", outcomeUnknown: false, retryCount: 1 });
        await vi.advanceTimersByTimeAsync(READ_ATTEMPT_TIMEOUT_MS + 300);
        await vi.advanceTimersByTimeAsync(READ_ATTEMPT_TIMEOUT_MS + 300);
        await assertion;
        expect(fetchMock).toHaveBeenCalledTimes(2);
        expect(vi.getTimerCount()).toBe(0);
    });

    it("recovers when the first read hangs through a cold start but the retry answers", async () => {
        vi.useFakeTimers();
        const fetchMock = vi.fn()
            .mockImplementationOnce(
                (_url: string, init: RequestInit) =>
                    new Promise((_resolve, reject) => {
                        init.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
                    }),
            )
            .mockResolvedValueOnce(new Response('{"ok":true}', { headers: { "Content-Type": "application/json" } }));
        vi.stubGlobal("fetch", fetchMock);
        const pending = api.get("/api/v1/test");
        await vi.advanceTimersByTimeAsync(READ_ATTEMPT_TIMEOUT_MS + 300);
        await expect(pending).resolves.toEqual({ ok: true });
        expect(fetchMock).toHaveBeenCalledTimes(2);
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

    it.each([
        [500, { detail: "psycopg.errors.UndefinedColumn: column x does not exist" }, "MediAgent couldn't complete this right now. Try again in a moment."],
        [500, { detail: [{ loc: ["body", "internal_field"], msg: "psycopg internal failure" }] }, "MediAgent couldn't complete this right now. Try again in a moment."],
        [409, { detail: "Conflict" }, "This action conflicts with the current information. Refresh to check the latest details before trying again."],
        [403, { error: { code: "AUTHORIZATION_ERROR", message: "AUTHORIZATION_ERROR" } }, "You don't have access to do this. Ask a clinic admin if you need it."],
        [404, null, "This item is no longer available. Refresh the page to see the latest."],
        [403, { detail: "Only clinic admins can manage staff" }, "Only clinic admins can manage staff"],
    ])("shows plain words instead of status codes, server internals and framework phrases (%i)", async (status, payload, message) => {
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(payload === null ? "" : JSON.stringify(payload), {
            headers: { "Content-Type": "application/json" }, status,
        })));
        const failure = await api.post("/api/v1/test").catch((error: unknown) => error);
        expect(failure).toBeInstanceOf(ApiClientError);
        expect((failure as ApiClientError).message).toBe(message);
        expect((failure as ApiClientError).message).not.toMatch(/HTTP \d|psycopg/);
        expect((failure as ApiClientError).status).toBe(status);
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
