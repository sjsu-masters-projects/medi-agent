import { createAuthSessionStorage } from "../../../../packages/shared/src/utils/auth-session";
import { createSessionGuard } from "../../../../packages/shared/src/utils/session-guard";
import {
    CLINICIAN_SESSION_LIMITS,
    PATIENT_SESSION_LIMITS,
    resolveSessionLimits,
} from "../../../../packages/shared/src/utils/session-limits";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

interface User {
    email: string;
    id: string;
    role: "clinician";
}
interface Session {
    accessToken: string;
    expiresAt: number;
    refreshToken: string;
    signedInAt?: number;
    user: User;
}

const KEY = "test-clinician-auth";
const HOUR = 3600 * 1000;
const MINUTE = 60 * 1000;

function jwt(payload: Record<string, unknown>) {
    return `h.${btoa(JSON.stringify(payload))}.s`;
}

function makeSession(overrides: Partial<Session> = {}): Session {
    return {
        accessToken: "access-1",
        expiresAt: Math.floor(Date.now() / 1000) + 60,
        refreshToken: "refresh-1",
        user: { email: "doctor@example.com", id: "c1", role: "clinician" },
        ...overrides,
    };
}

function makeTab(limits = CLINICIAN_SESSION_LIMITS) {
    return createAuthSessionStorage<"clinician", User, Session>({
        limits,
        role: "clinician",
        storageKey: KEY,
    });
}

/** A minimal cross-"tab" lock: callers queue behind each other like navigator.locks. */
function installFakeLocks() {
    let tail: Promise<unknown> = Promise.resolve();
    Object.defineProperty(navigator, "locks", {
        configurable: true,
        value: {
            request: (_name: string, task: () => Promise<unknown>) => {
                const run = tail.then(task, task);
                tail = run.catch(() => undefined);
                return run;
            },
        },
    });
}

function removeLocks() {
    Object.defineProperty(navigator, "locks", { configurable: true, value: undefined });
}

beforeEach(() => {
    window.localStorage.clear();
});

afterEach(() => {
    removeLocks();
    vi.useRealTimers();
    vi.unstubAllGlobals();
});

describe.each([
    ["navigator.locks", installFakeLocks],
    ["localStorage fallback lock", removeLocks],
])("single-flight refresh (%s)", (_name, setUpLock) => {
    beforeEach(() => setUpLock());

    it("refreshes once for two tabs and the second tab adopts the result", async () => {
        const tabA = makeTab();
        const tabB = makeTab();
        const stored = tabA.writeStoredSession(makeSession(), { signIn: true });
        const refreshSession = vi.fn(async () =>
            makeSession({ accessToken: "access-2", expiresAt: stored.expiresAt + 3600, refreshToken: "refresh-2" }),
        );

        const [a, b] = await Promise.all([
            tabA.refreshSingleFlight({ current: stored, refreshSession }),
            tabB.refreshSingleFlight({ current: stored, refreshSession }),
        ]);

        expect(refreshSession).toHaveBeenCalledTimes(1);
        expect(a).toMatchObject({ adopted: false, status: "ok" });
        expect(b).toMatchObject({ adopted: true, status: "ok" });
        expect(tabB.readStoredSession()?.refreshToken).toBe("refresh-2");
    });

    it("does not sign out when a rotation race makes the refresh fail", async () => {
        const tab = makeTab();
        const stored = tab.writeStoredSession(makeSession(), { signIn: true });
        const refreshSession = vi.fn(async () => {
            // Another tab rotated the token first; this refresh is then rejected.
            tab.writeStoredSession(makeSession({ accessToken: "access-2", refreshToken: "refresh-2" }));
            throw Object.assign(new Error("Invalid Refresh Token: Already Used"), { status: 400 });
        });

        const outcome = await tab.refreshSingleFlight({ current: stored, refreshSession });

        expect(outcome).toMatchObject({ adopted: true, status: "ok" });
        expect(tab.readStoredSession()?.refreshToken).toBe("refresh-2");
    });

    it("reports invalid only when the rejection is confirmed after re-reading storage", async () => {
        const tab = makeTab();
        const stored = tab.writeStoredSession(makeSession(), { signIn: true });
        const outcome = await tab.refreshSingleFlight({
            current: stored,
            refreshSession: async () => {
                throw Object.assign(new Error("expired"), { status: 401 });
            },
        });
        expect(outcome).toEqual({ status: "invalid" });
    });

    it("keeps the session on a transient failure", async () => {
        const tab = makeTab();
        const stored = tab.writeStoredSession(makeSession(), { signIn: true });
        const outcome = await tab.refreshSingleFlight({
            current: stored,
            refreshSession: async () => {
                throw Object.assign(new Error("bad gateway"), { status: 503 });
            },
        });
        expect(outcome).toEqual({ status: "transient" });
        expect(tab.readStoredSession()?.refreshToken).toBe("refresh-1");
    });
});

