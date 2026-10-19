import { act, cleanup, render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { hydrateRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "@/proxy";
import { PatientLocaleProvider } from "@/contexts/patient-locale-context";
import { AuthEntryLanguage, useAuthEntryLocale } from "@/components/features/auth-entry-language";
import { clearPatientLocale, PATIENT_LOCALE_COOKIE, PATIENT_LOCALE_HEADER, preferredPatientLocale } from "@/content/patient-locale";
import { GUEST_LOCALE_STORAGE_KEY } from "@/content/auth-entry-copy";

vi.mock("@/hooks/use-patient-profile", () => ({ useSharedPatientProfile: () => null }));
function Entry({ seen }: { seen: string[] }) {
  const { locale, setLocale } = useAuthEntryLocale();
  seen.push(locale);
  return <AuthEntryLanguage locale={locale} onChange={setLocale} />;
}
beforeEach(() => {
  window.localStorage.clear();
  document.cookie = `${PATIENT_LOCALE_COOKIE}=; Path=/; Max-Age=0`;
  window.history.replaceState({}, "", "/login");
});
afterEach(cleanup);

describe("first-render patient locale", () => {
  it.each(["en-US", "es-MX"] as const)("hydrates known %s without rendering another language", async (locale) => {
    document.cookie = `${PATIENT_LOCALE_COOKIE}=${locale}; Path=/`;
    const seen: string[] = [];
    const tree = <PatientLocaleProvider initialLocale={locale}><Entry seen={seen} /></PatientLocaleProvider>;
    const container = document.createElement("div");
    container.innerHTML = renderToString(tree);
    expect(container.querySelector("select")).toHaveValue(locale);
    document.body.append(container);
    let root!: ReturnType<typeof hydrateRoot>;
    await act(async () => { root = hydrateRoot(container, tree); });
    expect(new Set(seen)).toEqual(new Set([locale]));
    expect(document.documentElement.lang).toBe(locale);
    await act(async () => root.unmount());
    container.remove();
  });

  it("defers legacy local-storage entry until Spanish and document language are resolved", () => {
    window.localStorage.setItem(GUEST_LOCALE_STORAGE_KEY, "es-MX");
    const seen: string[] = [];
    const tree = <PatientLocaleProvider initialLocale={null}><Entry seen={seen} /></PatientLocaleProvider>;
    const html = renderToString(tree);
    expect(html).toContain('role="status"');
    expect(html).not.toContain("<select");
    render(tree);
    expect(new Set(seen)).toEqual(new Set(["es-MX"]));
    expect(document.documentElement.lang).toBe("es-MX");
    expect(document.cookie).toContain(`${PATIENT_LOCALE_COOKIE}=es-MX`);
    expect(screen.getByRole("combobox", { name: "Idioma" })).toHaveValue("es-MX");
  });

  it("lets an entry query override a cookie and ignores spoofed or unsupported hints", () => {
    const response = proxy(new NextRequest("https://patient.example/login?lang=es-MX", {
      headers: { cookie: `${PATIENT_LOCALE_COOKIE}=en-US`, [PATIENT_LOCALE_HEADER]: "untrusted" },
    }));
    expect(response.headers.get(`x-middleware-request-${PATIENT_LOCALE_HEADER}`)).toBe("es-MX");
    expect(response.cookies.get(PATIENT_LOCALE_COOKIE)?.value).toBe("es-MX");
    const invalid = proxy(new NextRequest("https://patient.example/login?lang=fr", { headers: { [PATIENT_LOCALE_HEADER]: "es-MX" } }));
    expect(invalid.headers.get(`x-middleware-request-${PATIENT_LOCALE_HEADER}`)).toBe("en-US");
    const saved = proxy(new NextRequest("https://patient.example/today?lang=en-US", { headers: { cookie: `${PATIENT_LOCALE_COOKIE}=es-MX` } }));
    expect(saved.headers.get(`x-middleware-request-${PATIENT_LOCALE_HEADER}`)).toBe("es-MX");
  });

  it("falls back to Accept-Language when no cookie or query exists, so SSR always knows a locale", () => {
    const header = (acceptLanguage: string | null) => {
      const response = proxy(new NextRequest("https://patient.example/today", { headers: acceptLanguage ? { "accept-language": acceptLanguage } : {} }));
      return response.headers.get(`x-middleware-request-${PATIENT_LOCALE_HEADER}`);
    };
    expect(header("es-MX,es;q=0.9,en;q=0.8")).toBe("es-MX");
    expect(header("fr-FR,es-419;q=0.8")).toBe("es-MX");
    expect(header("en-GB,en;q=0.9")).toBe("en-US");
    expect(header("fr-FR")).toBe("en-US");
    expect(header(null)).toBe("en-US");
    expect(preferredPatientLocale("es;q=0,en;q=0.5")).toBe("en-US");
  });

  it("lets a saved cookie outrank Accept-Language", () => {
    const response = proxy(new NextRequest("https://patient.example/today", { headers: { cookie: `${PATIENT_LOCALE_COOKIE}=en-US`, "accept-language": "es-MX" } }));
    expect(response.headers.get(`x-middleware-request-${PATIENT_LOCALE_HEADER}`)).toBe("en-US");
  });

  it("clears the locale cookie and guest preference on sign-out", () => {
    document.cookie = `${PATIENT_LOCALE_COOKIE}=es-MX; Path=/`;
    window.localStorage.setItem(GUEST_LOCALE_STORAGE_KEY, "es-MX");
    clearPatientLocale();
    expect(document.cookie).not.toContain(PATIENT_LOCALE_COOKIE);
    expect(window.localStorage.getItem(GUEST_LOCALE_STORAGE_KEY)).toBeNull();
  });
});
