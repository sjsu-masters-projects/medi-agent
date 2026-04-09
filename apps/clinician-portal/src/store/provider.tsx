"use client";

import { useEffect } from "react";
import { api } from "@/services/api";
import { clearStoredSession, restoreStoredSession } from "@/services/auth-session";
import { Provider } from "react-redux";
import { finishHydration, hydrateSession, type ClinicianAuthSession } from "./slices/auth-slice";
import { store } from "./store";

export function StoreProvider({ children }: { children: React.ReactNode }) {
    useEffect(() => {
        let isMounted = true;

        async function bootstrapAuth() {
            const session = await restoreStoredSession({
                refreshSession: async (refreshToken) => {
                    const response = await api.post<{
                        tokens: {
                            access_token: string;
                            refresh_token: string;
                            expires_at: number;
                        };
                        user: {
                            email: string;
                            id: string;
                            role: "patient" | "clinician";
                        };
                    }>("/api/v1/auth/refresh", {
                        expected_role: "clinician",
                        refresh_token: refreshToken,
                    });

                    if (response.user.role !== "clinician") {
                        throw new Error("This session belongs to a patient account.");
                    }

                    return {
                        accessToken: response.tokens.access_token,
                        expiresAt: response.tokens.expires_at,
                        refreshToken: response.tokens.refresh_token,
                        user: {
                            email: response.user.email,
                            id: response.user.id,
                            role: "clinician",
                        },
                    } satisfies ClinicianAuthSession;
                },
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

    return <Provider store={store}>{children}</Provider>;
}
