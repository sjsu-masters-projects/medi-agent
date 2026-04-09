import type { ClinicianAuthSession, ClinicianAuthUser } from "@/store/slices/auth-slice";

export const CLINICIAN_AUTH_STORAGE_KEY = "mediagent-clinician-auth";
const REFRESH_WINDOW_SECONDS = 60;

interface LegacyStoredSession {
    token?: string | null;
    refreshToken?: string | null;
    expiresAt?: number | null;
    user?: ClinicianAuthUser | null;
}

interface RestoreSessionParams {
    refreshSession: (refreshToken: string) => Promise<ClinicianAuthSession>;
}

function normalizeStoredSession(value: string | null): ClinicianAuthSession | null {
    if (!value) {
        return null;
    }

    try {
        const parsed = JSON.parse(value) as ClinicianAuthSession | LegacyStoredSession;
        const user = parsed.user;
        if (!user || user.role !== "clinician") {
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
    return normalizeStoredSession(window.localStorage.getItem(CLINICIAN_AUTH_STORAGE_KEY));
}

export function writeStoredSession(session: ClinicianAuthSession) {
    window.localStorage.setItem(CLINICIAN_AUTH_STORAGE_KEY, JSON.stringify(session));
}

export function clearStoredSession() {
    window.localStorage.removeItem(CLINICIAN_AUTH_STORAGE_KEY);
}

export async function restoreStoredSession({
    refreshSession,
}: RestoreSessionParams): Promise<ClinicianAuthSession | null> {
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
        if (refreshedSession.user.role !== "clinician") {
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
