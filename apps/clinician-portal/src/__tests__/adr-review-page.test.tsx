import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MedWatchPage from "@/app/(dashboard)/medwatch/page";

const { fetchADRReviewQueueMock, reviewADRAssessmentMock } = vi.hoisted(() => ({
    fetchADRReviewQueueMock: vi.fn(),
    reviewADRAssessmentMock: vi.fn(),
}));

vi.mock("@/services/clinicians", () => ({
    fetchADRReviewQueue: fetchADRReviewQueueMock,
    reviewADRAssessment: reviewADRAssessmentMock,
}));

const assessment = {
    id: "adr-1",
    patientId: "patient-1",
    patientFirstName: "Maya",
    patientLastName: "Patel",
    symptomReportId: "symptom-1",
    symptom: "dizziness",
    severity: 2,
    onset: "a few hours after starting the inhaler",
    symptomCreatedAt: "2026-10-02T09:52:00Z",
    suspectMedicationId: "medication-1",
    suspectMedicationName: "fluticasone/salmeterol inhaler",
    naranjoScore: 3,
    causality: "Possible",
    naranjoAnswers: {
        event_after_drug: "yes",
        improved_on_dechallenge: "yes",
    },
    naranjoAssessment: {
        missing_questions: ["alternative_causes"],
    },
    evidence: [
        {
            question: "event_after_drug",
            answer: "yes",
            evidence: "I became dizzy a few hours after starting the inhaler.",
        },
        {
            question: "improved_on_dechallenge",
            answer: "yes",
            evidence: "The dizziness improved after I stopped using it.",
        },
    ],
    status: "draft",
    createdAt: "2026-10-02T09:53:00Z",
};

describe("ADR review queue", () => {
    beforeEach(() => {
        fetchADRReviewQueueMock.mockReset();
        reviewADRAssessmentMock.mockReset();
    });

    it("shows the Naranjo score and patient-grounded evidence", async () => {
        fetchADRReviewQueueMock.mockResolvedValue([assessment]);

        render(<MedWatchPage />);

        expect(await screen.findByText("Maya Patel")).toBeInTheDocument();
        expect(screen.getByText("Naranjo 3")).toBeInTheDocument();
        expect(screen.getByText("Possible")).toBeInTheDocument();
        expect(screen.getByText("dizziness")).toBeInTheDocument();
        expect(screen.getByText("fluticasone/salmeterol inhaler")).toBeInTheDocument();
        expect(screen.getByText("Event followed medication")).toBeInTheDocument();
        expect(screen.getByText(/I became dizzy a few hours/)).toBeInTheDocument();
        expect(screen.getByText("Alternative causes")).toBeInTheDocument();
        expect(screen.getByRole("link", { name: /open patient record/i })).toHaveAttribute(
            "href",
            "/patients/patient-1",
        );
    });

    it("shows a truthful empty state when no ADR review is pending", async () => {
        fetchADRReviewQueueMock.mockResolvedValue([]);

        render(<MedWatchPage />);

        expect(await screen.findByText("No ADR assessments awaiting review")).toBeInTheDocument();
        expect(screen.queryByText("No MedWatch drafts")).not.toBeInTheDocument();
    });

    it("offers a retry when the queue request fails", async () => {
        fetchADRReviewQueueMock.mockRejectedValue(new Error("Service unavailable"));

        render(<MedWatchPage />);

        expect(await screen.findByText("Unable to load ADR reviews")).toBeInTheDocument();
        expect(screen.getByText("Service unavailable")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
    });

    it("marks an assessment reviewed and refreshes the pending queue", async () => {
        fetchADRReviewQueueMock.mockResolvedValueOnce([assessment]).mockResolvedValueOnce([]);
        reviewADRAssessmentMock.mockResolvedValue({ status: "reviewed" });

        render(<MedWatchPage />);

        fireEvent.click(await screen.findByRole("button", { name: "Mark reviewed" }));
        fireEvent.change(screen.getByLabelText(/review note/i), {
            target: { value: "Evidence reviewed with the medication history." },
        });
        fireEvent.click(screen.getByRole("button", { name: "Mark reviewed" }));

        await waitFor(() =>
            expect(reviewADRAssessmentMock).toHaveBeenCalledWith("adr-1", {
                action: "mark_reviewed",
                note: "Evidence reviewed with the medication history.",
                requestedInformation: [],
            }),
        );
        expect(await screen.findByText("ADR review saved and audited.")).toBeInTheDocument();
        expect(await screen.findByText("No ADR assessments awaiting review")).toBeInTheDocument();
    });

    it("requires a note and sends selected missing questions for information requests", async () => {
        fetchADRReviewQueueMock.mockResolvedValue([assessment]);
        reviewADRAssessmentMock.mockResolvedValue({ status: "draft" });

        render(<MedWatchPage />);

        fireEvent.click(await screen.findByRole("button", { name: "Request information" }));
        const submit = screen.getByRole("button", { name: "Request information" });
        expect(submit).toBeDisabled();
        fireEvent.change(screen.getByLabelText(/review note/i), {
            target: { value: "Please clarify other possible causes." },
        });
        fireEvent.click(submit);

        await waitFor(() =>
            expect(reviewADRAssessmentMock).toHaveBeenCalledWith("adr-1", {
                action: "request_information",
                note: "Please clarify other possible causes.",
                requestedInformation: ["alternative_causes"],
            }),
        );
    });
});
