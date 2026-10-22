import { configureStore } from "@reduxjs/toolkit";
import { fireEvent, render, screen } from "@testing-library/react";
import { Provider } from "react-redux";
import { describe, expect, it, vi } from "vitest";
import SymptomsPage from "@/app/(app)/symptoms/page";
import { authSlice, hydrateSession } from "@/store/slices/auth-slice";

const settings = vi.hoisted(() => ({ locale: "en-US", setConversationOpen: vi.fn() }));
vi.mock("@/contexts/patient-shell-context", () => ({
  usePatientShell: () => ({ setConversationOpen: settings.setConversationOpen }),
}));
vi.mock("@/hooks/use-patient-profile", () => ({
  usePatientProfile: () => ({ preferredLanguage: settings.locale }),
  useSharedPatientProfile: () => null,
}));
vi.mock("@/services/symptom-history", () => ({
  fetchSymptomHistory: vi.fn(() => new Promise(() => {})),
  fetchSymptomReport: vi.fn(),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ back: vi.fn() }) }));

describe("SymptomsPage", () => {
  it.each(["en-US", "es-MX"])(
    "offers an honest capture handoff in %s with a history section that invents nothing",
    (locale) => {
      settings.locale = locale;
      settings.setConversationOpen.mockClear();
      const store = configureStore({ reducer: { auth: authSlice.reducer } });
      store.dispatch(
        hydrateSession({
          accessToken: "t",
          expiresAt: 9999999999,
          refreshToken: "r",
          user: { email: "a@example.test", id: "p", role: "patient" },
        }),
      );
      render(
        <Provider store={store}>
          <SymptomsPage />
        </Provider>,
      );
      const spanish = locale === "es-MX";
      expect(
        screen.getByRole("link", {
          name: spanish ? "Abrir chat con Nora" : "Open chat with Nora",
        }),
      ).toHaveAttribute("href", "/chat");
      fireEvent.click(screen.getByRole("link", { name: spanish ? "Abrir chat con Nora" : "Open chat with Nora" }));
      expect(settings.setConversationOpen).toHaveBeenCalledWith(true);
      expect(screen.getByRole("heading", { name: spanish ? "Mis síntomas" : "My symptoms" })).toBeInTheDocument();
      expect(screen.getByRole("note")).toHaveTextContent("911");
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
        spanish ? "Reportar un síntoma" : "Report a symptom",
      );
      expect(
        screen
          .getByText(
            spanish
              ? "Qué incluir en tu reporte"
              : "What to include in your report",
          )
          .closest("details"),
      ).not.toHaveAttribute("open");
      expect(
        screen.queryByText(
          /Dizziness|medication adjustment|Care team notified|AI pattern detected/i,
        ),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /Save symptom|Guardar síntoma/i }),
      ).not.toBeInTheDocument();
      expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    },
  );
});
