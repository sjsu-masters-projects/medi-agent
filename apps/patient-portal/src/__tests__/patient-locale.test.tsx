import { act, cleanup, render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { hydrateRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "@/proxy";
import { PatientLocaleProvider } from "@/contexts/patient-locale-context";
import { AuthEntryLanguage, useAuthEntryLocale } from "@/components/features/auth-entry-language";
import { PATIENT_LOCALE_COOKIE, PATIENT_LOCALE_HEADER } from "@/content/patient-locale";
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
    expect(renderToString(tree)).toBe("");
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
    expect(invalid.headers.get(`x-middleware-request-${PATIENT_LOCALE_HEADER}`)).toBeNull();
    const saved = proxy(new NextRequest("https://patient.example/today?lang=en-US", { headers: { cookie: `${PATIENT_LOCALE_COOKIE}=es-MX` } }));
    expect(saved.headers.get(`x-middleware-request-${PATIENT_LOCALE_HEADER}`)).toBe("es-MX");
  });
});
