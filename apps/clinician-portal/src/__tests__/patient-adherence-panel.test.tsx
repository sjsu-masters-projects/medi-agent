import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PatientAdherencePanel } from "@/components/features/patient-adherence-panel";
import { adherencePatient } from "./fixtures/adherence";

vi.mock("@/components/features/adherence-chart", () => ({
  AdherenceChart: () => <div>Chart</div>,
}));

describe("PatientAdherencePanel", () => {
  it.each([
    ["side_effects", "Side effects"],
    ["cost", "Cost"],
    ["access", "Access"],
    ["schedule", "Schedule"],
    ["confusion", "Instructions unclear"],
    ["other", "Other"],
  ])("shows the %s barrier as a patient statement", (code, label) => {
    render(
      <PatientAdherencePanel
        patient={{
          ...adherencePatient,
          adherence_barriers: [
            {
              target_type: "medication",
              target_id: "med-1",
              barrier_code: code,
              notes: "<script>Synthetic note</script>",
              logged_at: "2026-10-02T08:00:00Z",
            },
          ],
        }}
      />,
    );
    const section = screen
      .getByRole("heading", {
        name: /Patient-reported barriers/,
      })
      .closest("section")!;
    expect(within(section).getByText(label)).toBeInTheDocument();
    expect(
      within(section).getByText("Synthetic medication"),
    ).toBeInTheDocument();
    expect(
      within(section).getByText("<script>Synthetic note</script>"),
    ).toBeInTheDocument();
    expect(section.querySelector("script")).toBeNull();
    expect(
      within(section).getByText(/Patient statements, not reviewed ADR/),
    ).toBeInTheDocument();
    expect(
      within(section).getByText(/Report time in America\/Los_Angeles/),
    ).toBeInTheDocument();
  });

  it("shows response-based metrics without treating unknown days as missed", () => {
    render(<PatientAdherencePanel patient={adherencePatient} />);
    expect(screen.getByText("33%")).toBeInTheDocument();
    expect(screen.getByText("1 completed / 3 responses")).toBeInTheDocument();
    expect(screen.getByText("2 / 3")).toBeInTheDocument();
    expect(screen.getByText(/Unrecorded days are unknown/)).toBeInTheDocument();
    const table = screen.getByRole("table");
    expect(within(table).queryByText("Sep 30, 2026")).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Show days without responses"));
    expect(within(table).getByText("Sep 30, 2026")).toBeInTheDocument();
    expect(within(table).getByText("No response")).toBeInTheDocument();
    expect(within(table).getByText("0%")).toBeInTheDocument();
  });

  it("names barriers and retains historical targets without attributing them to a new activity", () => {
    render(<PatientAdherencePanel patient={adherencePatient} />);
    expect(screen.getByText("Schedule")).toBeInTheDocument();
    expect(
      screen.getByText("Synthetic scheduling barrier"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Earlier record — not in the current activity list"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Patient statements, not reviewed ADR/),
    ).toBeInTheDocument();
    expect(
      screen.getByText("No additional note provided."),
    ).toBeInTheDocument();
  });

  it("does not report zero adherence when there are no records", () => {
    render(
      <PatientAdherencePanel
        patient={{
          ...adherencePatient,
          adherence_series: [],
          medications: [],
          obligations: [],
          adherence_barriers: [],
        }}
      />,
    );
    expect(screen.getByText("No data")).toBeInTheDocument();
    expect(
      screen.getByText(/No recorded responses in this reporting window/),
    ).toBeInTheDocument();
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });
});
