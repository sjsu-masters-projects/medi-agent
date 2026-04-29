"use client";

import { useEffect, useMemo, useRef } from "react";
import { useDispatch, useSelector } from "react-redux";
import type { AppDispatch } from "@/store/store";
import type { RootState } from "@/store/store";
import { hydrateSession, logout } from "@/store/slices/auth-slice";
import { writeStoredSession } from "@/services/auth-session";
import { refreshClinicianSession } from "@/services/auth-refresh";
import { redirectToLogin } from "@/services/auth-redirect";

const REFRESH_EARLY_WINDOW_SECONDS = 30 * 60;
const REFRESH_CHECK_INTERVAL_MS = 60 * 1000;

function shouldRefreshSoon(expiresAt: number, nowSeconds = Math.floor(Date.now() / 1000)) {
    return expiresAt - nowSeconds <= REFRESH_EARLY_WINDOW_SECONDS;
}

export function useAuthSessionRefresh() {
    const dispatch = useDispatch<AppDispatch>();
    const { expiresAt, refreshToken, isAuthenticated, loading } = useSelector(
        (state: RootState) => state.auth,
    );

    const refreshState = useRef({ inFlight: false });

    const refreshContext = useMemo(
        () => ({ expiresAt, refreshToken, isAuthenticated, loading }),
        [expiresAt, refreshToken, isAuthenticated, loading],
    );

    useEffect(() => {
        if (loading) {
            return;
        }

        let cancelled = false;

        async function maybeRefresh() {
            if (cancelled) {
                return;
            }

            if (!refreshContext.isAuthenticated) {
                return;
            }

            const currentRefreshToken = refreshContext.refreshToken;
            const currentExpiresAt = refreshContext.expiresAt;

            if (!currentRefreshToken || !currentExpiresAt) {
                return;
            }

            if (!shouldRefreshSoon(currentExpiresAt)) {
                return;
            }

            if (refreshState.current.inFlight) {
                return;
            }

            refreshState.current.inFlight = true;

            try {
                const session = await refreshClinicianSession(currentRefreshToken);
                writeStoredSession(session);
                dispatch(hydrateSession(session));
            } catch {
                dispatch(logout());
                redirectToLogin({ reason: "session_expired" });
            } finally {
                refreshState.current.inFlight = false;
            }
        }

        void maybeRefresh();

        const intervalId = window.setInterval(() => {
            void maybeRefresh();
        }, REFRESH_CHECK_INTERVAL_MS);

        const handleFocus = () => {
            void maybeRefresh();
        };

        window.addEventListener("focus", handleFocus);

        return () => {
            cancelled = true;
            window.clearInterval(intervalId);
            window.removeEventListener("focus", handleFocus);
        };
    }, [dispatch, loading, refreshContext]);
}
