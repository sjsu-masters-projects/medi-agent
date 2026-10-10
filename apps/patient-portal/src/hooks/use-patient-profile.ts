"use client";

import { createElement, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { PatientProfileContext } from "@/contexts/patient-profile-context";
export { useSharedPatientProfile } from "@/contexts/patient-profile-context";
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

function useProfileState(enabled = true) {
  const accessToken = useSelector((state: RootState) => state.auth.accessToken);
  const [sessionToken, setSessionToken] = useState(accessToken);
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<ProfileResult | null>(null);
  const revision = useRef(0);
  const latest = useRef({ accessToken, attempt });
  useLayoutEffect(() => { latest.current = { accessToken, attempt }; }, [accessToken, attempt]);
  if (sessionToken !== accessToken) {
    setSessionToken(accessToken);
    setResult(null);
  }
  const refresh = useCallback(() => setAttempt((current) => current + 1), []);
  const updateProfile = useCallback((update: PatientProfile | ((current: PatientProfile) => PatientProfile)) => {
    if (!accessToken || latest.current.accessToken !== accessToken) return;
    revision.current += 1;
    const currentAttempt = latest.current.attempt;
    setResult((previous) => {
      if (typeof update === "function" && (!previous?.profile || previous.token !== accessToken)) return previous;
      const profile = typeof update === "function" ? update(previous!.profile!) : update;
      if (!profile) return previous;
      return { token: accessToken, attempt: currentAttempt, profile, error: false, timezoneMissing: !profile.timezone.trim() };
    });
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken || !enabled) return;
    let isCurrent = true;
    const requestRevision = revision.current;
    api
      .get<PatientProfileResponse>("/api/v1/patients/me", {
        token: accessToken,
      })
      .then((raw) => {
        if (isCurrent && requestRevision === revision.current)
          setResult({
            token: accessToken,
            attempt,
            profile: mapProfile(raw),
            error: false,
            timezoneMissing: !raw.timezone?.trim(),
          });
      })
      .catch(() => {
        if (isCurrent && requestRevision === revision.current)
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
  }, [accessToken, attempt, enabled]);

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
    updateProfile,
  };
}

export function PatientProfileProvider({ children }: { children: ReactNode }) {
  const state = useProfileState();
  return createElement(PatientProfileContext.Provider, { value: state }, children);
}

export function usePatientProfileState() {
  const shared = useContext(PatientProfileContext);
  const standalone = useProfileState(!shared);
  return shared ?? standalone;
}

export function usePatientProfile(): PatientProfile | null {
  return usePatientProfileState().profile;
}
