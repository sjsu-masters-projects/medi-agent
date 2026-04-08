"use client";

import { useEffect } from "react";
import { Provider } from "react-redux";
import { finishHydration, hydrateSession, type ClinicianAuthUser } from "./slices/auth-slice";
import { store } from "./store";

const CLINICIAN_AUTH_STORAGE_KEY = "mediagent-clinician-auth";

export function StoreProvider({ children }: { children: React.ReactNode }) {
    useEffect(() => {
        try {
            const storedValue = window.localStorage.getItem(CLINICIAN_AUTH_STORAGE_KEY);
            if (!storedValue) {
                store.dispatch(finishHydration());
                return;
            }

            const parsed = JSON.parse(storedValue) as {
                token: string | null;
                user: ClinicianAuthUser;
            };

            if (parsed.user) {
                store.dispatch(hydrateSession(parsed));
                return;
            }
        } catch {
            window.localStorage.removeItem(CLINICIAN_AUTH_STORAGE_KEY);
        }

        store.dispatch(finishHydration());
    }, []);

    return <Provider store={store}>{children}</Provider>;
}
