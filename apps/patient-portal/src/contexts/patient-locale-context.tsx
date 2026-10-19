"use client";

import { createContext, useContext, useLayoutEffect, useSyncExternalStore, type ReactNode } from "react";
import { authEntryLocale } from "@/content/auth-entry-copy";
import { PATIENT_LOCALE_CHANGE_EVENT, rememberPatientLocale } from "@/content/patient-locale";
import { PatientLoadingSkeleton } from "@/components/layouts/patient-loading-skeleton";
import type { Locale } from "@/types";

const PatientLocaleContext = createContext<Locale | null>(null);
const subscribe = (callback: () => void) => {
  window.addEventListener(PATIENT_LOCALE_CHANGE_EVENT, callback);
  return () => window.removeEventListener(PATIENT_LOCALE_CHANGE_EVENT, callback);
};

export function PatientLocaleProvider({ initialLocale, children }: { initialLocale: Locale | null; children: ReactNode }) {
  const locale = useSyncExternalStore(subscribe, authEntryLocale, () => initialLocale);
  useLayoutEffect(() => {
    if (locale) rememberPatientLocale(locale);
  }, [locale]);
  // Existing local-storage-only visitors resolve before any translated UI is painted.
  return <PatientLocaleContext.Provider value={locale}>{locale ? children : <PatientLoadingSkeleton />}</PatientLocaleContext.Provider>;
}

export function useInitialPatientLocale() { return useContext(PatientLocaleContext); }
