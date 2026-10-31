import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { dispatch, state } = vi.hoisted(() => ({
    dispatch: vi.fn(),
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

vi.mock("@/hooks/use-clinic-filter", async () => (await import("@/test/clinic-filter-mock")).clinicFilterModule);

vi.mock("react-redux", () => ({
    useDispatch: () => dispatch,
    useSelector: (selector: (value: typeof state) => unknown) => selector(state),
}));

import PatientsPage from "@/app/(dashboard)/patients/page";
import { clinicFilterState, resetClinicFilter } from "@/test/clinic-filter-mock";

const originalPatient = { ...state.dashboard.patients[0] };

const twoClinics = [
    { clinic_id: "clinic-a", clinic_code: "AAA111", clinic_name: "City Health", role: "admin", status: "active" },
    { clinic_id: "clinic-b", clinic_code: "BBB222", clinic_name: "Bay Clinic", role: "provider", status: "active" },
] as never;


describe("PatientsPage", () => {
    beforeEach(() => {
        dispatch.mockReset();
        state.dashboard.error = null;
        state.dashboard.loading = false;
        state.dashboard.patients = [{ ...originalPatient, clinic_id: "clinic-b", clinic_name: "Bay Clinic" } as never];
        resetClinicFilter();
    });

    it("shows no clinic chip and no clinic filter for a single-clinic clinician", () => {
        render(<PatientsPage />);
        expect(screen.queryByText("Bay Clinic")).not.toBeInTheDocument();
        expect(screen.queryByLabelText("Clinic")).not.toBeInTheDocument();
        expect(dispatch).toHaveBeenCalledTimes(1);
    });

    it("shows the clinic chip after the name and a Clinic filter with several clinics", () => {
        clinicFilterState.clinics = twoClinics;
        render(<PatientsPage />);
        const row = screen.getByRole("link", { name: /maya patel/i });
        expect(row).toHaveTextContent("Maya Patel");
        expect(screen.getByText("Bay Clinic", { selector: "span" })).toHaveAttribute("title", "Bay Clinic");
        expect(screen.getByLabelText("Clinic")).toHaveValue("");
        fireEvent.change(screen.getByLabelText("Clinic"), { target: { value: "clinic-a" } });
        expect(clinicFilterState.setClinicId).toHaveBeenCalledWith("clinic-a");
    });

    it("asks the server for the chosen clinic and explains an empty clinic", () => {
        clinicFilterState.clinics = twoClinics;
        clinicFilterState.clinicId = "clinic-b";
        const loaded = state.dashboard.patients;
        state.dashboard.patients = [];
        render(<PatientsPage />);
        state.dashboard.patients = loaded;
        expect(screen.getByText(/No patients at Bay Clinic match/)).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Show all clinics" }));
        expect(clinicFilterState.setClinicId).toHaveBeenCalledWith(null);
    });

    it("loads and opens the real authorized patient identifier", () => {
        render(<PatientsPage />);

        expect(screen.getByRole("link", { name: /maya patel/i })).toHaveAccessibleName("Maya Patel");
        expect(screen.queryByText("patient-1")).not.toBeInTheDocument();

        expect(screen.getByRole("link", { name: /maya patel/i })).toHaveAttribute(
            "href", "/patients/d5cff0c5-0e56-4451-91ac-d13f7fce7e10",
        );
    });

    it("offers retry when the live roster request fails", () => {
        state.dashboard.error = "API error 500: dashboard";

        render(<PatientsPage />);

        expect(screen.getByRole("alert")).toHaveTextContent(/could not load assigned patients/i);
        fireEvent.click(screen.getByRole("button", { name: "Retry" }));
        expect(dispatch).toHaveBeenCalled();
    });
    it("associates roster values with native column and patient row headers", () => {
        render(<PatientsPage />);
        const table = screen.getByRole("table", { name: "Patient roster" });
        expect(within(table).getAllByRole("columnheader").map((cell) => cell.textContent)).toEqual([
            "Patient", "Risk level", "Adherence", "Active meds", "Last activity", "ADR alerts",
        ]);
        for (const header of within(table).getAllByRole("columnheader")) {
            expect(header).toHaveAttribute("scope", "col");
        }
        expect(within(table).getByRole("rowheader", { name: /maya patel/i })).toHaveAttribute("scope", "row");
        expect(within(table).getAllByRole("cell")).toHaveLength(5);
        expect(screen.queryByRole("button", { name: /maya patel/i })).not.toBeInTheDocument();
    });

    it("preserves sort and risk filtering with ordinary patient links", () => {
        state.dashboard.patients.push({ ...originalPatient, patient_id: "second", first_name: "Robin", last_name: "Lee", adherence_score: .4, risk_level: "low", last_activity: "5m ago" } as never);
        render(<PatientsPage />);
        const paths = () => within(screen.getByRole("table")).getAllByRole("link").map((link) => link.getAttribute("href"));
        expect(paths()).toEqual([`/patients/${originalPatient.patient_id}`, "/patients/second"]);
        fireEvent.change(screen.getByLabelText("Sort patients"), { target: { value: "adherence" } });
        expect(paths()).toEqual(["/patients/second", `/patients/${originalPatient.patient_id}`]);
        fireEvent.change(screen.getByLabelText("Sort patients"), { target: { value: "activity" } });
        expect(paths()).toEqual(["/patients/second", `/patients/${originalPatient.patient_id}`]);
        fireEvent.change(screen.getByLabelText("Filter patients by risk"), { target: { value: "low" } });
        expect(paths()).toEqual(["/patients/second"]);
    });

    it("keeps unavailable adherence distinct from zero and spans the empty table state", () => {
        state.dashboard.patients = [{ ...originalPatient, risk_level: "unknown", adherence_score: 0 } as never];
        render(<PatientsPage />);
        expect(screen.getByText("Not enough data")).toBeInTheDocument();
        expect(screen.queryByText("0%")).not.toBeInTheDocument();
        fireEvent.change(screen.getByLabelText("Filter patients by risk"), { target: { value: "high" } });
        const empty = within(screen.getByRole("table")).getByRole("cell");
        expect(empty).toHaveAttribute("colspan", "6");
        expect(empty).toHaveTextContent("No assigned patients match these filters.");
        expect(screen.queryByRole("link", { name: /maya/i })).not.toBeInTheDocument();
    });

});
