import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PatientPage from "@/app/(dashboard)/patients/[id]/page";
import { patientLoadFailure } from "@/hooks/use-patient-detail";
import type { PatientDeepDive } from "@/services/clinicians";

const mocks = vi.hoisted(() => ({
    patientId: "synthetic-a", userId: "synthetic-clinician-a",
    fetch: vi.fn(), soap: vi.fn(), push: vi.fn(),
}));
vi.mock("next/navigation", () => ({
    useParams: () => ({ id: mocks.patientId }),
    useSearchParams: () => ({ get: () => null }),
    useRouter: () => ({ push: mocks.push }),
}));
vi.mock("react-redux", () => ({
    useSelector: (selector: (state: unknown) => unknown) => selector({ auth: { user: mocks.userId ? { id: mocks.userId } : null } }),
}));
vi.mock("@/services/clinicians", () => ({ fetchPatientDeepDive: mocks.fetch, generateSoapNote: mocks.soap, sendPatientMessage: vi.fn() }));

const patient = (id = "synthetic-a"): PatientDeepDive => ({
    patient_id: id, first_name: "Synthetic", last_name: id,
    email: "synthetic@example.com", risk_level: "low", adherence_score: 0,
    medications: [], adherence_series: [], symptom_reports: [], chat_messages: [],
    conditions: [], allergies: [], documents: [],
});
function deferred() {
    let resolve!: (data: PatientDeepDive) => void;
    let reject!: (error: unknown) => void;
    const promise = new Promise<PatientDeepDive>((res, rej) => { resolve = res; reject = rej; });
    return { promise, resolve, reject };
}

describe("patient detail load states", () => {
    beforeEach(() => {
        mocks.patientId = "synthetic-a";
        mocks.userId = "synthetic-clinician-a";
        mocks.fetch.mockReset();
        mocks.soap.mockReset();
        mocks.push.mockReset();
    });

    it.each([403, 404])("shows a neutral %s state with roster navigation and no Retry", async (status) => {
        mocks.fetch.mockRejectedValue(Object.assign(new Error("private server detail"), { status }));
        render(<PatientPage />);
        expect(await screen.findByRole("heading", { name: status === 403 ? "Access denied" : "Patient not found" })).toBeInTheDocument();
        expect(screen.getByRole("status")).not.toHaveClass("bg-red-50");
        expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
        expect(screen.queryByText(/private server detail/)).not.toBeInTheDocument();
        expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Return to patient roster" }));
        expect(mocks.push).toHaveBeenCalledWith("/patients");
    });

    it("uses structured status rather than matching server wording", () => {
        expect(patientLoadFailure(new Error("You are not assigned to this patient"))).toBe("transient");
        expect(patientLoadFailure(new Error("Patient not found"))).toBe("transient");
        expect(patientLoadFailure(Object.assign(new Error("Patient not found"), { status: 503 }))).toBe("transient");
    });

    it.each([new TypeError("Network failed"), Object.assign(new Error("Unavailable"), { status: 503 })])("retries transient failures", async (failure) => {
        mocks.fetch.mockRejectedValueOnce(failure).mockResolvedValueOnce(patient());
        render(<PatientPage />);
        fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
        expect(await screen.findByRole("heading", { name: "Synthetic synthetic-a" })).toBeInTheDocument();
        expect(mocks.fetch).toHaveBeenCalledTimes(2);
    });

    it("clears loaded content during refresh and after assignment denial", async () => {
        const next = deferred();
        mocks.fetch.mockResolvedValueOnce(patient()).mockReturnValueOnce(next.promise);
        render(<PatientPage />);
        await screen.findByRole("heading", { name: "Synthetic synthetic-a" });
        fireEvent.click(screen.getByRole("button", { name: "Refresh patient data" }));
        expect(screen.queryByText("synthetic@example.com")).not.toBeInTheDocument();
        await act(async () => next.reject({ status: 403 }));
        expect(await screen.findByText("Access denied")).toBeInTheDocument();
        expect(screen.queryByText("synthetic@example.com")).not.toBeInTheDocument();
    });

    it.each(["route", "account"])("hides loaded content immediately on %s change", async (change) => {
        const next = deferred();
        mocks.fetch.mockResolvedValueOnce(patient()).mockReturnValueOnce(next.promise);
        const view = render(<PatientPage />);
        await screen.findByRole("heading", { name: "Synthetic synthetic-a" });
        if (change === "route") mocks.patientId = "synthetic-b";
        else mocks.userId = "synthetic-clinician-b";
        view.rerender(<PatientPage />);
        expect(screen.queryByText("synthetic@example.com")).not.toBeInTheDocument();
        await act(async () => next.reject({ status: 403 }));
        expect(await screen.findByText("Access denied")).toBeInTheDocument();
    });

    it.each(["resolve", "reject"])("ignores a late %s from a previous route", async (outcome) => {
        const old = deferred();
        mocks.fetch.mockReturnValueOnce(old.promise).mockResolvedValueOnce(patient("synthetic-b"));
        const view = render(<PatientPage />);
        mocks.patientId = "synthetic-b";
        view.rerender(<PatientPage />);
        await screen.findByRole("heading", { name: "Synthetic synthetic-b" });
        await act(async () => {
            if (outcome === "resolve") old.resolve(patient());
            else old.reject({ status: 403 });
        });
        expect(screen.getByRole("heading", { name: "Synthetic synthetic-b" })).toBeInTheDocument();
        expect(screen.queryByText("Access denied")).not.toBeInTheDocument();
    });

    it("does not load patient data when signed out", async () => {
        mocks.userId = "";
        const view = render(<PatientPage />);
        expect(mocks.fetch).not.toHaveBeenCalled();
        mocks.userId = "synthetic-clinician-a";
        mocks.fetch.mockResolvedValue(patient());
        view.rerender(<PatientPage />);
        await waitFor(() => expect(mocks.fetch).toHaveBeenCalledOnce());
    });
});
