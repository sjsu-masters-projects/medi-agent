import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import SymptomsPage from "@/app/(app)/symptoms/page";

const settings = vi.hoisted(() => ({ locale: "en-US" }));
vi.mock("@/hooks/use-patient-profile", () => ({
  usePatientProfile: () => ({ preferredLanguage: settings.locale }),
  useSharedPatientProfile: () => null,
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ back: vi.fn() }) }));

describe("SymptomsPage", () => {
  it.each(["en-US", "es-MX"])(
    "offers an honest capture handoff in %s without invented reports or save actions",
    (locale) => {
      settings.locale = locale;
      render(<SymptomsPage />);
      const spanish = locale === "es-MX";
      expect(
        screen.getByRole("link", {
          name: spanish ? "Abrir chat con Nora" : "Open chat with Nora",
        }),
      ).toHaveAttribute("href", "/chat");
      expect(
        screen.getByText(
          spanish
            ? "Historial de síntomas no disponible aquí"
            : "Symptom history is not available here",
        ),
      ).toBeInTheDocument();
      expect(screen.getByRole("note")).toHaveTextContent("911");
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
        spanish ? "Reportar un síntoma" : "Report a symptom",
      );
      expect(screen.getByText(spanish
        ? "Historial de síntomas no disponible aquí"
        : "Symptom history is not available here").closest("details"))
        .not.toHaveAttribute("open");
      expect(
        screen
          .getByText(
            spanish
              ? "Qué incluir en su reporte"
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
