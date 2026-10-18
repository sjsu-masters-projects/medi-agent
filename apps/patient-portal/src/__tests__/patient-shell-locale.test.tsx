import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import AppLayout from "@/app/(app)/layout";

const state = vi.hoisted(() => ({ loading: true, language: "en-US" }));
vi.mock("next/navigation", () => ({ usePathname: () => "/today" }));
vi.mock("@/hooks/use-patient-profile", () => ({
  PatientProfileProvider: ({ children }: { children: ReactNode }) => children,
  useSharedPatientProfile: () => state,
}));
vi.mock("@/components/layouts", () => ({
  ProtectedRoute: ({ children }: { children: ReactNode }) => children,
  BottomNav: () => <nav>{state.language}</nav>,
}));
vi.mock("@/components/layouts/patient-language-control", () => ({ PatientLanguageControl: () => null }));
vi.mock("@/contexts/notifications-context", () => ({ NotificationProvider: ({ children }: { children: ReactNode }) => children }));
vi.mock("@/contexts/patient-shell-context", () => ({
  PatientShellProvider: ({ children }: { children: ReactNode }) => children,
  usePatientShell: () => ({ conversationOpen: false }),
}));

describe("authenticated first language render", () => {
  it("waits for the saved profile before mounting patient screens or navigation", () => {
    state.loading = true;
    state.language = "en-US";
    const mounted = vi.fn();
    function Screen() { mounted(state.language); return <p>{state.language === "es-MX" ? "Hoy" : "Today"}</p>; }
    const view = render(<AppLayout><Screen /></AppLayout>);
    expect(mounted).not.toHaveBeenCalled();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    state.loading = false;
    state.language = "es-MX";
    view.rerender(<AppLayout><Screen /></AppLayout>);
    expect(mounted).toHaveBeenCalledExactlyOnceWith("es-MX");
    expect(screen.getByText("Hoy")).toBeInTheDocument();
    expect(screen.queryByText("Today")).not.toBeInTheDocument();
  });
});
