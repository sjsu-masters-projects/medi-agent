import { ApiClientError, api } from "@/services/api";
import { afterEach, describe, expect, it, vi } from "vitest";

describe("API client error mapping", () => {
    afterEach(() => {
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
});
