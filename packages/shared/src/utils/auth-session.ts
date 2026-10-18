import { getEffectiveSessionExpiresAt } from "./jwt-expiry";
import {
    evaluateSessionLimits,
    type SessionLimitReason,
    type SessionLimits,
    type SessionLimitStatus,
} from "./session-limits";

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
    /** Epoch milliseconds of the sign-in itself; kept across refreshes. */
    signedInAt?: number;
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
    limits?: SessionLimits;
    refreshWindowSeconds?: number;
    role: Role;
    storageKey: string;
}

interface RestoreSessionParams<Session> {
    refreshSession: (refreshToken: string) => Promise<Session>;
}

const DEFAULT_REFRESH_WINDOW_SECONDS = 300;
const ACTIVITY_WRITE_INTERVAL_MS = 30 * 1000;
const LOCK_STALE_MS = 15 * 1000;
const LOCK_WAIT_MS = 10 * 1000;
const SIGN_OUT_REASON_TTL_MS = 5 * 60 * 1000;

export type RefreshOutcome<Session> =
    | { status: "ok"; session: Session; adopted: boolean }
    /** The session is gone or the server rejected it: sign out. */
    | { status: "invalid" }
    /** Network or server trouble: keep the session and try again later. */
    | { status: "transient" };

export interface CurrentSessionRef {
    expiresAt: number;
    refreshToken: string;
}

function errorStatus(error: unknown): number | null {
    if (typeof error === "object" && error !== null && "status" in error) {
        const status = (error as { status: unknown }).status;
        return typeof status === "number" ? status : null;
    }
    return null;
}

/** Network failures and server-side trouble do not prove the session is invalid. */
export function isTransientRefreshError(error: unknown): boolean {
    if (error instanceof TypeError) {
        return true;
    }
    if (error instanceof Error && error.name === "AbortError") {
        return true;
    }
    const status = errorStatus(error);
    return status !== null && (status === 0 || status === 408 || status === 425 || status === 429 || status >= 500);
}

