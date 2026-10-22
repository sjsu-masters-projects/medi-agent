import { configureStore } from "@reduxjs/toolkit";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Provider } from "react-redux";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SymptomHistoryList, SymptomReportView } from "@/components/features/symptom-history";
import { ApiClientError } from "@/services/api";
import type { SymptomReportDetail, SymptomReportSummary } from "@/services/symptom-history";
import { authSlice, hydrateSession } from "@/store/slices/auth-slice";
import type { Locale } from "@/types";

const { fetchList, fetchOne } = vi.hoisted(() => ({ fetchList: vi.fn(), fetchOne: vi.fn() }));
vi.mock("@/services/symptom-history", () => ({
  fetchSymptomHistory: fetchList,
  fetchSymptomReport: fetchOne,
}));

const summary: SymptomReportSummary = {
  id: "11111111-1111-1111-1111-111111111111",
  symptom: "Mareo al levantarme",
  severity: 6,
  onset: "Ayer",
  duration: "Dos horas",
  confirmed_at: "2026-10-20T03:30:00+00:00",
  locale: "es-MX",
  status: "reviewed",
  events: [
    { kind: "reported", at: "2026-10-20T03:30:00+00:00", actor_name: null },
    { kind: "shared_with_care_team", at: "2026-10-20T03:30:01+00:00", actor_name: null },
    { kind: "reviewed", at: "2026-10-20T15:00:00+00:00", actor_name: "Pat Reviewer" },
  ],
};
const detail: SymptomReportDetail = {
  ...summary,
  body_area: null,
  answers: [
    { question_id: "severity", label: "Intensidad (0 a 10)", state: "answered", display: "6", wording: "seis" },
    { question_id: "course", label: "Cómo ha cambiado", state: "unknown", display: "No sé", wording: null },
  ],
};

function store() {
  const s = configureStore({ reducer: { auth: authSlice.reducer } });
  s.dispatch(
    hydrateSession({
      accessToken: "access-token",
      expiresAt: 9999999999,
      refreshToken: "r",
      user: { email: "a@example.test", id: "p", role: "patient" },
    }),
  );
  return s;
}
const wrap = (node: React.ReactNode) => render(<Provider store={store()}>{node}</Provider>);

beforeEach(() => {
  fetchList.mockReset();
  fetchOne.mockReset();
});

describe("SymptomHistoryList", () => {
  it.each<[Locale, string, string]>([
    ["en-US", "My symptoms", "Severity 6 of 10"],
    ["es-MX", "Mis síntomas", "Intensidad 6 de 10"],
  ])("lists confirmed reports in the saved time zone (%s)", async (locale, heading, severity) => {
    fetchList.mockResolvedValue({ items: [summary], has_more: false });
    wrap(<SymptomHistoryList locale={locale} timezone="America/Los_Angeles" />);
    expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
    const link = await screen.findByRole("link");
    expect(link).toHaveAttribute("href", `/symptoms/${summary.id}`);
    expect(link).toHaveTextContent("Mareo al levantarme");
    expect(link).toHaveTextContent(severity);
    // 03:30 UTC on Oct 20 is the evening of Oct 19 in Los Angeles.
    expect(link.textContent).toMatch(/19/);
    expect(link).toHaveTextContent(locale === "es-MX" ? "Revisado" : "Reviewed");
    expect(fetchList).toHaveBeenCalledWith("access-token", expect.anything());
  });

  it("shows an empty state without inventing history", async () => {
    fetchList.mockResolvedValue({ items: [], has_more: false });
    wrap(<SymptomHistoryList locale="en-US" timezone="UTC" />);
    expect(await screen.findByText("No confirmed symptom reports yet")).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("shows an error with retry and recovers", async () => {
    fetchList.mockRejectedValueOnce(new Error("down"));
    fetchList.mockResolvedValueOnce({ items: [summary], has_more: true });
    wrap(<SymptomHistoryList locale="en-US" timezone="UTC" />);
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    await screen.findByRole("link");
    expect(screen.getByText("Showing your most recent reports.")).toBeInTheDocument();
  });
});

describe("SymptomReportView", () => {
  it("shows confirmed answers in the report language and a status timeline", async () => {
    fetchOne.mockResolvedValue(detail);
    const { container } = wrap(<SymptomReportView id={summary.id} locale="en-US" timezone="UTC" />);
    await screen.findByText("Intensidad (0 a 10)");
    expect(container.querySelector('dl[lang="es-MX"]')).toBeInTheDocument();
    expect(screen.getByText("No sé")).toBeInTheDocument();
    const steps = screen.getAllByRole("listitem").map((item) => item.textContent);
    expect(steps[0]).toContain("You confirmed this report");
    expect(steps[1]).toContain("Sent to your care team");
    expect(steps[2]).toContain("Reviewed by Pat Reviewer");
    expect(screen.getByRole("note")).toHaveTextContent("911");
    expect(fetchOne).toHaveBeenCalledWith("access-token", summary.id, expect.anything());
  });

  it("does not claim steps that were not recorded", async () => {
    fetchOne.mockResolvedValue({ ...detail, status: "reported", events: [summary.events[0]] });
    wrap(<SymptomReportView id={summary.id} locale="es-MX" timezone="UTC" />);
    await screen.findByText("Confirmaste este reporte");
    expect(screen.queryByText(/Enviado a tu equipo/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Revisado por/)).not.toBeInTheDocument();
  });

  it("treats a report that is not theirs as not found", async () => {
    fetchOne.mockRejectedValue(new ApiClientError("nope", 404, null));
    wrap(<SymptomReportView id="other" locale="en-US" timezone="UTC" />);
    expect(await screen.findByText("Report not found")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("offers retry on a server failure", async () => {
    fetchOne.mockRejectedValueOnce(new ApiClientError("boom", 503, null));
    fetchOne.mockResolvedValueOnce(detail);
    wrap(<SymptomReportView id={summary.id} locale="en-US" timezone="UTC" />);
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByText("Intensidad (0 a 10)")).toBeInTheDocument());
  });
});
