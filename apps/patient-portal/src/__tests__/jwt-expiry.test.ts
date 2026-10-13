import { afterEach, describe, expect, it, vi } from "vitest";
import {
    decodeBase64Url,
    getEffectiveSessionExpiresAt,
    getJwtExpiresAt,
} from "../../../../packages/shared/src/utils/jwt-expiry";

// Synthetic claims only; the non-ASCII name exercises multi-byte UTF-8 and
// produces "-" and "_" in the base64url encoding.
const claims = { exp: 1_900_000_000, name: "José Núñez ✓", note: "?>?>" };
const encode = (value: unknown) => Buffer.from(JSON.stringify(value)).toString("base64url");
const token = `${encode({ alg: "none", typ: "JWT" })}.${encode(claims)}.`;

describe("JWT expiry helpers", () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it("decodes base64url payloads as UTF-8 in the browser path", () => {
        expect(typeof globalThis.atob).toBe("function");
        const payload = token.split(".")[1];
        expect(payload).toMatch(/[-_]/);
        expect(payload).not.toContain("=");

        expect(JSON.parse(decodeBase64Url(payload) ?? "null")).toEqual(claims);
    });

    it("decodes the same payload identically through Buffer when atob is unavailable", () => {
        const payload = token.split(".")[1];
        const browserDecoded = decodeBase64Url(payload);
        vi.stubGlobal("atob", undefined);

        expect(decodeBase64Url(payload)).toBe(browserDecoded);
    });

    it("reads exp from a token with non-ASCII claims", () => {
        expect(getJwtExpiresAt(token)).toBe(claims.exp);
    });

    it("returns null for missing, malformed or exp-less tokens", () => {
        expect(getJwtExpiresAt(null)).toBeNull();
        expect(getJwtExpiresAt("not-a-jwt")).toBeNull();
        expect(getJwtExpiresAt("a.%%%.b")).toBeNull();
        expect(getJwtExpiresAt(`x.${encode({ sub: "synthetic" })}.`)).toBeNull();
    });

    it("uses the earliest known session expiry", () => {
        expect(getEffectiveSessionExpiresAt(1_800_000_000, token)).toBe(1_800_000_000);
        expect(getEffectiveSessionExpiresAt(2_000_000_000, token)).toBe(claims.exp);
        expect(getEffectiveSessionExpiresAt(undefined, token)).toBe(claims.exp);
        expect(getEffectiveSessionExpiresAt(1_800_000_000, null)).toBe(1_800_000_000);
        expect(getEffectiveSessionExpiresAt(null, null)).toBeNull();
    });
});
