import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PatientADRPanel } from "@/components/features/patient-adr-panel";

const mocks = vi.hoisted(() => ({ fetchADRReviewQueue: vi.fn() }));
vi.mock("@/services/clinicians", async (importOriginal) => ({
    ...(await importOriginal<typeof import("@/services/clinicians")>()),
    ...mocks,
}));

const base = {
    patientId: "patient-1",
    patientFirstName: "Maya",
    patientLastName: "Patel",
    symptom: "dizziness",
    suspectMedicationName: "lisinopril",
    naranjoScore: 3,
    causality: "Possible",
    naranjoAssessment: {},
    createdAt: "2026-10-02T09:53:00Z",
};

describe("Patient ADR tab", () => {
    beforeEach(() => mocks.fetchADRReviewQueue.mockReset());

    it("lists current and past cases for the patient, linking to the case page", async () => {
        mocks.fetchADRReviewQueue.mockResolvedValue([
            { ...base, id: "adr-1", status: "draft" },
            { ...base, id: "adr-2", status: "dismissed", symptom: "cough" },
        ]);
        render(<PatientADRPanel patientId="patient-1" />);
        expect(await screen.findByText(/cough/)).toBeInTheDocument();
        expect(mocks.fetchADRReviewQueue).toHaveBeenCalledWith({ status: "all", patientId: "patient-1" });
        const links = screen.getAllByRole("link");
        expect(links.map((link) => link.getAttribute("href"))).toEqual(["/adr-reviews/adr-1", "/adr-reviews/adr-2"]);
        expect(screen.getByText("Awaiting review")).toBeInTheDocument();
        expect(screen.getByText("Dismissed")).toBeInTheDocument();
    });

    it("says so when the patient has no cases and handles a failure", async () => {
        mocks.fetchADRReviewQueue.mockResolvedValueOnce([]);
        const view = render(<PatientADRPanel patientId="patient-1" />);
        expect(await screen.findByText("No ADR cases")).toBeInTheDocument();
        view.unmount();
        mocks.fetchADRReviewQueue.mockRejectedValueOnce(new Error("private diagnostic"));
        render(<PatientADRPanel patientId="patient-1" />);
        expect(await screen.findByText("Unable to load ADR cases")).toBeInTheDocument();
        expect(screen.queryByText("private diagnostic")).not.toBeInTheDocument();
    });
});
