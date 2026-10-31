import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { PatientRiskData } from "@/services/clinicians";

const mocks = vi.hoisted(() => ({ dispatch: vi.fn(), push: vi.fn(), state: {
    dashboard: { stats: [{ label: "ADR Reviews Pending", value: "2 Pending" }],
        patients: [] as PatientRiskData[], loading: false, error: null as string | null },
} }));
vi.mock("@/hooks/use-clinic-filter", async () => (await import("@/test/clinic-filter-mock")).clinicFilterModule);
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock("react-redux", () => ({ useDispatch: () => mocks.dispatch,
    useSelector: (selector: (state: typeof mocks.state) => unknown) => selector(mocks.state) }));
vi.mock("@/services/dashboard-realtime", () => ({ subscribeDashboardRealtime: () => () => undefined }));
import DashboardPage from "@/app/(dashboard)/dashboard/page";
import { clinicFilterState, resetClinicFilter } from "@/test/clinic-filter-mock";

describe("Dashboard presentation", () => {
    beforeEach(() => {
        mocks.dispatch.mockReset(); mocks.push.mockReset();
        mocks.state.dashboard.loading = false; mocks.state.dashboard.error = null;
        mocks.state.dashboard.patients = [{ patient_id: "ca40d4c5-a74d-458e-b58c-c0ba32a61095",
            first_name: "Synthetic", last_name: "Patient", risk_level: "unknown", adherence_score: 0,
            open_adr_count: 0, active_med_count: 0, recent_symptom_severity: 0, last_activity: "No activity" }];
    });
    it("tags rows with the link's clinic only for a multi-clinic clinician", () => {
        mocks.state.dashboard.patients[0] = { ...mocks.state.dashboard.patients[0], clinic_id: "clinic-b", clinic_name: "Bay Clinic" };
        resetClinicFilter();
        const { unmount } = render(<DashboardPage />);
        expect(screen.queryByText("Bay Clinic")).not.toBeInTheDocument();
        expect(screen.queryByLabelText("Clinic")).not.toBeInTheDocument();
        unmount();
        clinicFilterState.clinics = [
            { clinic_id: "clinic-a", clinic_code: "A", clinic_name: "City Health", role: "admin", status: "active" },
            { clinic_id: "clinic-b", clinic_code: "B", clinic_name: "Bay Clinic", role: "provider", status: "active" },
        ] as never;
        render(<DashboardPage />);
        const chip = screen.getByText("Bay Clinic", { selector: "span" });
        expect(chip).toBeInTheDocument();
        // The chip sits on its own line under the name at every width.
        expect(chip.parentElement).toHaveClass("flex-col");
        expect(chip.parentElement?.className).not.toContain("sm:flex-row");
        expect(screen.getByLabelText("Clinic")).toBeInTheDocument();
        resetClinicFilter();
    });
    it("names All clinics or the filtered clinic, and nothing for a single-clinic clinician", () => {
        const two = [
            { clinic_id: "clinic-a", clinic_code: "A", clinic_name: "City Health", role: "admin", status: "active" },
            { clinic_id: "clinic-b", clinic_code: "B", clinic_name: "Bay Clinic", role: "provider", status: "active" },
        ] as never;
        resetClinicFilter();
        clinicFilterState.clinics = two;
        const first = render(<DashboardPage />);
        expect(screen.getByText(/ · All clinics$/)).toBeInTheDocument();
        first.unmount();
        clinicFilterState.clinicId = "clinic-b";
        const second = render(<DashboardPage />);
        expect(screen.getByText(/ · Bay Clinic$/)).toBeInTheDocument();
        second.unmount();
        resetClinicFilter();
        clinicFilterState.clinics = [two[0]] as never;
        render(<DashboardPage />);
        expect(screen.queryByText(/ · (City Health|All clinics)$/)).not.toBeInTheDocument();
        resetClinicFilter();
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
    it("explains versioned priority without presenting missing adherence as zero", () => {
        mocks.state.dashboard.patients[0] = {
            ...mocks.state.dashboard.patients[0], risk_level: "high", open_adr_count: 1,
            risk_explanation: { rule_version: "outpatient-review-priority-v1", calculated_at: "2026-10-21T09:00:00Z", adherence_available: false, adherence_window_days: 30, symptom_window_days: 7,
                factors: ["No recorded adherence responses; completion is unknown.", "1 ADR candidate awaiting review; not a confirmed adverse reaction.", "No confirmed symptom rating; severity is unknown."] },
        };
        render(<DashboardPage />);
        expect(screen.queryByText("0%")).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Explain review priority for Synthetic Patient" }));
        expect(screen.getByRole("dialog")).toHaveTextContent("outpatient-review-priority-v1");
        expect(screen.getByRole("dialog")).toHaveTextContent("not a diagnosis");
        expect(screen.getByRole("dialog")).toHaveTextContent("not the last clinical review");
    });

    it("does not invent a versioned explanation for an older snapshot", () => {
        render(<DashboardPage />);
        fireEvent.click(screen.getByRole("button", { name: "Explain review priority for Synthetic Patient" }));
        expect(screen.getByRole("dialog")).toHaveTextContent("The explanation for this priority isn't available");
    });

    it("disables dashboard refresh while loading", () => {
        mocks.state.dashboard.loading = true;
        render(<DashboardPage />);
        expect(screen.getByRole("button", { name: "Refresh dashboard" })).toBeDisabled();
    });
});
