"use client";

import { useEffect } from "react";
import { Provider } from "react-redux";
import { finishHydration, hydrateSession, type PatientAuthUser } from "./slices/auth-slice";
import { store } from "./store";

const PATIENT_AUTH_STORAGE_KEY = "mediagent-patient-auth";

export function StoreProvider({ children }: { children: React.ReactNode }) {
    useEffect(() => {
        try {
            const storedValue = window.localStorage.getItem(PATIENT_AUTH_STORAGE_KEY);
            if (!storedValue) {
                store.dispatch(finishHydration());
                return;
            }

            const parsed = JSON.parse(storedValue) as {
                token: string | null;
                user: PatientAuthUser;
            };

            if (parsed.user) {
                store.dispatch(hydrateSession(parsed));
                return;
            }
        } catch {
            window.localStorage.removeItem(PATIENT_AUTH_STORAGE_KEY);
        }

        store.dispatch(finishHydration());
    }, []);

    return <Provider store={store}>{children}</Provider>;
}
