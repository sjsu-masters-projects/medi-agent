"use client";

import { createContext, useContext } from "react";
import type { PatientProfile } from "@/hooks/use-patient-profile";

export interface PatientProfileState {
  profile: PatientProfile | null;
  loading: boolean;
  error: boolean;
  timezoneMissing: boolean;
  refresh: () => void;
  updateProfile: (profile: PatientProfile | ((current: PatientProfile) => PatientProfile)) => void;
}

export const PatientProfileContext = createContext<PatientProfileState | null>(null);
export function useSharedPatientProfile() {
  return useContext(PatientProfileContext);
}
