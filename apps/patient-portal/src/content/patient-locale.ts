import { normalizeLocale, type Locale } from "@/types";

export const PATIENT_LOCALE_COOKIE = "patient-portal.locale";
export const PATIENT_LOCALE_HEADER = "x-patient-locale";

export function isAuthEntryPath(pathname: string): boolean {
  return ["/login", "/signup", "/onboarding", "/forgot-password", "/reset-password"].includes(pathname);
}

export function supportedPatientLocale(value: string | null | undefined): Locale | null {
  return value === "en-US" || value === "es-MX" ? value : null;
}

export function readLocaleCookie(): Locale | null {
  if (typeof document === "undefined") return null;
  const value = document.cookie.split("; ").find((part) => part.startsWith(`${PATIENT_LOCALE_COOKIE}=`))?.split("=")[1];
  return supportedPatientLocale(value);
}

// A presentation hint only: no identity, session or clinical data enters this cookie.
export function rememberPatientLocale(locale: Locale) {
  document.documentElement.lang = normalizeLocale(locale);
  document.cookie = `${PATIENT_LOCALE_COOKIE}=${locale}; Path=/; Max-Age=31536000; SameSite=Lax${window.location.protocol === "https:" ? "; Secure" : ""}`;
}
