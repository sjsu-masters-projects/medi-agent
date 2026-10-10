import { afterEach, describe, expect, it, vi } from "vitest";
import { redirectToLogin } from "@/services/auth-redirect";

vi.mock("@/services/auth-session", () => ({ clearStoredSession: vi.fn() }));

describe("expired-session document destination", () => {
    afterEach(() => vi.unstubAllGlobals());

    it("retains Documents and its exact source anchor", () => {
        const assign = vi.fn();
        vi.stubGlobal("window", {
            location: {
                pathname: "/patients/morgan",
                search: "?tab=documents",
                hash: "#document-source-1",
                assign,
            },
        });
        redirectToLogin({ reason: "session_expired" });
        const target = new URL(assign.mock.calls[0][0], "https://clinician.example");
        expect(target.searchParams.get("return_path")).toBe(
            "/patients/morgan?tab=documents#document-source-1",
        );
        expect(target.searchParams.get("reason")).toBe("session_expired");
    });

    it("still rejects an external override", () => {
        const assign = vi.fn();
        vi.stubGlobal("window", { location: { pathname: "/patients", assign } });
        redirectToLogin({ returnPath: "//external.example#document-source-1" });
        const target = new URL(assign.mock.calls[0][0], "https://clinician.example");
        expect(target.searchParams.get("return_path")).toBe("/");
    });
});
