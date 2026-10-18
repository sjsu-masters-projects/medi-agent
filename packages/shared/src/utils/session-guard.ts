import type { SessionLimitReason, SessionLimitStatus, SessionLimits } from "./session-limits";

export interface SessionGuardStorage {
    getLimitStatus: () => SessionLimitStatus | null;
    limits: SessionLimits | null;
    recordActivity: (options?: { force?: boolean }) => "recorded" | "throttled" | "expired";
    signOut: (reason: string) => void;
}

export interface SessionGuardOptions {
    storage: SessionGuardStorage;
    /** Remaining idle time while the warning is due; null when it should be hidden. */
    onWarning?: (remainingMs: number | null) => void;
    /** Called after the shared session was cleared and every tab was told. */
    onSignOut: (reason: SessionLimitReason) => void;
}

const ACTIVITY_EVENTS = ["pointerdown", "pointermove", "keydown", "touchstart", "scroll"] as const;

/**
 * Watches activity and enforces the idle and absolute limits. Framework agnostic:
 * a portal hook starts it while a session exists and stops it afterwards.
 */
export function createSessionGuard({ onSignOut, onWarning, storage }: SessionGuardOptions) {
    let warningActive = false;
    let intervalId: ReturnType<typeof setInterval> | null = null;
    const warningMs = storage.limits?.warningMs ?? 0;

    function check() {
        const status = storage.getLimitStatus();
        if (!status) {
            return;
        }
        if (status.state === "expired") {
            stopWarning();
            storage.signOut(status.reason);
            onSignOut(status.reason);
            return;
        }
        if (warningMs > 0 && status.idleRemainingMs <= warningMs) {
            warningActive = true;
            onWarning?.(status.idleRemainingMs);
        } else {
            stopWarning();
        }
    }

    function stopWarning() {
        if (warningActive) {
            warningActive = false;
            onWarning?.(null);
        }
    }

    function handleActivity() {
        // Once the warning is up, only the explicit button keeps the session alive.
        if (warningActive) {
            return;
        }
        if (storage.recordActivity() === "expired") {
            check();
        }
    }

    function handleReturn() {
        // Check first: coming back after the limit must not quietly extend the session.
        check();
        handleActivity();
    }

    function handleVisibility() {
        if (document.visibilityState === "visible") {
            handleReturn();
        }
    }

    function stay() {
        warningActive = false;
        storage.recordActivity({ force: true });
        onWarning?.(null);
    }

    function start() {
        if (typeof window === "undefined" || intervalId !== null) {
            return stop;
        }
        for (const name of ACTIVITY_EVENTS) {
            window.addEventListener(name, handleActivity, { capture: true, passive: true });
        }
        window.addEventListener("focus", handleReturn);
        document.addEventListener("visibilitychange", handleVisibility);
        check();
        intervalId = setInterval(check, warningMs > 0 ? 1000 : 30 * 1000);
        return stop;
    }

    function stop() {
        if (typeof window === "undefined") {
            return;
        }
        for (const name of ACTIVITY_EVENTS) {
            window.removeEventListener(name, handleActivity, { capture: true });
        }
        window.removeEventListener("focus", handleReturn);
        document.removeEventListener("visibilitychange", handleVisibility);
        if (intervalId !== null) {
            clearInterval(intervalId);
            intervalId = null;
        }
        warningActive = false;
    }

    return { check, start, stay, stop };
}