describe("adopting a session", () => {
    it("keeps the MFA (aal2) access token and the original signedInAt", async () => {
        installFakeLocks();
        const tabA = makeTab();
        const tabB = makeTab();
        const stale = tabA.writeStoredSession(makeSession(), { signIn: true });
        const aal2 = jwt({ aal: "aal2", exp: Math.floor(Date.now() / 1000) + 3600 });
        tabB.writeStoredSession(makeSession({ accessToken: aal2, expiresAt: stale.expiresAt + 3600, refreshToken: "refresh-2" }));
        const refreshSession = vi.fn();

        const outcome = await tabA.refreshSingleFlight({ current: stale, refreshSession });

        expect(refreshSession).not.toHaveBeenCalled();
        expect(outcome.status).toBe("ok");
        if (outcome.status === "ok") {
            expect(JSON.parse(atob(outcome.session.accessToken.split(".")[1])).aal).toBe("aal2");
            expect(outcome.session.signedInAt).toBe(stale.signedInAt);
        }
    });

    it("recovers from a 401 by adopting a newer stored session without refreshing", async () => {
        const tab = makeTab();
        tab.writeStoredSession(makeSession({ accessToken: "newer" }), { signIn: true });
        const refreshSession = vi.fn();
        const session = await tab.recoverFromUnauthorized({ failedAccessToken: "stale", refreshSession });
        expect(session?.accessToken).toBe("newer");
        expect(refreshSession).not.toHaveBeenCalled();
    });
});

describe("cross-tab sync", () => {
    it("hydrates from a storage event carrying a new session", () => {
        const tab = makeTab();
        const onSession = vi.fn();
        const stop = tab.subscribe({ onLogout: vi.fn(), onSession });
        const next = makeSession({ accessToken: "access-9" });
        window.dispatchEvent(new StorageEvent("storage", { key: KEY, newValue: JSON.stringify(next) }));
        expect(onSession).toHaveBeenCalledWith(expect.objectContaining({ accessToken: "access-9" }));
        stop();
    });

    it("logs out when the stored session is removed", () => {
        const tab = makeTab();
        const onLogout = vi.fn();
        const stop = tab.subscribe({ onLogout, onSession: vi.fn() });
        window.dispatchEvent(new StorageEvent("storage", { key: KEY, newValue: null }));
        expect(onLogout).toHaveBeenCalledTimes(1);
        stop();
    });

    it("ignores storage events for other keys", () => {
        const tab = makeTab();
        const onLogout = vi.fn();
        const stop = tab.subscribe({ onLogout, onSession: vi.fn() });
        window.dispatchEvent(new StorageEvent("storage", { key: "other", newValue: null }));
        expect(onLogout).not.toHaveBeenCalled();
        stop();
    });

    it("broadcasts an explicit logout with its reason to other tabs", () => {
        const channels = new Set<FakeChannel>();
        class FakeChannel {
            onmessage: ((event: MessageEvent) => void) | null = null;
            constructor(public name: string) {
                channels.add(this);
            }
            postMessage(data: unknown) {
                for (const other of channels) {
                    if (other !== this && other.name === this.name) other.onmessage?.({ data } as MessageEvent);
                }
            }
            close() {
                channels.delete(this);
            }
        }
        vi.stubGlobal("BroadcastChannel", FakeChannel);
        const tabA = makeTab();
        const tabB = makeTab();
        tabA.writeStoredSession(makeSession(), { signIn: true });
        const onLogout = vi.fn();
        const stop = tabB.subscribe({ onLogout, onSession: vi.fn() });

        tabA.signOut("inactivity");

        expect(onLogout).toHaveBeenCalledWith("inactivity");
        expect(tabA.readStoredSession()).toBeNull();
        expect(tabB.consumeSignOutReason()).toBe("inactivity");
        stop();
    });
});

