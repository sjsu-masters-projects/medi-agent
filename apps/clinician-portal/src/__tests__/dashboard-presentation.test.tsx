import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PatientRiskData } from "@/services/clinicians";

const mocks = vi.hoisted(() => ({ dispatch: vi.fn(), push: vi.fn(), state: {
    dashboard: { stats: [{ label: "ADR Reviews Pending", value: "2 Pending" }],
        patients: [] as PatientRiskData[], loading: false, error: null as string | null },
} }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock("react-redux", () => ({ useDispatch: () => mocks.dispatch,
    useSelector: (selector: (state: typeof mocks.state) => unknown) => selector(mocks.state) }));
vi.mock("@/services/dashboard-realtime", () => ({ subscribeDashboardRealtime: () => () => undefined }));
import DashboardPage from "@/app/(dashboard)/dashboard/page";

describe("Dashboard presentation", () => {
    beforeEach(() => {
        mocks.dispatch.mockReset(); mocks.push.mockReset();
        mocks.state.dashboard.loading = false; mocks.state.dashboard.error = null;
        mocks.state.dashboard.patients = [{ patient_id: "ca40d4c5-a74d-458e-b58c-c0ba32a61095",
            first_name: "Synthetic", last_name: "Patient", risk_level: "unknown", adherence_score: 0,
            open_adr_count: 0, active_med_count: 0, recent_symptom_severity: 0, last_activity: "No activity" }];
    });
    it("keeps internal patient identity in navigation without displaying it or inferring missed doses", () => {
        render(<DashboardPage />);
        expect(screen.queryByText(/ca40d4c5/)).not.toBeInTheDocument();
        expect(screen.queryByText("0%")).not.toBeInTheDocument();
        expect(screen.getByText("Not enough data")).toBeInTheDocument();
        expect(screen.queryByText("Missed Doses")).not.toBeInTheDocument();
        expect(screen.queryByText("On Track")).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Review" }));
        expect(mocks.push).toHaveBeenCalledWith("/patients/ca40d4c5-a74d-458e-b58c-c0ba32a61095");
    });
    it("shows a real zero recorded-response score and a concise pending count", () => {
        mocks.state.dashboard.patients[0].risk_level = "high";
        render(<DashboardPage />);
        expect(screen.getByText("0%")).toBeInTheDocument();
        expect(screen.getByText("ADR Reviews")).toBeInTheDocument();
        expect(screen.getByText("2")).toBeInTheDocument();
        expect(screen.queryByText("2 Pending")).not.toBeInTheDocument();
        expect(screen.getByText(/share of recorded responses/)).toHaveTextContent("last 30 days");
    });
    it("disables dashboard refresh while loading", () => {
        mocks.state.dashboard.loading = true;
        render(<DashboardPage />);
        expect(screen.getByRole("button", { name: "Refresh dashboard" })).toBeDisabled();
    });
});
