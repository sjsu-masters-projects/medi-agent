import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import VisitsPage from "@/app/(app)/visits/page";
import type { AppointmentApiRecord } from "@/services/appointments";

const push = vi.fn();

vi.mock("next/navigation", () => ({
    useRouter: () => ({ back: vi.fn(), push }),
}));

const getMock = vi.fn();

vi.mock("@/services/api", () => ({
    api: {
        get: (...args: unknown[]) => getMock(...args),
    },
}));

let authState = {
    accessToken: "test-token" as string | null,
    loading: false,
};

vi.mock("react-redux", () => ({
    useSelector: (selector: (state: unknown) => unknown) =>
        selector({ auth: authState }),
}));

function buildRecord(overrides: Partial<AppointmentApiRecord> = {}): AppointmentApiRecord {
    return {
        id: "appt-1",
        patient_id: "patient-1",
        care_team_id: "care-team-1",
        clinician_name: "Elena Park",
        scheduled_at: "2099-01-15T17:30:00Z",
        duration_minutes: 45,
        appointment_type: "follow_up",
        location: "Room 302",
        reason: "Asthma review",
        notes: "Bring your inhaler",
        status: "scheduled",
        created_at: "2026-01-01T00:00:00Z",
        ...overrides,
    } as AppointmentApiRecord;
}

describe("VisitsPage", () => {
    beforeEach(() => {
        getMock.mockReset();
        push.mockReset();
        authState = { accessToken: "test-token", loading: false };
    });

    it("requests the patient's appointments with the access token", async () => {
        getMock.mockResolvedValue([]);

        render(<VisitsPage />);

        await waitFor(() => {
            expect(getMock).toHaveBeenCalledWith("/api/v1/appointments/", {
                token: "test-token",
            });
        });
    });

    it("renders appointment details returned by the backend", async () => {
        getMock.mockResolvedValue([buildRecord()]);

        render(<VisitsPage />);

        expect(await screen.findByText("Elena Park")).toBeInTheDocument();
        expect(screen.getByText("Room 302")).toBeInTheDocument();
        expect(screen.getByText("Asthma review")).toBeInTheDocument();
        expect(screen.getByText("Follow-up")).toBeInTheDocument();
        expect(screen.getByText("Scheduled")).toBeInTheDocument();
        expect(screen.getByText(/45 min/)).toBeInTheDocument();
        expect(screen.queryByText(/No visits scheduled yet/i)).not.toBeInTheDocument();
    });

    it("omits optional fields that the backend did not provide", async () => {
        getMock.mockResolvedValue([
            buildRecord({ clinician_name: null, location: null, reason: null }),
        ]);

        render(<VisitsPage />);

        expect(await screen.findByText("Follow-up")).toBeInTheDocument();
        expect(screen.queryByText("Elena Park")).not.toBeInTheDocument();
        expect(screen.queryByText("Room 302")).not.toBeInTheDocument();
        expect(screen.queryByText(/Reason for visit/i)).not.toBeInTheDocument();
    });

    it("shows the empty state when the patient has no appointments", async () => {
        getMock.mockResolvedValue([]);

        render(<VisitsPage />);

        expect(await screen.findByText(/No visits scheduled yet/i)).toBeInTheDocument();
        expect(
            screen.getByRole("button", { name: /Message care team/i }),
        ).toBeInTheDocument();
    });

    it("shows a retry-able error state when the request fails", async () => {
        getMock.mockRejectedValue(new Error("Backend unavailable"));

        render(<VisitsPage />);

        expect(await screen.findByText(/Could not load visits/i)).toBeInTheDocument();
        expect(screen.getByText(/Backend unavailable/i)).toBeInTheDocument();
        expect(screen.queryByText(/No visits scheduled yet/i)).not.toBeInTheDocument();
    });

    it("does not call the API when there is no session", async () => {
        authState = { accessToken: null, loading: false };

        render(<VisitsPage />);

        await waitFor(() => {
            expect(screen.getByText(/No visits scheduled yet/i)).toBeInTheDocument();
        });
        expect(getMock).not.toHaveBeenCalled();
    });
});
