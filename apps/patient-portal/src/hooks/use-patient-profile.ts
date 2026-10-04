"use client";

import { useCallback, useEffect, useState } from "react";
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
  timezone?: string | null;
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

interface ProfileResult {
  token: string;
  attempt: number;
  profile: PatientProfile | null;
  error: boolean;
  timezoneMissing: boolean;
}

export function usePatientProfileState() {
  const accessToken = useSelector((state: RootState) => state.auth.accessToken);
  const [sessionToken, setSessionToken] = useState(accessToken);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<ProfileResult | null>(null);
  if (sessionToken !== accessToken) {
    setSessionToken(accessToken);
    setResult(null);
  }
  const refresh = useCallback(() => setAttempt((current) => current + 1), []);

  useEffect(() => {
    if (!accessToken) return;
    let isCurrent = true;
    api
      .get<PatientProfileResponse>("/api/v1/patients/me", {
        token: accessToken,
      })
      .then((raw) => {
        if (isCurrent)
          setResult({
            token: accessToken,
            attempt,
            profile: mapProfile(raw),
            error: false,
            timezoneMissing: !raw.timezone?.trim(),
          });
      })
      .catch(() => {
        if (isCurrent)
          setResult({
            token: accessToken,
            attempt,
            profile: null,
            error: true,
            timezoneMissing: true,
          });
      });
    return () => {
      isCurrent = false;
    };
  }, [accessToken, attempt]);

  // Bind results to the session and retry so an old patient's settings never render.
  const current =
    accessToken && result?.token === accessToken && result.attempt === attempt
      ? result
      : null;
  return {
    profile: current?.profile ?? null,
    loading: Boolean(accessToken && !current),
    error: current?.error ?? false,
    timezoneMissing: current?.timezoneMissing ?? true,
    refresh,
  };
}

export function usePatientProfile(): PatientProfile | null {
  return usePatientProfileState().profile;
}
