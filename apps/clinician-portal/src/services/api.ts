/**
 * Base API client — wraps fetch with auth headers and error handling.
 */

import { fetchWithReadRecovery } from "../../../../packages/shared/src/utils/api-transport";

const API_BASE_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

interface RequestOptions extends RequestInit {
    token?: string;
}

function handleUnauthorizedRequest(token: string | undefined) {
    if (!token) {
        return;
    }

    // Avoid SSR + avoid redirect loops.
    if (typeof window === "undefined" || window.location.pathname === "/login") {
        return;
    }

    // Lazy import to avoid hard dependency cycles for modules that only use `api`.
    void import("@/services/auth-redirect").then(({ redirectToLogin }) => {
        redirectToLogin({ reason: "session_expired" });
    });
}

/**
 * After a 401: adopt a newer session another tab stored, or do one single-flight
 * refresh. Returns the access token to retry with, or null when the user must sign in.
 * Lazy imports avoid a cycle, because the refresh call itself goes through `api`.
 */
async function recoverAccessToken(failedAccessToken: string): Promise<string | null> {
    if (typeof window === "undefined") {
        return null;
    }
    try {
        const [{ recoverFromUnauthorized }, { refreshClinicianSession }] = await Promise.all([
            import("@/services/auth-session"),
            import("@/services/auth-refresh"),
        ]);
        const session = await recoverFromUnauthorized({
            failedAccessToken,
            refreshSession: refreshClinicianSession,
        });
        if (session) {
            // Other consumers of the Redux copy pick this up through the session event.
            return session.accessToken;
        }
    } catch {
        // Fall through to the sign-in redirect.
    }
    return null;
}

type JsonObject = Record<string, unknown>;

interface ValidationErrorDetail {
    loc?: unknown;
    msg?: unknown;
}

function isJsonObject(value: unknown): value is JsonObject {
    return typeof value === "object" && value !== null;
}

function humanizeFieldName(field: string): string {
    return field
        .split("_")
        .filter(Boolean)
        .map((part, index) => {
            if (index === 0) {
                return part.charAt(0).toUpperCase() + part.slice(1);
            }
            return part;
        })
        .join(" ");
}

function formatValidationMessage(field: string | null, message: string): string {
    if (!field) {
        return message;
    }

    const label = humanizeFieldName(field);
    const lowered = message.toLowerCase();

    if (lowered === "field required") {
        return `${label} is required.`;
    }

    if (lowered.startsWith("string should have at least")) {
        return `${label} should${message.slice("String should".length)}`;
    }

    if (lowered.startsWith("string should have at most")) {
        return `${label} should${message.slice("String should".length)}`;
    }

    return `${label}: ${message}`;
}

function extractValidationMessages(details: unknown[]): string[] {
    const messages: string[] = [];

    for (const detail of details) {
        if (!isJsonObject(detail)) {
            continue;
        }

        const typedDetail = detail as ValidationErrorDetail;
        const msg = typeof typedDetail.msg === "string" ? typedDetail.msg : null;
        if (!msg) {
            continue;
        }

        const field = Array.isArray(typedDetail.loc)
            ? typedDetail.loc
                  .filter((part): part is string => typeof part === "string")
                  .findLast((part) => !["body", "query", "path", "header"].includes(part)) || null
            : null;

        messages.push(formatValidationMessage(field, msg));
    }

    return Array.from(new Set(messages));
}

const STATUS_MESSAGES: Record<number, string> = {
    400: "That request couldn't be completed. Check the details and try again.",
    401: "Your session has ended. Sign in again.",
    403: "You don't have access to do this. Ask a clinic admin if you need it.",
    404: "This item is no longer available. Refresh the page to see the latest.",
    405: "That request couldn't be completed. Check the details and try again.",
    409: "This action conflicts with the current information. Refresh to check the latest details before trying again.",
    413: "That file is too large to upload.",
    415: "That file type isn't supported.",
    422: "Some details are missing or invalid. Check the form and try again.",
    429: "Too many requests. Wait a moment and try again.",
};

/** Plain words for a status when the server gave nothing written for people (UX-007). */
export function friendlyStatusMessage(status: number): string {
    if (status >= 500) return "MediAgent couldn't complete this right now. Try again in a moment.";
    return STATUS_MESSAGES[status] ?? "Something went wrong. Try again.";
}

