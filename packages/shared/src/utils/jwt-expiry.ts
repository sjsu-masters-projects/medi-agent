interface JwtPayloadWithExpiry {
    exp?: unknown;
}

function decodeBase64Url(value: string): string | null {
    const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized.padEnd(
        normalized.length + ((4 - (normalized.length % 4)) % 4),
        "=",
    );

    try {
        if (typeof globalThis.atob === "function") {
            return globalThis.atob(padded);
        }

        if (typeof Buffer !== "undefined") {
            return Buffer.from(padded, "base64").toString("utf8");
        }
    } catch {
        return null;
    }

    return null;
}

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

export function getEffectiveSessionExpiresAt(
    expiresAt: number | null | undefined,
    accessToken: string | null | undefined,
): number | null {
    const tokenExpiresAt = getJwtExpiresAt(accessToken);

    if (typeof expiresAt !== "number") {
        return tokenExpiresAt;
    }

    if (typeof tokenExpiresAt !== "number") {
        return expiresAt;
    }

    return Math.min(expiresAt, tokenExpiresAt);
}
