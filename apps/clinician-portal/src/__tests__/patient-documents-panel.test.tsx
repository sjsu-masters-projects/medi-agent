import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { PatientDocumentsPanel } from "@/components/features/patient-documents-panel";
import {
    approveDocumentReview,
    fetchClinicianDocumentSource,
    rejectDocumentReview,
    retryClinicianDocumentSummary,
} from "@/services/clinicians";

vi.mock("@/services/clinicians", () => ({
    approveDocumentReview: vi.fn(),
    fetchClinicianDocumentSource: vi.fn(),
    rejectDocumentReview: vi.fn(),
    retryClinicianDocumentIngestion: vi.fn(),
    retryClinicianDocumentSummary: vi.fn(),
}));

vi.mock("@/components/features/document-summary", () => ({
    DocumentSummary: ({ summaryText }: { summaryText: string }) => (
        <div>{summaryText}</div>
    ),
}));

vi.mock("@/components/features/document-source-viewer", () => ({
    DocumentSourceViewer: ({ sourceUrl }: { sourceUrl?: string | null }) => (
        <div data-testid="source-viewer">{sourceUrl}</div>
    ),
}));

describe("PatientDocumentsPanel", () => {
    beforeEach(() => {
        vi.mocked(approveDocumentReview).mockReset();
        vi.mocked(fetchClinicianDocumentSource).mockReset();
        vi.mocked(rejectDocumentReview).mockReset();
        vi.mocked(retryClinicianDocumentSummary).mockReset();
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

    it("loads a fresh, authorized source URL only after the clinician opens a document", async () => {
        vi.mocked(fetchClinicianDocumentSource).mockResolvedValue({
            file_name: "lab.pdf",
            file_url: "https://example.test/signed-lab.pdf",
            mime_type: "application/pdf",
            preview_status: "not_required",
        });

        render(
            <PatientDocumentsPanel
                documents={[
                    {
                        id: "doc-source",
                        fileName: "lab.pdf",
                        documentType: "lab_report",
                        parseStatus: "completed",
                        createdAt: "2026-04-21T10:00:00Z",
                        uploadedByRole: "patient",
                        reviewStatus: "approved",
                    },
                ]}
                onRefresh={vi.fn()}
                patientId="patient-source"
            />,
        );

        fireEvent.click(screen.getByRole("button", { name: /open source document/i }));

        await waitFor(() =>
            expect(fetchClinicianDocumentSource).toHaveBeenCalledWith("patient-source", "doc-source"),
        );
        expect(await screen.findByTestId("source-viewer")).toHaveTextContent("signed-lab.pdf");
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

    it("offers a retry when the patient explanation is unavailable", async () => {
        const onRefresh = vi.fn();
        vi.mocked(retryClinicianDocumentSummary).mockResolvedValue({
            id: "doc-1",
            fileName: "lab.pdf",
            documentType: "lab_report",
            parseStatus: "completed",
            summaryStatus: "pending",
            createdAt: "2026-04-21T10:00:00Z",
            uploadedByRole: "patient",
        });

        render(
            <PatientDocumentsPanel
                documents={[
                    {
                        id: "doc-1",
                        fileName: "lab.pdf",
                        documentType: "lab_report",
                        parseStatus: "completed",
                        summaryStatus: "failed",
                        summaryFailureCode: "provider_unavailable",
                        createdAt: "2026-04-21T10:00:00Z",
                        uploadedByRole: "patient",
                    },
                ]}
                onRefresh={onRefresh}
                patientId="patient-1"
            />,
        );

        // The clinician is told the clinical record is intact, not just that a box is empty.
        expect(
            screen.getByText(/Extraction and review candidates are unaffected/i),
        ).toBeInTheDocument();

        fireEvent.click(
            screen.getByRole("button", { name: /retry patient explanation/i }),
        );

        await waitFor(() => {
            expect(retryClinicianDocumentSummary).toHaveBeenCalledWith(
                "patient-1",
                "doc-1",
            );
        });
        expect(onRefresh).toHaveBeenCalled();
    });

    it("does not offer a retry for a document with nothing to explain", () => {
        render(
            <PatientDocumentsPanel
                documents={[
                    {
                        id: "doc-2",
                        fileName: "blank.pdf",
                        documentType: "lab_report",
                        parseStatus: "completed",
                        summaryStatus: "not_required",
                        createdAt: "2026-04-21T10:00:00Z",
                        uploadedByRole: "patient",
                    },
                ]}
                onRefresh={vi.fn()}
                patientId="patient-1"
            />,
        );

        expect(
            screen.getByText(/needs a patient explanation/i),
        ).toBeInTheDocument();
        expect(
            screen.queryByRole("button", { name: /retry patient explanation/i }),
        ).not.toBeInTheDocument();
    });

    it("shows an automatic retry state without offering a duplicate retry", () => {
        render(
            <PatientDocumentsPanel
                documents={[
                    {
                        id: "doc-retrying",
                        fileName: "follow-up.tiff",
                        documentType: "other",
                        parseStatus: "completed",
                        summaryStatus: "pending",
                        summaryFailureCode: "provider_unavailable",
                        summaryAttempts: 1,
                        summaryNextAttemptAt: "2026-04-21T10:02:00Z",
                        createdAt: "2026-04-21T10:00:00Z",
                        uploadedByRole: "clinician",
                    },
                ]}
                onRefresh={vi.fn()}
                patientId="patient-1"
            />,
        );

        expect(screen.getByText(/will retry automatically \(attempt 1 of 3\)/i)).toBeInTheDocument();
        expect(
            screen.queryByRole("button", { name: /retry patient explanation/i }),
        ).not.toBeInTheDocument();
    });
});
