"use client";

import { useEffect, useMemo, useRef } from "react";
import { useDispatch, useSelector } from "react-redux";
import type { AppDispatch } from "@/store/store";
import type { RootState } from "@/store/store";
import { hydrateSession, logout } from "@/store/slices/auth-slice";
import { refreshSingleFlight } from "@/services/auth-session";
import { refreshClinicianSession } from "@/services/auth-refresh";
import { redirectToLogin } from "@/services/auth-redirect";

const REFRESH_EARLY_WINDOW_SECONDS = 30 * 60;
const REFRESH_CHECK_INTERVAL_MS = 60 * 1000;
// A token issued with a short lifetime is always inside the early window; without a floor
// each refresh re-triggered the next one at once and rebuilt every live connection.
const MIN_REFRESH_GAP_MS = 5 * 60 * 1000;

function shouldRefreshSoon(expiresAt: number, nowSeconds = Math.floor(Date.now() / 1000)) {
    return expiresAt - nowSeconds <= REFRESH_EARLY_WINDOW_SECONDS;
}

export function useAuthSessionRefresh() {
    const dispatch = useDispatch<AppDispatch>();
    const { expiresAt, refreshToken, isAuthenticated, loading } = useSelector(
        (state: RootState) => state.auth,
    );

    const refreshState = useRef({ inFlight: false, lastRefreshAt: 0 });

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

            const expiresInSeconds = currentExpiresAt - Math.floor(Date.now() / 1000);
            if (
                expiresInSeconds > 60 &&
                Date.now() - refreshState.current.lastRefreshAt < MIN_REFRESH_GAP_MS
            ) {
                return;
            }

            refreshState.current.inFlight = true;

            try {
                // One refresh across all tabs: a newer stored session is adopted instead.
                const outcome = await refreshSingleFlight({
                    current: {
                        expiresAt: currentExpiresAt,
                        refreshToken: currentRefreshToken,
                    },
                    refreshSession: refreshClinicianSession,
                });

                if (outcome.status === "ok") {
                    dispatch(hydrateSession(outcome.session));
                } else if (outcome.status === "invalid") {
                    dispatch(logout());
                    redirectToLogin({ reason: "session_expired" });
                }
                // A transient failure keeps the session; the next check tries again.
            } finally {
                refreshState.current.inFlight = false;
                refreshState.current.lastRefreshAt = Date.now();
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
