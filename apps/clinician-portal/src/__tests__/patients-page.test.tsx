import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { dispatch, push, state } = vi.hoisted(() => ({
    dispatch: vi.fn(),
    push: vi.fn(),
    state: {
        dashboard: {
            patients: [
                {
                    patient_id: "d5cff0c5-0e56-4451-91ac-d13f7fce7e10",
                    first_name: "Maya",
                    last_name: "Patel",
                    risk_level: "high",
                    adherence_score: 0.72,
                    open_adr_count: 1,
                    active_med_count: 3,
                    recent_symptom_severity: 4,
                    last_activity: "2h ago",
                },
            ],
            loading: false,
            error: null as string | null,
        },
    },
}));

vi.mock("next/navigation", () => ({
    useRouter: () => ({ push }),
}));

vi.mock("react-redux", () => ({
    useDispatch: () => dispatch,
    useSelector: (selector: (value: typeof state) => unknown) => selector(state),
}));

import PatientsPage from "@/app/(dashboard)/patients/page";

describe("PatientsPage", () => {
    beforeEach(() => {
        dispatch.mockReset();
        push.mockReset();
        state.dashboard.error = null;
        state.dashboard.loading = false;
    });

    it("loads and opens the real authorized patient identifier", () => {
        render(<PatientsPage />);

        expect(screen.getByRole("button", { name: /maya patel/i })).toBeInTheDocument();
        expect(screen.queryByText("patient-1")).not.toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: /maya patel/i }));

        expect(push).toHaveBeenCalledWith("/patients/d5cff0c5-0e56-4451-91ac-d13f7fce7e10");
    });

    it("offers retry when the live roster request fails", () => {
        state.dashboard.error = "API error 500: dashboard";

        render(<PatientsPage />);

        expect(screen.getByRole("alert")).toHaveTextContent(/could not load assigned patients/i);
        fireEvent.click(screen.getByRole("button", { name: "Retry" }));
        expect(dispatch).toHaveBeenCalled();
    });
});
