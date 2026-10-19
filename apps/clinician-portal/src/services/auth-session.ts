import { createAuthSessionStorage } from "../../../../packages/shared/src/utils/auth-session";
import {
    CLINICIAN_SESSION_LIMITS,
    resolveSessionLimits,
} from "../../../../packages/shared/src/utils/session-limits";
import type { ClinicianAuthSession, ClinicianAuthUser } from "@/store/slices/auth-slice";

const clinicianAuthSessionStorage = createAuthSessionStorage<
    "clinician",
    ClinicianAuthUser,
    ClinicianAuthSession
>({
    // Process env values must be read statically so Next.js can inline them.
    limits: resolveSessionLimits(CLINICIAN_SESSION_LIMITS, {
        idleMinutes: process.env.NEXT_PUBLIC_CLINICIAN_SESSION_IDLE_MINUTES,
        maxHours: process.env.NEXT_PUBLIC_CLINICIAN_SESSION_MAX_HOURS,
        warningSeconds: process.env.NEXT_PUBLIC_CLINICIAN_SESSION_WARNING_SECONDS,
    }),
    role: "clinician",
    storageKey: "mediagent-clinician-auth",
});

export const CLINICIAN_AUTH_STORAGE_KEY = clinicianAuthSessionStorage.storageKey;
export const SESSION_LIMITS = clinicianAuthSessionStorage.limits;
export const {
    clearStoredSession,
    consumeSignOutReason,
    getLimitStatus,
    isSessionExpiring,
    readStoredSession,
    recordActivity,
    recoverFromUnauthorized,
    refreshSingleFlight,
    restoreStoredSession,
    signOut,
    subscribe,
    writeStoredSession,
} = clinicianAuthSessionStorage;
