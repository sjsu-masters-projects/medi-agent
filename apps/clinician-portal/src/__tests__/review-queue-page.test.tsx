import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Provider } from "react-redux";
import { afterEach, describe, expect, it, vi, beforeEach } from "vitest";
import ReviewQueuePage from "@/app/(dashboard)/review-queue/page";
import {
    approveDocumentReview,
    fetchDocumentReviewQueue,
    rejectDocumentReview,
} from "@/services/clinicians";
import { store } from "@/store/store";
import { simulateNonUsDefaultLocale } from "./fixtures/locale";

vi.mock("@/services/clinicians", () => ({
    fetchDocumentReviewQueue: vi.fn(),
    approveDocumentReview: vi.fn(),
    rejectDocumentReview: vi.fn(),
}));

describe("ReviewQueuePage", () => {
    beforeEach(() => {
        vi.mocked(fetchDocumentReviewQueue).mockReset();
        vi.mocked(approveDocumentReview).mockReset();
        vi.mocked(rejectDocumentReview).mockReset();
    });

    it("renders pending queue items and approve action", async () => {
        vi.mocked(fetchDocumentReviewQueue).mockResolvedValue([
            {
                id: "doc-1",
                patientId: "patient-1",
                patientFirstName: "Ana",
                patientLastName: "Lopez",
                fileName: "upload.pdf",
                documentType: "lab_report",
                parseStatus: "pending",
                aiSummary: "Lab summary",
                sourceClinic: "North Clinic",
                createdAt: "2026-04-22T10:00:00Z",
                uploadedByRole: "patient",
                reviewStatus: "pending",
            },
        ]);
        vi.mocked(approveDocumentReview).mockResolvedValue({
            status: "reviewed",
            document_id: "doc-1",
            patient_id: "patient-1",
            review_status: "approved",
            reviewed_by: "clinician-1",
            reviewed_at: "2026-04-23T10:00:00Z",
            review_note: undefined,
        });

        render(
            <Provider store={store}>
                <ReviewQueuePage />
            </Provider>,
        );

        expect(await screen.findByText("upload.pdf")).toBeInTheDocument();
        expect(screen.getByRole("link", { name: "Review document" })).toHaveAttribute("href", "/patients/patient-1?tab=documents#document-doc-1");
        fireEvent.click(screen.getByRole("button", { name: "Approve" }));

        await waitFor(() =>
            expect(approveDocumentReview).toHaveBeenCalledWith("patient-1", "doc-1"),
        );
        await waitFor(() =>
            expect(screen.queryByText("upload.pdf")).not.toBeInTheDocument(),
        );
    });

    it("supports rejecting a queue item with a note", async () => {
        vi.mocked(fetchDocumentReviewQueue).mockResolvedValue([
            {
                id: "doc-2",
                patientId: "patient-2",
                patientFirstName: "Luis",
                patientLastName: "Garcia",
                fileName: "image.png",
                documentType: "other",
                parseStatus: "completed",
                aiSummary: undefined,
                sourceClinic: undefined,
                createdAt: "2026-04-22T10:00:00Z",
                uploadedByRole: "patient",
                reviewStatus: "pending",
            },
        ]);
        vi.mocked(rejectDocumentReview).mockResolvedValue({
            status: "reviewed",
            document_id: "doc-2",
            patient_id: "patient-2",
            review_status: "rejected",
            reviewed_by: "clinician-1",
            reviewed_at: "2026-04-23T11:00:00Z",
            review_note: "Unreadable image",
        });

        render(
            <Provider store={store}>
                <ReviewQueuePage />
            </Provider>,
        );

        expect(await screen.findByText("image.png")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Reject" }));
        fireEvent.change(screen.getByRole("textbox", { name: /review note/i }), {
            target: { value: "Unreadable image" },
        });
        fireEvent.click(screen.getByRole("button", { name: /Confirm rejection/i }));

        await waitFor(() =>
            expect(rejectDocumentReview).toHaveBeenCalledWith(
                "patient-2",
                "doc-2",
                "Unreadable image",
            ),
        );
        await waitFor(() =>
            expect(screen.queryByText("image.png")).not.toBeInTheDocument(),
        );
    });

    describe("upload dates", () => {
        afterEach(() => vi.restoreAllMocks());

        it("formats the upload time as en-US even when the default locale is not US", async () => {
            simulateNonUsDefaultLocale();
            vi.mocked(fetchDocumentReviewQueue).mockResolvedValue([
                {
                    id: "doc-date",
                    patientId: "patient-date",
                    patientFirstName: "Ana",
                    patientLastName: "Lopez",
                    fileName: "dated.pdf",
                    documentType: "other",
                    parseStatus: "completed",
                    createdAt: "2026-10-12T12:00:00Z",
                    uploadedByRole: "patient",
                    reviewStatus: "pending",
                },
            ]);

            render(
                <Provider store={store}>
                    <ReviewQueuePage />
                </Provider>,
            );

            expect(await screen.findByText("dated.pdf")).toBeInTheDocument();
            const time = document.querySelector('time[datetime="2026-10-12T12:00:00Z"]');
            expect(time?.textContent).toMatch(/^10\/12\/2026, /);
            expect(time?.textContent).not.toContain("12/10/2026");
        });
    });
});
