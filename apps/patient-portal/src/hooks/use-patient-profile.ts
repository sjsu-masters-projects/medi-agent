"use client";

import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import { api } from "@/services/api";
import type { RootState } from "@/store/store";
import { normalizeLocale, type Locale } from "@/types";

interface PatientProfileResponse {
    date_of_birth: string;
    email: string;
    first_name: string;
    id: string;
    last_name: string;
    preferred_language: Locale;
    timezone?: string;
}

export interface PatientProfile {
    dateOfBirth: string;
    email: string;
    firstName: string;
    id: string;
    lastName: string;
    preferredLanguage: Locale;
    timezone: string;
}

function mapProfile(raw: PatientProfileResponse): PatientProfile {
    return {
        dateOfBirth: raw.date_of_birth,
        email: raw.email,
        firstName: raw.first_name,
        id: raw.id,
        lastName: raw.last_name,
        preferredLanguage: normalizeLocale(raw.preferred_language),
        timezone: raw.timezone ?? "UTC",
    };
}

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
                // The Today page still works with the generic greeting.
            });

        return () => {
            isMounted = false;
        };
    }, [accessToken]);

    return profile;
}
