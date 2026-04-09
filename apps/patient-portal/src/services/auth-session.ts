import type { PatientAuthSession, PatientAuthUser } from "@/store/slices/auth-slice";

export const PATIENT_AUTH_STORAGE_KEY = "mediagent-patient-auth";
const REFRESH_WINDOW_SECONDS = 60;

interface LegacyStoredSession {
    token?: string | null;
    refreshToken?: string | null;
    expiresAt?: number | null;
    user?: PatientAuthUser | null;
}

interface RestoreSessionParams {
    refreshSession: (refreshToken: string) => Promise<PatientAuthSession>;
}

function normalizeStoredSession(value: string | null): PatientAuthSession | null {
    if (!value) {
        return null;
    }

    try {
        const parsed = JSON.parse(value) as PatientAuthSession | LegacyStoredSession;
        const user = parsed.user;
        if (!user || user.role !== "patient") {
            return null;
        }

        if ("accessToken" in parsed && "refreshToken" in parsed && "expiresAt" in parsed) {
            if (!parsed.accessToken || !parsed.refreshToken || !parsed.expiresAt) {
                return null;
            }

            return {
                accessToken: parsed.accessToken,
                refreshToken: parsed.refreshToken,
                expiresAt: parsed.expiresAt,
                user,
            };
        }

        if (!parsed.token || !parsed.refreshToken || !parsed.expiresAt) {
            return null;
        }

        return {
            accessToken: parsed.token,
            refreshToken: parsed.refreshToken,
            expiresAt: parsed.expiresAt,
            user,
        };
    } catch {
        return null;
    }
}

export function isSessionExpiring(expiresAt: number, nowSeconds = Math.floor(Date.now() / 1000)) {
    return expiresAt - nowSeconds <= REFRESH_WINDOW_SECONDS;
}

export function readStoredSession() {
    return normalizeStoredSession(window.localStorage.getItem(PATIENT_AUTH_STORAGE_KEY));
}

export function writeStoredSession(session: PatientAuthSession) {
    window.localStorage.setItem(PATIENT_AUTH_STORAGE_KEY, JSON.stringify(session));
}

export function clearStoredSession() {
    window.localStorage.removeItem(PATIENT_AUTH_STORAGE_KEY);
}

export async function restoreStoredSession({
    refreshSession,
}: RestoreSessionParams): Promise<PatientAuthSession | null> {
    const storedSession = readStoredSession();
    if (!storedSession) {
        clearStoredSession();
        return null;
    }

    if (!isSessionExpiring(storedSession.expiresAt)) {
        return storedSession;
    }

    try {
        const refreshedSession = await refreshSession(storedSession.refreshToken);
        if (refreshedSession.user.role !== "patient") {
            clearStoredSession();
            return null;
        }
        writeStoredSession(refreshedSession);
        return refreshedSession;
    } catch {
        clearStoredSession();
        return null;
    }
}
