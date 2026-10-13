"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { useSharedPatientProfile } from "@/hooks/use-patient-profile";
import { authEntryLocale, getAuthEntryCopy, GUEST_LOCALE_STORAGE_KEY } from "@/content/auth-entry-copy";
import { DEFAULT_LOCALE, SUPPORTED_LOCALES, getLocaleLabel, normalizeLocale, type Locale } from "@/types";
import { Icon } from "@/components/ui/icons";

const subscribe = (callback: () => void) => {
  window.addEventListener("popstate", callback);
  return () => window.removeEventListener("popstate", callback);
};

// Before sign-in there is no patient profile. Carry this entry choice through links.
export function useAuthEntryLocale() {
  const shared = useSharedPatientProfile();
  const browserLocale = useSyncExternalStore(subscribe, authEntryLocale, () => DEFAULT_LOCALE);
  const [choice, setLocale] = useState<Locale | null>(null);
  const locale = shared?.profile?.preferredLanguage ?? choice ?? browserLocale;
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  return {
    locale,
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
  return <label className="flex items-center justify-end px-5 pt-3 text-sm font-medium text-muted">
    <span className="sr-only">{getAuthEntryCopy(locale).language}</span>
    <span className="relative min-w-0 max-w-full">
    <Icon name="globe" className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
    <select className="min-h-11 min-w-11 max-w-full appearance-none rounded-full bg-surface/70 py-2 pl-9 pr-9 text-[13px] font-medium text-ink-2 shadow-[inset_0_0_0_1px_rgba(16,32,43,.06)] outline-none hover:bg-surface focus:ring-4 focus:ring-brand/15"
      value={locale} onChange={(event) => onChange(normalizeLocale(event.target.value))}>
      {SUPPORTED_LOCALES.map((value) => <option key={value} value={value}>{getLocaleLabel(value)}</option>)}
    </select>
    <Icon name="chevronDown" className="pointer-events-none absolute right-3.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-2" />
    </span>
  </label>;
}