// Framework defaults and bare codes say what failed, not what to do next.
const FRAMEWORK_PHRASE = /^(?:bad request|forbidden|not found|method not allowed|conflict|payload too large|unsupported media type|unprocessable (?:entity|content)|too many requests)\.?$/i;
const BARE_CODE = /^[A-Z][A-Z0-9_]+$/;

function readableOr(status: number, message: string): string {
    const text = message.trim();
    // 401 text is kept as sent: sign-in screens map it themselves.
    if (status === 401) return text || friendlyStatusMessage(status);
    if (status >= 500 || !text || FRAMEWORK_PHRASE.test(text) || BARE_CODE.test(text)) {
        return friendlyStatusMessage(status);
    }
    return text;
}

function parseApiErrorMessage(status: number, payload: unknown): string {
    // Server failures can contain internal details in any payload shape.
    if (status >= 500) return friendlyStatusMessage(status);
    if (!isJsonObject(payload)) {
        return friendlyStatusMessage(status);
    }

    const nestedError = payload.error;
    if (isJsonObject(nestedError) && typeof nestedError.message === "string") {
        return readableOr(status, nestedError.message);
    }

    if (typeof payload.message === "string") {
        return readableOr(status, payload.message);
    }

    if (typeof payload.detail === "string") {
        return readableOr(status, payload.detail);
    }

    if (Array.isArray(payload.detail)) {
        const messages = extractValidationMessages(payload.detail);
        if (messages.length > 0) {
            return messages.join(" ");
        }
    }

    return friendlyStatusMessage(status);
}

export class ApiClientError extends Error {
    readonly details: unknown;
    readonly status: number;

    constructor(message: string, status: number, details: unknown) {
        super(message);
        this.name = "ApiClientError";
        this.status = status;
        this.details = details;
    }
}

export function isRetryableApiError(error: unknown): error is ApiClientError {
    return error instanceof ApiClientError && [502, 503, 504].includes(error.status);
}

class ApiClient {
    private baseUrl: string;

    constructor(baseUrl: string) {
        this.baseUrl = baseUrl;
    }

    private async request<T>(endpoint: string, options: RequestOptions = {}, retried = false): Promise<T> {
        const { token, headers: customHeaders, ...fetchOptions } = options;

        const headers: Record<string, string> = {
            "Content-Type": "application/json",
            ...((customHeaders as Record<string, string>) || {}),
        };

        if (token) {
            headers["Authorization"] = `Bearer ${token}`;
        }

        const response = await fetchWithReadRecovery(`${this.baseUrl}${endpoint}`, {
            ...fetchOptions,
            headers,
        });

        if (!response.ok) {
            if (response.status === 401 && token && !retried && typeof window !== "undefined" && window.location.pathname !== "/login") {
                const recoveredToken = await recoverAccessToken(token);
                if (recoveredToken && recoveredToken !== token) {
                    return this.request<T>(endpoint, { ...options, token: recoveredToken }, true);
                }
            }
            if (response.status === 401) {
                handleUnauthorizedRequest(token);
            }
            const errorPayload = await response.json().catch(() => null);
            const message = parseApiErrorMessage(response.status, errorPayload);
            throw new ApiClientError(message, response.status, errorPayload);
        }

        if (response.status === 204) {
            return undefined as T;
        }

        const contentType = response.headers.get("content-type") || "";
        if (!contentType.includes("application/json")) {
            return (await response.text()) as T;
        }

        return response.json() as Promise<T>;
    }

    async get<T>(endpoint: string, options?: RequestOptions): Promise<T> {
        return this.request<T>(endpoint, { ...options, method: "GET" });
    }

    async post<T>(endpoint: string, body?: unknown, options?: RequestOptions): Promise<T> {
        return this.request<T>(endpoint, {
            ...options,
            method: "POST",
            body: body ? JSON.stringify(body) : undefined,
        });
    }

    async put<T>(endpoint: string, body?: unknown, options?: RequestOptions): Promise<T> {
        return this.request<T>(endpoint, {
            ...options,
            method: "PUT",
            body: body ? JSON.stringify(body) : undefined,
        });
    }

    async delete<T>(endpoint: string, options?: RequestOptions): Promise<T> {
        return this.request<T>(endpoint, { ...options, method: "DELETE" });
    }
}

export const api = new ApiClient(API_BASE_URL);
