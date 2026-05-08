export interface BuildLoginRedirectUrlParams {
    loginPath: string;
    reason?: string;
    returnPath?: string;
}

function sanitizeRelativePath(raw: string | null | undefined): string | null {
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

    // Prevent any URI scheme, including handlers without "//" such as "javascript:".
    if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(value)) {
        return null;
    }

    if (value.includes("\\")) {
        return null;
    }

    let pathname = value.split(/[?#]/, 1)[0];
    try {
        for (let index = 0; index < 3; index += 1) {
            const decoded = decodeURIComponent(pathname);
            if (decoded === pathname) {
                break;
            }
            pathname = decoded;
        }
    } catch {
        return null;
    }

    const segments = pathname.split("/");
    if (segments.some((segment) => segment === "." || segment === "..")) {
        return null;
    }

    return value;
}

export function sanitizeReturnPath(raw: string | null | undefined): string | null {
    return sanitizeRelativePath(raw);
}

export function sanitizeLoginPath(raw: string | null | undefined): string | null {
    return sanitizeRelativePath(raw);
}

export function buildLoginRedirectUrl({
    loginPath,
    reason,
    returnPath,
}: BuildLoginRedirectUrlParams): string {
    const sanitizedLoginPath = sanitizeLoginPath(loginPath) ?? "/login";
    const sanitizedReturnPath = sanitizeReturnPath(returnPath) ?? "/";

    const params = new URLSearchParams();

    if (reason) {
        params.set("reason", reason);
    }

    params.set("return_path", sanitizedReturnPath);

    return `${sanitizedLoginPath}?${params.toString()}`;
}
