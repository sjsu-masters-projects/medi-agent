export interface BuildLoginRedirectUrlParams {
    loginPath: string;
    reason?: string;
    returnPath?: string;
}

export function sanitizeReturnPath(raw: string | null | undefined): string | null {
    if (!raw) {
        return null;
    }

    const value = raw.trim();
    if (!value) {
        return null;
    }

    if (!value.startsWith("/")) {
        return null;
    }

    // Prevent protocol-relative URLs like "//evil.com"
    if (value.startsWith("//")) {
        return null;
    }

    // Prevent absolute URLs sneaking in.
    if (value.includes("://")) {
        return null;
    }

    return value;
}

export function buildLoginRedirectUrl({
    loginPath,
    reason,
    returnPath,
}: BuildLoginRedirectUrlParams): string {
    const sanitizedReturnPath = sanitizeReturnPath(returnPath) ?? "/";

    const params = new URLSearchParams();

    if (reason) {
        params.set("reason", reason);
    }

    params.set("return_path", sanitizedReturnPath);

    return `${loginPath}?${params.toString()}`;
}
