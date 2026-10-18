import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthEntryLanguage, useAuthEntryLocale } from "@/components/features/auth-entry-language";
import { GUEST_LOCALE_STORAGE_KEY } from "@/content/auth-entry-copy";
import type { Locale } from "@/types";

const context = vi.hoisted(() => ({ profile: null as { preferredLanguage: Locale } | null }));
vi.mock("@/hooks/use-patient-profile", () => ({ useSharedPatientProfile: () => context }));
function Entry() {
  const { locale, setLocale } = useAuthEntryLocale();
  return <><output aria-label="Interface language">{locale}</output><AuthEntryLanguage locale={locale} onChange={setLocale} /></>;
}
beforeEach(() => {
  document.cookie = "patient-portal.locale=; Path=/; Max-Age=0";
  window.localStorage.clear();
  window.history.replaceState({}, "", "/login");
  context.profile = null;
  document.documentElement.lang = "en-US";
});
afterEach(cleanup);

describe("auth entry language", () => {
  it("restores only the guest entry choice and allows a route to carry that choice", () => {
    window.localStorage.setItem(GUEST_LOCALE_STORAGE_KEY, "es-MX");
    const view = render(<Entry />);
    expect(screen.getByRole("combobox", { name: "Idioma" })).toHaveValue("es-MX");
    expect(document.documentElement).toHaveAttribute("lang", "es-MX");
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "en-US" } });
    expect(window.localStorage.getItem(GUEST_LOCALE_STORAGE_KEY)).toBe("en-US");
    expect(document.documentElement).toHaveAttribute("lang", "en-US");
    view.unmount();
    window.history.replaceState({}, "", "/signup?lang=es-MX");
    render(<Entry />);
    expect(screen.getByRole("combobox", { name: "Idioma" })).toHaveValue("es-MX");
    expect(document.documentElement).toHaveAttribute("lang", "es-MX");
  });

  it("keeps each loaded patient preference authoritative over guest and route language", () => {
    window.localStorage.setItem(GUEST_LOCALE_STORAGE_KEY, "es-MX");
    window.history.replaceState({}, "", "/login?lang=es-MX");
    context.profile = { preferredLanguage: "en-US" };
    const view = render(<Entry />);
    expect(screen.getByLabelText("Interface language")).toHaveTextContent("en-US");
    expect(document.documentElement).toHaveAttribute("lang", "en-US");
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    context.profile = { preferredLanguage: "es-MX" };
    view.rerender(<Entry />);
    expect(screen.getByLabelText("Interface language")).toHaveTextContent("es-MX");
    expect(document.documentElement).toHaveAttribute("lang", "es-MX");
  });
});
