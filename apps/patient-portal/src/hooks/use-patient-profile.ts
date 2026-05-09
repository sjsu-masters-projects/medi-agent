"use client";

import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import { api } from "@/services/api";
import type { RootState } from "@/store/store";

interface PatientProfileResponse {
    id: string;
    email: string;
    first_name: string;
    last_name: string;
    date_of_birth: string;
    preferred_language: string;
    timezone?: string;
}

export interface PatientProfile {
    id: string;
    email: string;
    firstName: string;
    lastName: string;
    dateOfBirth: string;
    preferredLanguage: string;
    timezone: string;
}

function mapProfile(raw: PatientProfileResponse): PatientProfile {
    return {
        dateOfBirth: raw.date_of_birth,
        email: raw.email,
        firstName: raw.first_name,
        id: raw.id,
        lastName: raw.last_name,
        preferredLanguage: raw.preferred_language,
        timezone: raw.timezone ?? "UTC",
    };
}

/**
 * Fetches and caches the logged-in patient's profile for use across pages.
 * Returns null while loading or when unauthenticated.
 */
export function usePatientProfile(): PatientProfile | null {
    const accessToken = useSelector((state: RootState) => state.auth.accessToken);
    const [profile, setProfile] = useState<PatientProfile | null>(null);

    useEffect(() => {
        if (!accessToken) {
            return;
        }

        let isMounted = true;

        api.get<PatientProfileResponse>("/api/v1/patients/me", { token: accessToken })
            .then((raw) => {
                if (isMounted) {
                    setProfile(mapProfile(raw));
                }
            })
            .catch(() => {
                // Silently ignore — today page still works without the greeting name.
            });

        return () => {
            isMounted = false;
        };
    }, [accessToken]);

    return profile;
}
