"use client";

import { useEffect, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { createSessionGuard } from "../../../../packages/shared/src/utils/session-guard";
import { hydrateSession, logout } from "@/store/slices/auth-slice";
import type { AppDispatch, RootState } from "@/store/store";
import * as authSession from "@/services/auth-session";
import { redirectToLogin, type AuthRedirectReason } from "@/services/auth-redirect";

/**
 * Keeps every tab in step with the shared session: a newer session stored by
 * another tab is adopted, a sign-out anywhere signs out everywhere, and the
 * inactivity and absolute limits are enforced and exposes the inactivity warning countdown.
 */
export function useSessionLifecycle() {
    const [warningMs, setWarningMs] = useState<number | null>(null);
    const stayRef = useRef<() => void>(() => undefined);
    const dispatch = useDispatch<AppDispatch>();
    const { isAuthenticated, loading } = useSelector((state: RootState) => state.auth);

    useEffect(() => {
        if (loading) {
            return;
        }
        return authSession.subscribe({
            onLogout: (reason) => {
                if (!isAuthenticated) {
                    return;
                }
                dispatch(logout());
                redirectToLogin({ reason: (reason as AuthRedirectReason | null) ?? "logged_out" });
            },
            onSession: (session) => {
                if (isAuthenticated) {
                    dispatch(hydrateSession(session));
                }
            },
        });
    }, [dispatch, isAuthenticated, loading]);

    useEffect(() => {
        if (loading || !isAuthenticated) {
            return;
        }
        const guard = createSessionGuard({
            onSignOut: (reason) => {
                setWarningMs(null);
                dispatch(logout());
                redirectToLogin({ reason });
            },
            onWarning: setWarningMs,
            storage: {
                getLimitStatus: authSession.getLimitStatus,
                limits: authSession.SESSION_LIMITS,
                recordActivity: authSession.recordActivity,
                signOut: authSession.signOut,
            },
        });
        stayRef.current = guard.stay;
        const stop = guard.start();
        return () => {
            stop();
            stayRef.current = () => undefined;
            setWarningMs(null);
        };
    }, [dispatch, isAuthenticated, loading]);

    return { stay: () => stayRef.current(), warningMs };
}
