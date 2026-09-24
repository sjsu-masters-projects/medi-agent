import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import VisitsPage from "@/app/(app)/visits/page";
import { AppointmentStatus, type Appointment } from "@/types";

const respond = vi.fn();

interface VisitsHookState {
  visits: Appointment[];
  loading: boolean;
  error: string | null;
  respond: typeof respond;
  respondingId: string | null;
  refresh: () => void;
}

let hookState: VisitsHookState;

vi.mock("next/navigation", () => ({
  useRouter: () => ({ back: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/hooks/use-visits-data", () => ({
  useVisitsData: () => hookState,
}));

function makeVisit(overrides: Partial<Appointment> = {}): Appointment {
  return {
    id: "appt-1",
    patientId: "pt-1",
    careTeamId: "ct-1",
    clinicianName: "Elena Park",
    scheduledAt: "2026-05-08T17:00:00Z",
    durationMinutes: 30,
    appointmentType: "follow_up",
    status: AppointmentStatus.PROPOSED,
    createdAt: "2026-05-07T10:00:00Z",
    reason: "Blood pressure check",
    ...overrides,
  };
}

beforeEach(() => {
  respond.mockReset();
  hookState = {
    visits: [],
    loading: false,
    error: null,
    respond,
    respondingId: null,
    refresh: vi.fn(),
  };
});

describe("VisitsPage", () => {
  it("shows an empty state when there are no visits", () => {
    render(<VisitsPage />);
    expect(screen.getByText(/No visits yet/i)).toBeInTheDocument();
  });

  it("shows a proposed visit and responds on accept/decline", () => {
    hookState.visits = [makeVisit()];
    render(<VisitsPage />);

    expect(screen.getByText(/Awaiting your response/i)).toBeInTheDocument();
    expect(screen.getByText(/Blood pressure check/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Accept/i }));
    expect(respond).toHaveBeenCalledWith("appt-1", "accept");

    fireEvent.click(screen.getByRole("button", { name: /Decline/i }));
    expect(respond).toHaveBeenCalledWith("appt-1", "decline");
  });

  it("shows a confirmed visit without response actions", () => {
    hookState.visits = [
      makeVisit({ id: "appt-2", status: AppointmentStatus.CONFIRMED }),
    ];
    render(<VisitsPage />);

    expect(screen.getByText("Confirmed")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Accept/i }),
    ).not.toBeInTheDocument();
  });

  it("shows an error state with the failure message", () => {
    hookState.error = "The network is unavailable.";
    render(<VisitsPage />);
    expect(screen.getByText(/network is unavailable/i)).toBeInTheDocument();
  });
});
