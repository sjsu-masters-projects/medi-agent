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

/** A cold Cloud Run instance took 18-38 s to answer; a read that long is retried instead of spinning. */
export const READ_ATTEMPT_TIMEOUT_MS = 30_000;
const GATEWAY_STATUSES = new Set([502, 503, 504]);

function pauseBeforeRetry(signal: AbortSignal | null | undefined, baseMs: number): Promise<void> {
    return new Promise((resolve, reject) => {
        const abort = () => {
            clearTimeout(timer);
            signal?.removeEventListener("abort", abort);
            reject(new DOMException("Request aborted", "AbortError"));
        };
        const timer = setTimeout(() => {
            signal?.removeEventListener("abort", abort);
            resolve();
        }, baseMs + Math.floor(Math.random() * 150));
        signal?.addEventListener("abort", abort, { once: true });
        if (signal?.aborted) abort();
    });
}

/** One read attempt bounded by a timeout. A timeout surfaces as a TypeError, like a dropped connection. */
async function fetchReadAttempt(url: string, options: RequestInit): Promise<Response> {
    const timeoutController = new AbortController();
    const caller = options.signal;
    const forwardAbort = () => timeoutController.abort();
    caller?.addEventListener("abort", forwardAbort, { once: true });
    if (caller?.aborted) timeoutController.abort();
    let timedOut = false;
    const timer = setTimeout(() => {
        timedOut = true;
        timeoutController.abort();
    }, READ_ATTEMPT_TIMEOUT_MS);
    try {
        return await fetch(url, { ...options, signal: timeoutController.signal });
    } catch (error) {
        if (timedOut && !caller?.aborted) throw new TypeError("Request timed out");
        throw error;
    } finally {
        clearTimeout(timer);
        caller?.removeEventListener("abort", forwardAbort);
    }
}

/**
 * Retry only a failed read, never a write. A read is replayed once after a transport
 * failure, a 30 s timeout, or a 502/503/504 gateway answer (a browser also reports an
 * un-CORSed 502 as "Failed to fetch"). Other HTTP errors are returned unchanged.
 */
export async function fetchWithReadRecovery(url: string, options: RequestInit): Promise<Response> {
    const method = (options.method || "GET").toUpperCase();
    const isRead = method === "GET" || method === "HEAD";
    for (let attempt = 0; ; attempt += 1) {
        try {
            const response = isRead ? await fetchReadAttempt(url, options) : await fetch(url, options);
            if (isRead && attempt === 0 && GATEWAY_STATUSES.has(response.status)) {
                await pauseBeforeRetry(options.signal, 400);
                continue;
            }
            return response;
        } catch (error) {
            if (options.signal?.aborted && error instanceof TypeError) throw new DOMException("Request aborted", "AbortError");
            if (options.signal?.aborted || !(error instanceof TypeError)) throw error;
            if (isRead && attempt === 0) {
                await pauseBeforeRetry(options.signal, 100);
                continue;
            }
            throw new ApiTransportError(!isRead, attempt);
        }
    }
}
