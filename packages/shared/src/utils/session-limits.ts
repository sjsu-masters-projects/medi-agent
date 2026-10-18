/**
 * Inactivity and absolute session limits, enforced in the browser by the portals.
 * One module owns the defaults so both portals and the tests agree.
 */

export interface SessionLimits {
    /** Sign out after this long without activity in any tab. */
    idleMs: number;
    /** Sign out this long after the sign-in itself, whatever the activity. */
    absoluteMs: number;
    /** Warn this long before the idle limit. 0 disables the warning. */
    warningMs: number;
}

export type SessionLimitReason = "inactivity" | "session_limit";

const MINUTE = 60 * 1000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

export const CLINICIAN_SESSION_LIMITS: SessionLimits = {
    absoluteMs: 12 * HOUR,
    idleMs: 2 * HOUR,
    warningMs: 2 * MINUTE,
};

export const PATIENT_SESSION_LIMITS: SessionLimits = {
    absoluteMs: 90 * DAY,
    idleMs: 30 * DAY,
    warningMs: 0,
};

/** Optional overrides as raw strings (for example `process.env.NEXT_PUBLIC_*`). */
export interface SessionLimitOverrides {
    idleMinutes?: string | null;
    maxHours?: string | null;
    warningSeconds?: string | null;
}

function positiveNumber(raw: string | null | undefined): number | null {
    if (!raw) {
        return null;
    }
    const value = Number(raw);
    return Number.isFinite(value) && value > 0 ? value : null;
}

export function resolveSessionLimits(
    defaults: SessionLimits,
    overrides: SessionLimitOverrides = {},
): SessionLimits {
    const idle = positiveNumber(overrides.idleMinutes);
    const max = positiveNumber(overrides.maxHours);
    const warning = positiveNumber(overrides.warningSeconds);
    return {
        absoluteMs: max ? max * HOUR : defaults.absoluteMs,
        idleMs: idle ? idle * MINUTE : defaults.idleMs,
        warningMs: warning ? warning * 1000 : defaults.warningMs,
    };
}

export type SessionLimitStatus =
    | { state: "expired"; reason: SessionLimitReason }
    | { state: "ok"; idleRemainingMs: number; absoluteRemainingMs: number };

export function evaluateSessionLimits(params: {
    limits: SessionLimits;
    now: number;
    signedInAt: number;
    lastActivityAt: number;
}): SessionLimitStatus {
    const { lastActivityAt, limits, now, signedInAt } = params;
    const absoluteRemainingMs = signedInAt + limits.absoluteMs - now;
    if (absoluteRemainingMs <= 0) {
        return { reason: "session_limit", state: "expired" };
    }
    const idleRemainingMs = lastActivityAt + limits.idleMs - now;
    if (idleRemainingMs <= 0) {
        return { reason: "inactivity", state: "expired" };
    }
    return { absoluteRemainingMs, idleRemainingMs, state: "ok" };
}
