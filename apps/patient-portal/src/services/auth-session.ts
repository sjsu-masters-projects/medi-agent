import { createAuthSessionStorage } from "../../../../packages/shared/src/utils/auth-session";
import {
    PATIENT_SESSION_LIMITS,
    resolveSessionLimits,
} from "../../../../packages/shared/src/utils/session-limits";
import type { PatientAuthSession, PatientAuthUser } from "@/store/slices/auth-slice";

const patientAuthSessionStorage = createAuthSessionStorage<
    "patient",
    PatientAuthUser,
    PatientAuthSession
>({
    // Process env values must be read statically so Next.js can inline them.
    limits: resolveSessionLimits(PATIENT_SESSION_LIMITS, {
        idleMinutes: process.env.NEXT_PUBLIC_PATIENT_SESSION_IDLE_MINUTES,
        maxHours: process.env.NEXT_PUBLIC_PATIENT_SESSION_MAX_HOURS,
    }),
    role: "patient",
    storageKey: "mediagent-patient-auth",
});

export const PATIENT_AUTH_STORAGE_KEY = patientAuthSessionStorage.storageKey;
export const SESSION_LIMITS = patientAuthSessionStorage.limits;
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
} = patientAuthSessionStorage;
