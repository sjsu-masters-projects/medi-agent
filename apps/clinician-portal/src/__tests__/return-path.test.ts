import { describe, expect, it } from "vitest";
import { buildLoginRedirectUrl, sanitizeReturnPath } from "../../../../packages/shared/src/utils/return-path";

describe("return path helpers", () => {
    it("rejects absolute and protocol-relative URLs", () => {
        expect(sanitizeReturnPath("https://evil.com")).toBe(null);
        expect(sanitizeReturnPath("http://evil.com")).toBe(null);
        expect(sanitizeReturnPath("//evil.com/path")).toBe(null);
    });

    it("rejects protocol-relative URLs", () => {
        expect(sanitizeReturnPath("//evil.com/path")).toBe(null);
    });

    it("accepts relative paths and preserves query", () => {
        expect(sanitizeReturnPath("/dashboard?tab=risk")).toBe("/dashboard?tab=risk");
    });

    it("builds login redirect URL with encoded return_path", () => {
        const url = buildLoginRedirectUrl({
            loginPath: "/login",
            reason: "session_expired",
            returnPath: "/dashboard?tab=risk",
        });

        expect(url).toContain("/login?");
        expect(url).toContain("reason=session_expired");
        expect(url).toContain("return_path=%2Fdashboard%3Ftab%3Drisk");
    });
});
