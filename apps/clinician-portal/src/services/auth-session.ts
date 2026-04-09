import { createAuthSessionStorage } from "../../../../packages/shared/src/utils/auth-session";
import type { ClinicianAuthSession, ClinicianAuthUser } from "@/store/slices/auth-slice";

const clinicianAuthSessionStorage = createAuthSessionStorage<
    "clinician",
    ClinicianAuthUser,
    ClinicianAuthSession
>({
    role: "clinician",
    storageKey: "mediagent-clinician-auth",
});

export const CLINICIAN_AUTH_STORAGE_KEY = clinicianAuthSessionStorage.storageKey;
export const {
    clearStoredSession,
    isSessionExpiring,
    readStoredSession,
    restoreStoredSession,
    writeStoredSession,
} = clinicianAuthSessionStorage;
