/**
 * Base API client — wraps fetch with auth headers and error handling.
 */

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

    void import("@/services/auth-redirect").then(({ redirectToLogin }) => {
        redirectToLogin({ reason: "session_expired" });
    });
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

function parseApiErrorMessage(status: number, payload: unknown): string {
    if (!isJsonObject(payload)) {
        return `HTTP ${status}`;
    }

    const nestedError = payload.error;
    if (isJsonObject(nestedError) && typeof nestedError.message === "string") {
        return nestedError.message;
    }

    if (typeof payload.message === "string") {
        return payload.message;
    }

    if (typeof payload.detail === "string") {
        return payload.detail;
    }

    if (Array.isArray(payload.detail)) {
        const messages = extractValidationMessages(payload.detail);
        if (messages.length > 0) {
            return messages.join(" ");
        }
    }

    return `HTTP ${status}`;
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

class ApiClient {
    private baseUrl: string;

    constructor(baseUrl: string) {
        this.baseUrl = baseUrl;
    }

    private async request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
        const { token, headers: customHeaders, ...fetchOptions } = options;

        const headers: Record<string, string> = {
            "Content-Type": "application/json",
            ...((customHeaders as Record<string, string>) || {}),
        };

        if (token) {
            headers["Authorization"] = `Bearer ${token}`;
        }

        const response = await fetch(`${this.baseUrl}${endpoint}`, {
            ...fetchOptions,
            headers,
        });

        if (!response.ok) {
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
