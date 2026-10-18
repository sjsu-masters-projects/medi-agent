import { normalizeLocale, type Locale } from "@/types";

export const PATIENT_LOCALE_COOKIE = "patient-portal.locale";
export const PATIENT_LOCALE_HEADER = "x-patient-locale";
export const PATIENT_LOCALE_CHANGE_EVENT = "patient-locale-change";
export const GUEST_LOCALE_STORAGE_KEY = "patient-portal.guest.locale";

export function isAuthEntryPath(pathname: string): boolean {
  return ["/login", "/signup", "/onboarding", "/forgot-password", "/reset-password"].includes(pathname);
}

export function supportedPatientLocale(value: string | null | undefined): Locale | null {
  return value === "en-US" || value === "es-MX" ? value : null;
}

export function preferredPatientLocale(acceptLanguage: string | null): Locale {
  const preferences = (acceptLanguage ?? "")
    .split(",")
    .map((entry, order) => {
      const [rawTag, ...parameters] = entry.trim().split(";");
      const quality = parameters.reduce((current, parameter) => {
        const match = parameter.trim().match(/^q=(0(?:\.\d+)?|1(?:\.0+)?)$/i);
        return match ? Number(match[1]) : current;
      }, 1);
      return { order, quality, tag: rawTag.toLowerCase().replaceAll("_", "-") };
    })
    .filter(({ quality, tag }) => quality > 0 && tag && tag !== "*")
    .sort((left, right) => right.quality - left.quality || left.order - right.order);

  for (const { tag } of preferences) {
    if (tag === "es" || tag.startsWith("es-")) return "es-MX";
    if (tag === "en" || tag.startsWith("en-")) return "en-US";
  }
  return "en-US";
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
  window.dispatchEvent(new Event(PATIENT_LOCALE_CHANGE_EVENT));
}

export function clearPatientLocale() {
  document.cookie = `${PATIENT_LOCALE_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax${window.location.protocol === "https:" ? "; Secure" : ""}`;
  try { window.localStorage.removeItem(GUEST_LOCALE_STORAGE_KEY); } catch { /* Sign-out still clears the cookie when storage is unavailable. */ }
  window.dispatchEvent(new Event(PATIENT_LOCALE_CHANGE_EVENT));
}
