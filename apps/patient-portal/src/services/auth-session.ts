import { createAuthSessionStorage } from "../../../../packages/shared/src/utils/auth-session";
import type { PatientAuthSession, PatientAuthUser } from "@/store/slices/auth-slice";

const patientAuthSessionStorage = createAuthSessionStorage<
    "patient",
    PatientAuthUser,
    PatientAuthSession
>({
    role: "patient",
    storageKey: "mediagent-patient-auth",
});

export const PATIENT_AUTH_STORAGE_KEY = patientAuthSessionStorage.storageKey;
export const {
    clearStoredSession,
    isSessionExpiring,
    readStoredSession,
    restoreStoredSession,
    writeStoredSession,
} = patientAuthSessionStorage;
