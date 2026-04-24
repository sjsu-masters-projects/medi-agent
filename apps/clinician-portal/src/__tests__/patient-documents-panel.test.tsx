import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { PatientDocumentsPanel } from "@/components/features/patient-documents-panel";
import {
    approveDocumentReview,
    rejectDocumentReview,
} from "@/services/clinicians";

vi.mock("@/services/clinicians", () => ({
    approveDocumentReview: vi.fn(),
    rejectDocumentReview: vi.fn(),
}));

vi.mock("@/components/features/document-summary", () => ({
    DocumentSummary: ({ summaryText }: { summaryText: string }) => (
        <div>{summaryText}</div>
    ),
}));

describe("PatientDocumentsPanel", () => {
    beforeEach(() => {
        vi.mocked(approveDocumentReview).mockReset();
        vi.mocked(rejectDocumentReview).mockReset();
    });

    it("renders review metadata for reviewed patient uploads", () => {
        render(
            <PatientDocumentsPanel
                documents={[
                    {
                        id: "doc-1",
                        fileName: "lab.pdf",
                        documentType: "lab_report",
                        parseStatus: "completed",
                        aiSummary: "Summary text",
                        createdAt: "2026-04-21T10:00:00Z",
                        uploadedByRole: "patient",
                        reviewStatus: "rejected",
                        reviewedAt: "2026-04-22T09:00:00Z",
                        reviewNote: "Looks valid",
                        reviewer: {
                            id: "clinician-1",
                            firstName: "Mina",
                            lastName: "Shah",
                        },
                    },
                ]}
                onRefresh={vi.fn()}
                patientId="patient-1"
            />,
        );

        expect(screen.getByText("lab.pdf")).toBeInTheDocument();
        expect(screen.getByText(/Review rejected/i)).toBeInTheDocument();
        expect(screen.getByText(/by Mina Shah/i)).toBeInTheDocument();
        expect(screen.getByText(/Review note: Looks valid/i)).toBeInTheDocument();
    });

    it("approves pending patient uploads and refreshes the deep dive", async () => {
        const onRefresh = vi.fn();
        vi.mocked(approveDocumentReview).mockResolvedValue({
            status: "reviewed",
            document_id: "doc-2",
            patient_id: "patient-2",
            review_status: "approved",
            reviewed_by: "clinician-1",
            reviewed_at: "2026-04-23T10:00:00Z",
            review_note: undefined,
        });

        render(
            <PatientDocumentsPanel
                documents={[
                    {
                        id: "doc-2",
                        fileName: "upload.pdf",
                        documentType: "other",
                        parseStatus: "pending",
                        createdAt: "2026-04-21T10:00:00Z",
                        uploadedByRole: "patient",
                        reviewStatus: "pending",
                    },
                ]}
                onRefresh={onRefresh}
                patientId="patient-2"
            />,
        );

        fireEvent.click(screen.getByRole("button", { name: "Approve" }));

        await waitFor(() =>
            expect(approveDocumentReview).toHaveBeenCalledWith("patient-2", "doc-2"),
        );
        await waitFor(() => expect(onRefresh).toHaveBeenCalled());
    });

    it("rejects pending patient uploads with a note and refreshes the deep dive", async () => {
        const onRefresh = vi.fn();
        vi.mocked(rejectDocumentReview).mockResolvedValue({
            status: "reviewed",
            document_id: "doc-3",
            patient_id: "patient-3",
            review_status: "rejected",
            reviewed_by: "clinician-1",
            reviewed_at: "2026-04-23T10:00:00Z",
            review_note: "Unreadable image",
        });

        render(
            <PatientDocumentsPanel
                documents={[
                    {
                        id: "doc-3",
                        fileName: "image.png",
                        documentType: "other",
                        parseStatus: "completed",
                        createdAt: "2026-04-21T10:00:00Z",
                        uploadedByRole: "patient",
                        reviewStatus: "pending",
                    },
                ]}
                onRefresh={onRefresh}
                patientId="patient-3"
            />,
        );

        fireEvent.click(screen.getByRole("button", { name: "Reject" }));
        fireEvent.change(screen.getByRole("textbox", { name: /review note/i }), {
            target: { value: "Unreadable image" },
        });
        fireEvent.click(screen.getByRole("button", { name: /Confirm rejection/i }));

        await waitFor(() =>
            expect(rejectDocumentReview).toHaveBeenCalledWith(
                "patient-3",
                "doc-3",
                "Unreadable image",
            ),
        );
        await waitFor(() => expect(onRefresh).toHaveBeenCalled());
    });
});
