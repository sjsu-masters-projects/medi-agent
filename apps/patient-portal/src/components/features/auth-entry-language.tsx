"use client";

import { useState, useSyncExternalStore } from "react";
import { useSharedPatientProfile } from "@/hooks/use-patient-profile";
import { authEntryLocale, getAuthEntryCopy, GUEST_LOCALE_STORAGE_KEY } from "@/content/auth-entry-copy";
import { DEFAULT_LOCALE, SUPPORTED_LOCALES, getLocaleLabel, normalizeLocale, type Locale } from "@/types";

const subscribe = (callback: () => void) => {
  window.addEventListener("popstate", callback);
  return () => window.removeEventListener("popstate", callback);
};

// Before sign-in there is no patient profile. Carry this entry choice through links.
export function useAuthEntryLocale() {
  const shared = useSharedPatientProfile();
  const browserLocale = useSyncExternalStore(subscribe, authEntryLocale, () => DEFAULT_LOCALE);
  const [choice, setLocale] = useState<Locale | null>(null);
  return {
    locale: shared?.profile?.preferredLanguage ?? choice ?? browserLocale,
    setLocale: (locale: Locale) => {
      if (shared?.profile) return;
      setLocale(locale);
      // This key is for entry screens only, never an authenticated preference.
      try { window.localStorage.setItem(GUEST_LOCALE_STORAGE_KEY, locale); } catch { /* Entry choice remains usable without storage. */ }
    },
  };
}

export function AuthEntryLanguage({ locale, onChange }: { locale: Locale; onChange: (locale: Locale) => void }) {
  const shared = useSharedPatientProfile();
  if (shared?.profile) return null;
  return <label className="flex items-center justify-end gap-3 px-5 py-3 text-sm font-medium text-[#5b6b83]">
    {getAuthEntryCopy(locale).language}
    <select className="min-h-11 rounded-lg border border-[#d9cbc0] bg-white px-3 py-2 text-[#17233a] focus-visible:outline-2 focus-visible:outline-[#147465]"
      value={locale} onChange={(event) => onChange(normalizeLocale(event.target.value))}>
      {SUPPORTED_LOCALES.map((value) => <option key={value} value={value}>{getLocaleLabel(value)}</option>)}
    </select>
  </label>;
}
