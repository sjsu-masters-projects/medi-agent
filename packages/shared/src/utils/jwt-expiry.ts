interface JwtPayloadWithExpiry {
    exp?: unknown;
}

/**
 * Decode one base64url JWT segment into a UTF-8 string, or `null` when it is
 * not valid base64.
 *
 * JWT segments use the URL-safe alphabet without padding (RFC 7515), while
 * `atob` and `Buffer`'s `"base64"` decoder expect standard base64. The segment
 * is therefore translated (`-` to `+`, `_` to `/`) and padded with `=` to a
 * multiple of four before decoding. Both runtimes decode the bytes as UTF-8 so
 * non-ASCII claims read the same in the browser and in Node.
 */
export function decodeBase64Url(value: string): string | null {
    const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(
        normalized.length + ((4 - (normalized.length % 4)) % 4),
        "=",
    );

    try {
        if (typeof globalThis.atob === "function") {
            // `atob` returns one character per byte; decode those bytes as UTF-8.
            const binary = globalThis.atob(padded);
            const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
            return new TextDecoder().decode(bytes);
        }

        if (typeof Buffer !== "undefined") {
            return Buffer.from(padded, "base64").toString("utf8");
        }
    } catch {
        return null;
    }

    return null;
}

/**
 * Read the `exp` claim (seconds since the Unix epoch) from a JWT without
 * verifying its signature.
 *
 * Use this only to schedule a client-side refresh; the server remains the
 * authority on whether a token is valid. Returns `null` when the token is
 * missing, malformed, or has no numeric `exp` claim.
 */
export function getJwtExpiresAt(
    token: string | null | undefined,
): number | null {
    if (!token) {
        return null;
    }

    const [, payload] = token.split(".");
    if (!payload) {
        return null;
    }

    const decoded = decodeBase64Url(payload);
    if (!decoded) {
        return null;
    }

    try {
        const parsed = JSON.parse(decoded) as JwtPayloadWithExpiry;
        return typeof parsed.exp === "number" ? parsed.exp : null;
    } catch {
        return null;
    }
}

/**
 * Return the earliest known expiry, in seconds since the Unix epoch, for a
 * session.
 *
 * Combines the session's reported `expiresAt` with the access token's own
 * `exp` claim so a refresh is never scheduled after the token stops working.
 * Either value may be missing; returns `null` only when neither is available.
 */
export function getEffectiveSessionExpiresAt(
    expiresAt: number | null | undefined,
    accessToken: string | null | undefined,
): number | null {
    const tokenExpiresAt = getJwtExpiresAt(accessToken);

    // A missing or zero expiry carries no information; never let it force a refresh loop.
    if (typeof expiresAt !== "number" || expiresAt <= 0) {
        return tokenExpiresAt;
    }

    if (typeof tokenExpiresAt !== "number") {
        return expiresAt;
    }

    return Math.min(expiresAt, tokenExpiresAt);
}
