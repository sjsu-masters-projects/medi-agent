/**
 * Error text that is safe to show a clinician (UX-007).
 *
 * Kept apart from the API client so screens can use it without importing the client,
 * and errors are recognised by name so a mocked client in tests changes nothing here.
 */
const READABLE_ERRORS = new Set(["ApiClientError", "ApiTransportError", "MedWatchRequestError"]);

/**
 * API and transport errors carry plain messages (the client maps status-only and
 * framework errors). Any other thrown value, such as a code bug or a parse error,
 * is replaced by the screen's own fallback.
 */
export function readableError(error: unknown, fallback: string): string {
    if (error instanceof Error && READABLE_ERRORS.has(error.name) && error.message.trim()) {
        return error.message;
    }
    return fallback;
}