describe("idle and absolute limits", () => {
    beforeEach(() => {
        vi.useFakeTimers();
        vi.setSystemTime(new Date("2026-10-17T09:00:00Z"));
    });

    function startGuard(tab = makeTab()) {
        const onWarning = vi.fn();
        const onSignOut = vi.fn();
        const guard = createSessionGuard({ onSignOut, onWarning, storage: tab });
        return { guard, onSignOut, onWarning, tab };
    }

    it("warns two minutes before the idle limit with a countdown, then signs out", () => {
        const tab = makeTab();
        tab.writeStoredSession(makeSession({ expiresAt: 9_999_999_999 }), { signIn: true });
        const { guard, onSignOut, onWarning } = startGuard(tab);
        guard.start();

        vi.advanceTimersByTime(2 * HOUR - 2 * MINUTE - 1000);
        expect(onWarning).not.toHaveBeenCalled();

        vi.advanceTimersByTime(1000);
        expect(onWarning).toHaveBeenLastCalledWith(2 * MINUTE);
        vi.advanceTimersByTime(30 * 1000);
        expect(onWarning).toHaveBeenLastCalledWith(90 * 1000);

        vi.advanceTimersByTime(90 * 1000);
        expect(onSignOut).toHaveBeenCalledWith("inactivity");
        expect(tab.readStoredSession()).toBeNull();
        guard.stop();
    });

    it("Stay signed in resets the idle clock and hides the warning", () => {
        const tab = makeTab();
        tab.writeStoredSession(makeSession({ expiresAt: 9_999_999_999 }), { signIn: true });
        const { guard, onSignOut, onWarning } = startGuard(tab);
        guard.start();
        vi.advanceTimersByTime(2 * HOUR - MINUTE);
        expect(onWarning).toHaveBeenLastCalledWith(MINUTE);

        guard.stay();
        expect(onWarning).toHaveBeenLastCalledWith(null);
        vi.advanceTimersByTime(HOUR);
        expect(onSignOut).not.toHaveBeenCalled();
        expect(tab.readStoredSession()).not.toBeNull();
        guard.stop();
    });

    it("passive activity extends the idle clock but not once the warning is showing", () => {
        const tab = makeTab();
        tab.writeStoredSession(makeSession({ expiresAt: 9_999_999_999 }), { signIn: true });
        const { guard, onSignOut } = startGuard(tab);
        guard.start();
        vi.advanceTimersByTime(HOUR);
        window.dispatchEvent(new Event("pointermove"));
        vi.advanceTimersByTime(HOUR + 30 * MINUTE);
        expect(onSignOut).not.toHaveBeenCalled();

        vi.advanceTimersByTime(29 * MINUTE); // warning is up
        window.dispatchEvent(new Event("keydown"));
        vi.advanceTimersByTime(3 * MINUTE);
        expect(onSignOut).toHaveBeenCalledWith("inactivity");
        guard.stop();
    });

    it("writes the shared lastActivityAt at most once every 30 seconds", () => {
        const tab = makeTab();
        tab.writeStoredSession(makeSession({ expiresAt: 9_999_999_999 }), { signIn: true });
        const setItem = vi.spyOn(Storage.prototype, "setItem");
        tab.recordActivity({ force: true });
        setItem.mockClear();
        vi.advanceTimersByTime(10 * 1000);
        expect(tab.recordActivity()).toBe("throttled");
        vi.advanceTimersByTime(21 * 1000);
        expect(tab.recordActivity()).toBe("recorded");
        expect(setItem).toHaveBeenCalledTimes(1);
        setItem.mockRestore();
    });

    it("shares lastActivityAt between tabs through storage", () => {
        const tabA = makeTab();
        const tabB = makeTab();
        tabA.writeStoredSession(makeSession({ expiresAt: 9_999_999_999 }), { signIn: true });
        vi.advanceTimersByTime(110 * MINUTE);
        // Tab B alone would be 10 minutes from the idle limit; tab A is active.
        tabA.recordActivity({ force: true });
        vi.advanceTimersByTime(30 * MINUTE);
        expect(tabB.getLimitStatus()).toMatchObject({ idleRemainingMs: 90 * MINUTE, state: "ok" });
    });

    it("ends the session at the 12-hour absolute maximum despite activity", () => {
        const tab = makeTab();
        tab.writeStoredSession(makeSession({ expiresAt: 9_999_999_999 }), { signIn: true });
        const { guard, onSignOut } = startGuard(tab);
        guard.start();
        for (let i = 0; i < 12 * 4; i += 1) {
            window.dispatchEvent(new Event("pointerdown"));
            vi.advanceTimersByTime(15 * MINUTE);
        }
        expect(onSignOut).toHaveBeenCalledWith("session_limit");
        guard.stop();
    });

    it("keeps signedInAt across refresh writes", () => {
        const tab = makeTab();
        const first = tab.writeStoredSession(makeSession(), { signIn: true });
        vi.advanceTimersByTime(HOUR);
        const refreshed = tab.writeStoredSession(makeSession({ accessToken: "access-2" }));
        expect(refreshed.signedInAt).toBe(first.signedInAt);
        const again = tab.writeStoredSession(makeSession(), { signIn: true });
        expect(again.signedInAt).toBeGreaterThan(first.signedInAt as number);
    });

    it("signs out at load when a patient is past 30 idle days or 90 days total", async () => {
        const patient = createAuthSessionStorage<"patient", { email: string; id: string; role: "patient" }, never>({
            limits: PATIENT_SESSION_LIMITS,
            role: "patient",
            storageKey: "test-patient-auth",
        });
        const user = { email: "p@example.com", id: "p1", role: "patient" };
        const base = { accessToken: "a", expiresAt: 9_999_999_999, refreshToken: "r", user };
        const refreshSession = vi.fn();
        const now = Date.now();
        const DAY = 24 * HOUR;

        window.localStorage.setItem("test-patient-auth", JSON.stringify({ ...base, signedInAt: now - 40 * DAY }));
        window.localStorage.setItem("test-patient-auth-activity", String(now - 31 * DAY));
        expect(await patient.restoreStoredSession({ refreshSession })).toBeNull();
        expect(patient.consumeSignOutReason()).toBe("inactivity");

        window.localStorage.setItem("test-patient-auth", JSON.stringify({ ...base, signedInAt: now - 91 * DAY }));
        window.localStorage.setItem("test-patient-auth-activity", String(now - DAY));
        expect(await patient.restoreStoredSession({ refreshSession })).toBeNull();
        expect(patient.consumeSignOutReason()).toBe("session_limit");

        window.localStorage.setItem("test-patient-auth", JSON.stringify({ ...base, signedInAt: now - 40 * DAY }));
        window.localStorage.setItem("test-patient-auth-activity", String(now - 29 * DAY));
        expect(await patient.restoreStoredSession({ refreshSession })).not.toBeNull();
    });
});

describe("session limit configuration", () => {
    it("uses the defaults and ignores invalid overrides", () => {
        expect(resolveSessionLimits(CLINICIAN_SESSION_LIMITS, { idleMinutes: "abc", maxHours: "-1" })).toEqual(
            CLINICIAN_SESSION_LIMITS,
        );
    });

    it("applies valid overrides", () => {
        expect(resolveSessionLimits(CLINICIAN_SESSION_LIMITS, { idleMinutes: "30", maxHours: "8", warningSeconds: "60" })).toEqual({
            absoluteMs: 8 * HOUR,
            idleMs: 30 * MINUTE,
            warningMs: 60 * 1000,
        });
    });
});
