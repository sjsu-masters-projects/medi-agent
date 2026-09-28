import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CarePlanPanel } from "@/components/features/care-plan-panel";
import {
    fetchClinicianCarePlan,
    fetchClinicianCarePlanGeneration,
    fetchClinicianDocumentSource,
    retryClinicianCarePlanGeneration,
} from "@/services/clinicians";

vi.mock("@/services/clinicians", () => ({
    approveClinicianCarePlan: vi.fn(),
    fetchClinicianCarePlan: vi.fn(),
    fetchClinicianCarePlanGeneration: vi.fn(),
    fetchClinicianDocumentSource: vi.fn(),
    retryClinicianCarePlanGeneration: vi.fn(),
    updateClinicianCarePlan: vi.fn(),
}));

vi.mock("@/components/features/document-source-viewer", () => ({
    DocumentSourceViewer: ({ fileName }: { fileName: string }) => <p>Preview: {fileName}</p>,
}));

describe("CarePlanPanel", () => {
    beforeEach(() => {
        vi.mocked(fetchClinicianCarePlan).mockReset();
        vi.mocked(fetchClinicianCarePlanGeneration).mockReset();
        vi.mocked(fetchClinicianDocumentSource).mockReset();
        vi.mocked(retryClinicianCarePlanGeneration).mockReset();
    });

    it("shows a failed automatic draft and retries the same evidence", async () => {
        vi.mocked(fetchClinicianCarePlan).mockResolvedValue(null);
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue({
            id: "generation-1",
            patient_id: "patient-1",
            status: "failed",
            attempts: 3,
            requested_at: "2026-09-28T10:00:00Z",
            failure_code: "provider_unavailable",
        });
        vi.mocked(retryClinicianCarePlanGeneration).mockResolvedValue({ status: "pending" });

        render(<CarePlanPanel patientId="patient-1" />);

        expect(await screen.findByText("Automatic evidence draft failed")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Retry generation" }));
        await waitFor(() =>
            expect(retryClinicianCarePlanGeneration).toHaveBeenCalledWith("patient-1"),
        );
    });

    it("opens an item source with the existing protected document route", async () => {
        vi.mocked(fetchClinicianCarePlan).mockResolvedValue({
            id: "plan-1", patient_id: "patient-1", version_number: 1, status: "draft", items: [{
                id: "item-1", source_fact_id: "fact-1", category: "movement", title: "Walk", instructions: "Walk for 20 minutes.", frequency: "3x per week", schedule: {}, medication: {}, confidence_score: 0.9, uncertainty: [], conflict: {}, is_removed: false,
                source: { document_id: "document-1", excerpt: "Walk for 20 minutes.", location: { page: 2 } },
            }],
        });
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue(null);
        vi.mocked(fetchClinicianDocumentSource).mockResolvedValue({
            file_name: "source.pdf", file_url: "https://signed.test/original", mime_type: "application/pdf", preview_status: "ready", preview_url: "https://signed.test/preview", preview_mime_type: "application/pdf",
        });

        render(<CarePlanPanel patientId="patient-1" />);

        fireEvent.click(await screen.findByRole("button", { name: "Review source beside item" }));
        await waitFor(() => expect(fetchClinicianDocumentSource).toHaveBeenCalledWith("patient-1", "document-1"));
        expect(await screen.findByText("Preview: source.pdf")).toBeInTheDocument();
    });
});