function sleep(ms: number) {
    return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

function safeStorage(): Storage | null {
    try {
        return typeof window === "undefined" ? null : window.localStorage;
    } catch {
        return null;
    }
}

export function createAuthSessionStorage<
    Role extends string,
    User extends SharedAuthUser<Role>,
    Session extends SharedAuthSession<Role, User>,
>({
    limits,
    refreshWindowSeconds = DEFAULT_REFRESH_WINDOW_SECONDS,
    role,
    storageKey,
}: CreateAuthSessionStorageConfig<Role>) {
    const activityKey = `${storageKey}-activity`;
    const lockKey = `${storageKey}-refresh-lock`;
    const reasonKey = `${storageKey}-signout`;
    const lockName = `mediagent-${role}-auth-refresh`;
    const channelName = `mediagent-${role}-auth`;
    const changeEvent = `${storageKey}:changed`;
    let lastActivityWriteAt = 0;

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
                    ...parsed,
                    accessToken: parsed.accessToken,
                    expiresAt: parsed.expiresAt,
                    refreshToken: parsed.refreshToken,
                    signedInAt:
                        typeof parsed.signedInAt === "number" ? parsed.signedInAt : undefined,
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
        const storage = safeStorage();
        return storage ? normalizeStoredSession(storage.getItem(storageKey)) : null;
    }

    function readNumber(key: string): number | null {
        const raw = safeStorage()?.getItem(key);
        const value = raw ? Number(raw) : NaN;
        return Number.isFinite(value) ? value : null;
    }

    /** A later expiry or a different refresh token means another tab refreshed or re-signed in. */
    function isNewerSession(candidate: CurrentSessionRef, current: CurrentSessionRef) {
        return (
            candidate.refreshToken !== current.refreshToken ||
            candidate.expiresAt > current.expiresAt
        );
    }

    /**
     * Stores a session. A refresh keeps the original `signedInAt`; pass
     * `signIn: true` for a real sign-in so the absolute limit restarts.
     */
    function writeStoredSession(
        session: Session,
        { signIn = false }: { signIn?: boolean } = {},
    ): Session {
        const storage = safeStorage();
        const now = Date.now();
        const existing = readStoredSession();
        const signedInAt = signIn
            ? now
            : (session.signedInAt ??
              (existing && existing.user.id === session.user.id ? existing.signedInAt : undefined) ??
              now);
        const stamped = { ...session, signedInAt } as Session;
        storage?.setItem(storageKey, JSON.stringify(stamped));
        if (signIn) {
            storage?.setItem(activityKey, String(now));
            storage?.removeItem(reasonKey);
            lastActivityWriteAt = now;
        }
        return stamped;
    }

    function clearStoredSession() {
        const storage = safeStorage();
        storage?.removeItem(storageKey);
        storage?.removeItem(activityKey);
    }

    function openChannel(): BroadcastChannel | null {
        try {
            return typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel(channelName);
        } catch {
            return null;
        }
    }

    /** Records why the session ended, tells every tab, and clears the shared session. */
    function signOut(reason: string) {
        try {
            safeStorage()?.setItem(reasonKey, JSON.stringify({ at: Date.now(), reason }));
        } catch {
            // The reason is a courtesy; signing out must still work.
        }
        const channel = openChannel();
        try {
            channel?.postMessage({ reason, type: "logout" });
        } finally {
            channel?.close();
        }
        clearStoredSession();
    }

    function readSignOutReason(remove: boolean): string | null {
        const storage = safeStorage();
        try {
            const parsed = JSON.parse(storage?.getItem(reasonKey) ?? "null") as {
                at?: number;
                reason?: string;
            } | null;
            if (remove) {
                storage?.removeItem(reasonKey);
            }
            if (parsed?.reason && typeof parsed.at === "number" && Date.now() - parsed.at < SIGN_OUT_REASON_TTL_MS) {
                return parsed.reason;
            }
        } catch {
            // fall through
        }
        return null;
    }

    function emitLocalChange(session: Session) {
        if (typeof window !== "undefined") {
            window.dispatchEvent(new CustomEvent(changeEvent, { detail: session }));
        }
    }

    // ---- Cross-tab single-flight lock -----------------------------------

    async function withFallbackLock<T>(task: () => Promise<T>): Promise<T> {
        const storage = safeStorage();
        if (!storage) {
            return task();
        }
        const owner = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
        const holder = () => {
            try {
                return JSON.parse(storage.getItem(lockKey) ?? "null") as { at: number; owner: string } | null;
            } catch {
                return null;
            }
        };
        const deadline = Date.now() + LOCK_WAIT_MS;
        for (;;) {
            const held = holder();
            if (!held || Date.now() - held.at > LOCK_STALE_MS) {
                storage.setItem(lockKey, JSON.stringify({ at: Date.now(), owner }));
                await sleep(20);
                if (holder()?.owner === owner) {
                    break;
                }
            }
            if (Date.now() > deadline) {
                break;
            }
            await sleep(50);
        }
        try {
            return await task();
        } finally {
            if (holder()?.owner === owner) {
                storage.removeItem(lockKey);
            }
        }
    }

    function withRefreshLock<T>(task: () => Promise<T>): Promise<T> {
        const locks = typeof navigator === "undefined" ? undefined : navigator.locks;
        if (locks?.request) {
            return locks.request(lockName, task) as Promise<T>;
        }
        return withFallbackLock(task);
    }

    /**
     * Refreshes at most once across tabs. Inside the lock the stored session is
     * re-read: if another tab already stored a newer one, it is adopted and no
     * refresh call is made. A failed refresh re-reads storage before it is
     * allowed to mean "sign out".
     */
    function refreshSingleFlight({
        current,
        refreshSession,
    }: {
        current: CurrentSessionRef | null;
        refreshSession: (refreshToken: string) => Promise<Session>;
    }): Promise<RefreshOutcome<Session>> {
        return withRefreshLock(async (): Promise<RefreshOutcome<Session>> => {
            const stored = readStoredSession();
            if (!stored) {
                return { status: "invalid" };
            }
            if (current && isNewerSession(stored, current)) {
                emitLocalChange(stored);
                return { adopted: true, session: stored, status: "ok" };
            }
            try {
                const refreshed = await refreshSession(stored.refreshToken);
                if (refreshed.user.role !== role) {
                    signOut("unauthorized");
                    return { status: "invalid" };
                }
                const written = writeStoredSession(refreshed);
                emitLocalChange(written);
                return { adopted: false, session: written, status: "ok" };
            } catch (error) {
                const latest = readStoredSession();
                if (!latest) {
                    return { status: "invalid" };
                }
                if (isNewerSession(latest, stored)) {
                    emitLocalChange(latest);
                    return { adopted: true, session: latest, status: "ok" };
                }
                return isTransientRefreshError(error) ? { status: "transient" } : { status: "invalid" };
            }
        });
    }

    /**
     * After a 401: adopt a newer stored session if there is one, otherwise do one
     * single-flight refresh. Returns the session to retry with, or null to sign out.
     */
    async function recoverFromUnauthorized({
        failedAccessToken,
        refreshSession,
    }: {
        failedAccessToken: string;
        refreshSession: (refreshToken: string) => Promise<Session>;
    }): Promise<Session | null> {
        const stored = readStoredSession();
        if (!stored) {
            return null;
        }
        if (stored.accessToken !== failedAccessToken) {
            emitLocalChange(stored);
            return stored;
        }
        const outcome = await refreshSingleFlight({ current: stored, refreshSession });
        return outcome.status === "ok" ? outcome.session : null;
    }

    // ---- Limits and activity ----------------------------------------------

    function getLimitStatus(): SessionLimitStatus | null {
        if (!limits) {
            return null;
        }
        const session = readStoredSession();
        if (!session) {
            return null;
        }
        const now = Date.now();
        let signedInAt = session.signedInAt;
        if (typeof signedInAt !== "number") {
            // A session from before the limits existed starts counting now.
            signedInAt = now;
            safeStorage()?.setItem(storageKey, JSON.stringify({ ...session, signedInAt }));
        }
        return evaluateSessionLimits({
            lastActivityAt: readNumber(activityKey) ?? signedInAt,
            limits,
            now,
            signedInAt,
        });
    }

    /** Shared across tabs through storage; at most one write per 30 seconds per tab. */
    function recordActivity({ force = false }: { force?: boolean } = {}): "recorded" | "throttled" | "expired" {
        const now = Date.now();
        if (!force && now - lastActivityWriteAt < ACTIVITY_WRITE_INTERVAL_MS) {
            return "throttled";
        }
        const status = getLimitStatus();
        if (!status) {
            return "throttled";
        }
        if (status.state === "expired") {
            return "expired";
        }
        safeStorage()?.setItem(activityKey, String(now));
        lastActivityWriteAt = now;
        return "recorded";
    }

    async function restoreStoredSession({
        refreshSession,
    }: RestoreSessionParams<Session>): Promise<Session | null> {
        const storedSession = readStoredSession();

        if (!storedSession) {
            clearStoredSession();
            return null;
        }

        const status = getLimitStatus();
        if (status?.state === "expired") {
            signOut(status.reason satisfies SessionLimitReason);
            return null;
        }

        const effectiveExpiresAt = getEffectiveSessionExpiresAt(
            storedSession.expiresAt,
            storedSession.accessToken,
        );

        if (effectiveExpiresAt && !isSessionExpiring(effectiveExpiresAt)) {
            return storedSession;
        }

        const outcome = await refreshSingleFlight({
            current: storedSession,
            refreshSession,
        });

        if (outcome.status === "ok") {
            return outcome.session;
        }
        if (outcome.status === "transient") {
            // Keep the stored session for a later attempt; use it only while the access token is still valid.
            const stillValid =
                effectiveExpiresAt !== null &&
                effectiveExpiresAt !== undefined &&
                effectiveExpiresAt > Math.floor(Date.now() / 1000);
            return stillValid ? storedSession : null;
        }
        clearStoredSession();
        return null;
    }

    // ---- Cross-tab sync ---------------------------------------------------

    function subscribe({
        onLogout,
        onSession,
    }: {
        onLogout: (reason: string | null) => void;
        onSession: (session: Session) => void;
    }): () => void {
        if (typeof window === "undefined") {
            return () => undefined;
        }
        const handleStorage = (event: StorageEvent) => {
            if (event.key === null) {
                onLogout(readSignOutReason(false));
                return;
            }
            if (event.key !== storageKey) {
                return;
            }
            if (event.newValue === null) {
                onLogout(readSignOutReason(false));
                return;
            }
            const session = normalizeStoredSession(event.newValue);
            if (session) {
                onSession(session);
            }
        };
        const handleLocal = (event: Event) => {
            onSession((event as CustomEvent<Session>).detail);
        };
        let channel: BroadcastChannel | null = null;
        try {
            channel = typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel(channelName);
            if (channel) {
                channel.onmessage = (event: MessageEvent) => {
                    const data = event.data as { reason?: string; type?: string } | null;
                    if (data?.type === "logout") {
                        onLogout(data.reason ?? null);
                    }
                };
            }
        } catch {
            channel = null;
        }
        window.addEventListener("storage", handleStorage);
        window.addEventListener(changeEvent, handleLocal);
        return () => {
            window.removeEventListener("storage", handleStorage);
            window.removeEventListener(changeEvent, handleLocal);
            channel?.close();
        };
    }

    return {
        clearStoredSession,
        consumeSignOutReason: () => readSignOutReason(true),
        getLimitStatus,
        isSessionExpiring,
        limits: limits ?? null,
        readStoredSession,
        recordActivity,
        recoverFromUnauthorized,
        refreshSingleFlight,
        restoreStoredSession,
        signOut,
        storageKey,
        subscribe,
        writeStoredSession,
    };
}
