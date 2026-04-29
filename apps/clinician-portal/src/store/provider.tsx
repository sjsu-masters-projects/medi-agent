"use client";

import { useEffect } from "react";
import { clearStoredSession, restoreStoredSession } from "@/services/auth-session";
import { Provider } from "react-redux";
import { finishHydration, hydrateSession } from "./slices/auth-slice";
import { store } from "./store";
import { refreshClinicianSession } from "@/services/auth-refresh";
import { useAuthSessionRefresh } from "@/hooks/use-auth-session-refresh";

function AuthSessionRefresh() {
    useAuthSessionRefresh();
    return null;
}

export function StoreProvider({ children }: { children: React.ReactNode }) {
    useEffect(() => {
        let isMounted = true;

        async function bootstrapAuth() {
            const session = await restoreStoredSession({
                refreshSession: refreshClinicianSession,
            });

            if (!isMounted) {
                return;
            }

            if (session) {
                store.dispatch(hydrateSession(session));
            } else {
                clearStoredSession();
                store.dispatch(finishHydration());
            }
        }

        void bootstrapAuth();

        return () => {
            isMounted = false;
        };
    }, []);

    return (
        <Provider store={store}>
            <AuthSessionRefresh />
            {children}
        </Provider>
    );
}
