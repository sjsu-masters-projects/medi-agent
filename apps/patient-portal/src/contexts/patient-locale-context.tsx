"use client";

import { createContext, useContext, useLayoutEffect, useSyncExternalStore, type ReactNode } from "react";
import { authEntryLocale } from "@/content/auth-entry-copy";
import { rememberPatientLocale } from "@/content/patient-locale";
import type { Locale } from "@/types";

const PatientLocaleContext = createContext<Locale | null>(null);
const subscribe = () => () => {};

export function PatientLocaleProvider({ initialLocale, children }: { initialLocale: Locale | null; children: ReactNode }) {
  const locale = useSyncExternalStore(subscribe, authEntryLocale, () => initialLocale);
  useLayoutEffect(() => {
    if (locale) rememberPatientLocale(locale);
  }, [locale]);
  // Existing local-storage-only visitors resolve before any translated UI is painted.
  return <PatientLocaleContext.Provider value={locale}>{locale ? children : null}</PatientLocaleContext.Provider>;
}

export function useInitialPatientLocale() { return useContext(PatientLocaleContext); }
