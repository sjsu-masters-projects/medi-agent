import { getEffectiveSessionExpiresAt } from "./jwt-expiry";

export interface SharedAuthUser<Role extends string> {
    email: string;
    id: string;
    role: Role;
}

export interface SharedAuthSession<
    Role extends string,
    User extends SharedAuthUser<Role> = SharedAuthUser<Role>,
> {
    accessToken: string;
    refreshToken: string;
    expiresAt: number;
    user: User;
}

interface LegacyStoredSession<
    Role extends string,
    User extends SharedAuthUser<Role>,
> {
    token?: string | null;
    refreshToken?: string | null;
    expiresAt?: number | null;
    user?: User | null;
}

interface CreateAuthSessionStorageConfig<Role extends string> {
    refreshWindowSeconds?: number;
    role: Role;
    storageKey: string;
}

interface RestoreSessionParams<Session> {
    refreshSession: (refreshToken: string) => Promise<Session>;
}

const DEFAULT_REFRESH_WINDOW_SECONDS = 300;

export function createAuthSessionStorage<
    Role extends string,
    User extends SharedAuthUser<Role>,
    Session extends SharedAuthSession<Role, User>,
>({
    refreshWindowSeconds = DEFAULT_REFRESH_WINDOW_SECONDS,
    role,
    storageKey,
}: CreateAuthSessionStorageConfig<Role>) {
    function normalizeStoredSession(value: string | null): Session | null {
        if (!value) {
            return null;
        }

        try {
            const parsed = JSON.parse(value) as
                | Session
                | LegacyStoredSession<Role, User>;
            const user = parsed.user;

            if (!user || user.role !== role) {
                return null;
            }

            if (
                "accessToken" in parsed &&
                "refreshToken" in parsed &&
                "expiresAt" in parsed
            ) {
                if (
                    !parsed.accessToken ||
                    !parsed.refreshToken ||
                    !parsed.expiresAt
                ) {
                    return null;
                }

                return {
                    accessToken: parsed.accessToken,
                    expiresAt: parsed.expiresAt,
                    refreshToken: parsed.refreshToken,
                    user,
                } as Session;
            }

            if (!parsed.token || !parsed.refreshToken || !parsed.expiresAt) {
                return null;
            }

            return {
                accessToken: parsed.token,
                expiresAt: parsed.expiresAt,
                refreshToken: parsed.refreshToken,
                user,
            } as Session;
        } catch {
            return null;
        }
    }

    function isSessionExpiring(
        expiresAt: number,
        nowSeconds = Math.floor(Date.now() / 1000),
    ) {
        return expiresAt - nowSeconds <= refreshWindowSeconds;
    }

    function readStoredSession() {
        return normalizeStoredSession(window.localStorage.getItem(storageKey));
    }

    function writeStoredSession(session: Session) {
        window.localStorage.setItem(storageKey, JSON.stringify(session));
    }

    function clearStoredSession() {
        window.localStorage.removeItem(storageKey);
    }

    async function restoreStoredSession({
        refreshSession,
    }: RestoreSessionParams<Session>): Promise<Session | null> {
        const storedSession = readStoredSession();

        if (!storedSession) {
            clearStoredSession();
            return null;
        }

        const effectiveExpiresAt = getEffectiveSessionExpiresAt(
            storedSession.expiresAt,
            storedSession.accessToken,
        );

        if (effectiveExpiresAt && !isSessionExpiring(effectiveExpiresAt)) {
            return storedSession;
        }

        try {
            const refreshedSession = await refreshSession(
                storedSession.refreshToken,
            );

            if (refreshedSession.user.role !== role) {
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

    return {
        clearStoredSession,
        isSessionExpiring,
        readStoredSession,
        restoreStoredSession,
        storageKey,
        writeStoredSession,
    };
}
