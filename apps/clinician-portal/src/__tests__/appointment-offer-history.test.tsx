import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppointmentOfferHistory } from "@/components/features/appointment-offer-history";
import type { Appointment } from "@/types";

const visit: Appointment = {
  id: "synthetic-slot",
  patientId: "synthetic-patient",
  careTeamId: "synthetic-team",
  proposalGroupId: "synthetic-group",
  scheduledAt: "2026-10-05T16:00:00Z",
  proposalExpiresAt: "2026-10-04T16:00:00Z",
  durationMinutes: 30,
  appointmentType: "follow_up",
  status: "expired",
  createdAt: "2026-09-28T00:00:00Z",
  reason: "Synthetic follow-up",
  patientNote: "As written",
};
describe("expired offer history", () => {
  it("offers export for the confirmed slot, not its withdrawn siblings", () => {
    render(
      <AppointmentOfferHistory
        token="synthetic-session"
        appointments={[
          { ...visit, id: "booked", status: "confirmed" },
          { ...visit, id: "unchosen", status: "withdrawn" },
          visit,
        ]}
        timezone="America/Los_Angeles"
        disabled={false}
        onRepropose={vi.fn()}
      />,
    );
    expect(
      screen.getAllByRole("button", { name: "Add to calendar" }),
    ).toHaveLength(1);
  });
  it("permits a fresh offer after all old choices expire and preserves the old note", () => {
    const onRepropose = vi.fn();
    render(
      <AppointmentOfferHistory
        appointments={[visit]}
        timezone="America/Los_Angeles"
        disabled={false}
        onRepropose={onRepropose}
      />,
    );
    expect(screen.getAllByText("Expired").length).toBeGreaterThan(0);
    expect(screen.getByText(/As written/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Offer new times" }));
    expect(onRepropose).toHaveBeenCalledWith(visit);
  });
  it("keeps a partially expired offer active and labels its remaining response deadline", () => {
    render(
      <AppointmentOfferHistory
        appointments={[
          visit,
          {
            ...visit,
            id: "future",
            status: "proposed",
            scheduledAt: "2026-10-06T16:00:00Z",
          },
        ]}
        timezone="America/Los_Angeles"
        disabled={false}
        onRepropose={vi.fn()}
      />,
    );
    expect(screen.getAllByText("Awaiting patient response").length).toBeGreaterThan(0);
    expect(screen.getByText(/Available until.*9:00/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Offer new times" }),
    ).not.toBeInTheDocument();
  });
  it("shows the confirmed status when an earlier sibling expired", () => {
    render(
      <AppointmentOfferHistory
        appointments={[
          visit,
          {
            ...visit,
            id: "chosen",
            status: "confirmed",
            scheduledAt: "2026-10-06T16:00:00Z",
          },
        ]}
        timezone="UTC"
        disabled={false}
        onRepropose={vi.fn()}
      />,
    );
    expect(screen.getAllByText("Confirmed").length).toBeGreaterThan(0);
    expect(
      screen.queryByRole("button", { name: "Offer new times" }),
    ).not.toBeInTheDocument();
  });
  it("shows time first, then patient and clinic chip, then status for a multi-clinic clinician", () => {
    render(
      <AppointmentOfferHistory
        appointments={[{ ...visit, status: "confirmed", clinicId: "c1", clinicName: "Synthetic Clinic North" }]}
        timezone="UTC"
        disabled={false}
        patientName="Maya Patel"
        showClinic
        onRepropose={vi.fn()}
      />,
    );
    const row = document.getElementById("appointment-synthetic-slot")!;
    const line = row.firstElementChild as HTMLElement;
    const [time, group, status] = Array.from(line.children) as HTMLElement[];
    expect(time).toHaveTextContent("Oct 5, 2026, 4:00 PM");
    expect(time.querySelector(".font-semibold")).not.toBeNull();
    expect(group).toHaveTextContent("Maya PatelSynthetic Clinic North");
    expect(group).toHaveClass("basis-full", "sm:basis-auto");
    expect(status).toHaveTextContent("Confirmed");
    expect(line).toHaveClass("flex-wrap");
  });
  it("shows no clinic chip for a single-clinic clinician", () => {
    render(
      <AppointmentOfferHistory
        appointments={[{ ...visit, clinicName: "Synthetic Clinic North" }]}
        timezone="UTC"
        disabled={false}
        patientName="Maya Patel"
        onRepropose={vi.fn()}
      />,
    );
    expect(screen.queryByText("Synthetic Clinic North")).not.toBeInTheDocument();
    expect(screen.getByText("Maya Patel")).toBeInTheDocument();
  });
});
