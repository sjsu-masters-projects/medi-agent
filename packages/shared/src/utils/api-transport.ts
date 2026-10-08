import type { Locale } from "../types";

export class ApiTransportError extends Error {
    readonly outcomeUnknown: boolean;
    readonly retryCount: number;

    constructor(outcomeUnknown: boolean, retryCount: number) {
        super(getTransportErrorMessage(outcomeUnknown));
        this.name = "ApiTransportError";
        this.outcomeUnknown = outcomeUnknown;
        this.retryCount = retryCount;
    }
}

export function getTransportErrorMessage(outcomeUnknown: boolean, locale: Locale = "en-US"): string {
    if (locale === "es-MX") {
        return outcomeUnknown
            ? "No pudimos confirmar si se guardó el cambio. Actualiza la página antes de volver a intentarlo."
            : "No pudimos conectar. Revisa tu conexión y vuelve a intentarlo.";
    }
    return outcomeUnknown
        ? "Could not confirm whether your change was saved. Refresh before trying again."
        : "Could not connect. Check your connection and try again.";
}

function pauseBeforeRetry(signal?: AbortSignal | null): Promise<void> {
    return new Promise((resolve, reject) => {
        const abort = () => {
            clearTimeout(timer);
            signal?.removeEventListener("abort", abort);
            reject(new DOMException("Request aborted", "AbortError"));
        };
        const timer = setTimeout(() => {
            signal?.removeEventListener("abort", abort);
            resolve();
        }, 100 + Math.floor(Math.random() * 150));
        signal?.addEventListener("abort", abort, { once: true });
        if (signal?.aborted) abort();
    });
}

/** Retry only a failed read transport, never a write or an HTTP error response. */
export async function fetchWithReadRecovery(url: string, options: RequestInit): Promise<Response> {
    const method = (options.method || "GET").toUpperCase();
    const isRead = method === "GET" || method === "HEAD";
    for (let attempt = 0; ; attempt += 1) {
        try {
            return await fetch(url, options);
        } catch (error) {
            if (options.signal?.aborted || !(error instanceof TypeError)) throw error;
            if (isRead && attempt === 0) {
                await pauseBeforeRetry(options.signal);
                continue;
            }
            throw new ApiTransportError(!isRead, attempt);
        }
    }
}
