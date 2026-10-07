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
    expect(screen.getByText("Expired")).toBeInTheDocument();
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
    expect(screen.getByText("Awaiting patient response")).toBeInTheDocument();
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
    expect(screen.getByText("Confirmed")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Offer new times" }),
    ).not.toBeInTheDocument();
  });
});
