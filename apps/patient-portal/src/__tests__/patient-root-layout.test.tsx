import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import RootLayout from "@/app/layout";
import { PATIENT_LOCALE_COOKIE, PATIENT_LOCALE_HEADER } from "@/content/patient-locale";

const request = vi.hoisted(() => ({ cookie: undefined as string | undefined, header: null as string | null }));
vi.mock("next/headers", () => ({
  cookies: async () => ({ get: (name: string) => name === PATIENT_LOCALE_COOKIE ? { value: request.cookie } : undefined }),
  headers: async () => ({ get: (name: string) => name === PATIENT_LOCALE_HEADER ? request.header : null }),
}));
vi.mock("next/font/google", () => ({ Geist: () => ({ variable: "geist" }), Geist_Mono: () => ({ variable: "mono" }) }));
vi.mock("@/store/provider", () => ({ StoreProvider: ({ children }: { children: ReactNode }) => children }));
beforeEach(() => { request.cookie = undefined; request.header = null; });

describe("server document language", () => {
  it.each(["en-US", "es-MX"])("renders the saved %s cookie into html lang", async (locale) => {
    request.cookie = locale;
    const html = renderToStaticMarkup(await RootLayout({ children: <p>Entry content</p> }));
    expect(html).toContain(`<html lang="${locale}"`);
    expect(html).toContain("Entry content");
  });
  it("uses the current entry request hint before an older cookie", async () => {
    request.cookie = "en-US";
    request.header = "es-MX";
    expect(renderToStaticMarkup(await RootLayout({ children: <p>Entrada</p> }))).toContain('<html lang="es-MX"');
  });
  it("defers unknown browser preferences without exposing English entry content", async () => {
    request.cookie = "unsupported";
    expect(renderToStaticMarkup(await RootLayout({ children: <p>English entry content</p> }))).not.toContain("English entry content");
  });
});
