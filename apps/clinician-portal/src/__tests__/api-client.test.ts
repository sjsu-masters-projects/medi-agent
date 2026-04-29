import { ApiClientError, api } from "@/services/api";
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
        redirectToLogin.mockReset();
        vi.unstubAllGlobals();
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
