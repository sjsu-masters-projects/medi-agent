"use client";

import { useEffect, useMemo, useRef } from "react";
import { useDispatch, useSelector } from "react-redux";
import type { AppDispatch } from "@/store/store";
import type { RootState } from "@/store/store";
import { hydrateSession, logout } from "@/store/slices/auth-slice";
import { writeStoredSession } from "@/services/auth-session";
import { refreshPatientSession } from "@/services/auth-refresh";
import { redirectToLogin } from "@/services/auth-redirect";
import { getEffectiveSessionExpiresAt } from "../../../../packages/shared/src/utils/jwt-expiry";

const REFRESH_EARLY_WINDOW_SECONDS = 30 * 60;
const REFRESH_CHECK_INTERVAL_MS = 60 * 1000;
// A token issued with a short lifetime is always inside the early window; without a floor
// each refresh re-triggered the next one at once and rebuilt every live connection.
const MIN_REFRESH_GAP_MS = 5 * 60 * 1000;

function shouldRefreshSoon(
    expiresAt: number,
    nowSeconds = Math.floor(Date.now() / 1000),
) {
    return expiresAt - nowSeconds <= REFRESH_EARLY_WINDOW_SECONDS;
}

export function useAuthSessionRefresh() {
    const dispatch = useDispatch<AppDispatch>();
    const { accessToken, expiresAt, refreshToken, isAuthenticated, loading } =
        useSelector((state: RootState) => state.auth);

    const refreshState = useRef({ inFlight: false, lastRefreshAt: 0 });

    const refreshContext = useMemo(
        () => ({
            accessToken,
            expiresAt,
            refreshToken,
            isAuthenticated,
            loading,
        }),
        [accessToken, expiresAt, refreshToken, isAuthenticated, loading],
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

            const effectiveExpiresAt = getEffectiveSessionExpiresAt(
                currentExpiresAt,
                refreshContext.accessToken,
            );

            if (effectiveExpiresAt && !shouldRefreshSoon(effectiveExpiresAt)) {
                return;
            }

            if (refreshState.current.inFlight) {
                return;
            }

            const expiresInSeconds = effectiveExpiresAt
                ? effectiveExpiresAt - Math.floor(Date.now() / 1000)
                : 0;
            if (
                expiresInSeconds > 60 &&
                Date.now() - refreshState.current.lastRefreshAt < MIN_REFRESH_GAP_MS
            ) {
                return;
            }

            refreshState.current.inFlight = true;

            try {
                const session =
                    await refreshPatientSession(currentRefreshToken);
                writeStoredSession(session);
                dispatch(hydrateSession(session));
            } catch {
                dispatch(logout());
                redirectToLogin({ reason: "session_expired" });
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
