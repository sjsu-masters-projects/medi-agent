import { describe, expect, it } from "vitest";
import {
    buildLoginRedirectUrl,
    sanitizeLoginPath,
    sanitizeReturnPath,
} from "../../../../packages/shared/src/utils/return-path";

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

    it("rejects traversal and backslash return paths", () => {
        expect(sanitizeReturnPath("/../admin")).toBe(null);
        expect(sanitizeReturnPath("/dashboard/./settings")).toBe(null);
        expect(sanitizeReturnPath("/dashboard\\settings")).toBe(null);
    });

    it("sanitizes login paths before building redirects", () => {
        expect(sanitizeLoginPath("/login")).toBe("/login");
        expect(sanitizeLoginPath("//evil.com/login")).toBe(null);
        expect(sanitizeLoginPath("javascript:alert(1)")).toBe(null);

        const url = buildLoginRedirectUrl({
            loginPath: "//evil.com/login",
            returnPath: "/dashboard",
        });

        expect(url).toBe("/login?return_path=%2Fdashboard");
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
