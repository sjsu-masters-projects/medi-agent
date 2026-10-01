import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CarePlanPanel } from "@/components/features/care-plan-panel";
import {
    fetchClinicianCarePlanReviewContext,
    fetchClinicianCarePlanGeneration,
    fetchClinicianDocumentSource,
    retryClinicianCarePlanGeneration,
    updateClinicianCarePlan,
} from "@/services/clinicians";

vi.mock("@/services/clinicians", () => ({
    approveClinicianCarePlan: vi.fn(),
    fetchClinicianCarePlanReviewContext: vi.fn(),
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
        vi.mocked(fetchClinicianCarePlanReviewContext).mockReset();
        vi.mocked(fetchClinicianCarePlanGeneration).mockReset();
        vi.mocked(fetchClinicianDocumentSource).mockReset();
        vi.mocked(retryClinicianCarePlanGeneration).mockReset();
        vi.mocked(updateClinicianCarePlan).mockReset();
    });

    it("shows a failed automatic draft and retries the same evidence", async () => {
        vi.mocked(fetchClinicianCarePlanReviewContext).mockResolvedValue({ latest: null, active: null, patient_locale: "en-US", active_medications: [] });
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
        vi.mocked(fetchClinicianCarePlanReviewContext).mockResolvedValue({ latest: {
            id: "plan-1", patient_id: "patient-1", version_number: 1, status: "draft", items: [{
                id: "item-1", source_fact_id: "fact-1", category: "movement", title: "Walk", instructions: "Walk for 20 minutes.", frequency: "3x per week", schedule: {}, medication: {}, confidence_score: 0.9, uncertainty: [], conflict: {}, is_removed: false,
                source: { document_id: "document-1", file_name: "source.pdf", excerpt: "Walk for 20 minutes.", location: { page: 2 } },
                sources: [
                    { document_id: "document-1", file_name: "source.pdf", excerpt: "Walk for 20 minutes.", location: { page: 2 } },
                    { document_id: "document-1", file_name: "source.pdf", excerpt: "Walk for 20 minutes.", location: { page: 2 } },
                    { document_id: "document-1", file_name: "source.pdf", excerpt: "Walk for 20", location: { page: 2 } },
                    { document_id: "document-2", file_name: "follow-up.pdf", excerpt: "Continue walking.", location: { page: 1 } },
                ],
            }],
        }, active: null, patient_locale: "en-US", active_medications: [] });
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue(null);
        vi.mocked(fetchClinicianDocumentSource).mockResolvedValue({
            file_name: "source.pdf", file_url: "https://signed.test/original", mime_type: "application/pdf", preview_status: "ready", preview_url: "https://signed.test/preview", preview_mime_type: "application/pdf",
        });

        render(<CarePlanPanel patientId="patient-1" />);

        expect(await screen.findAllByRole("button", { name: "Review source: source.pdf" })).toHaveLength(1);
        fireEvent.click(await screen.findByRole("button", { name: "Review source: source.pdf" }));
        await waitFor(() => expect(fetchClinicianDocumentSource).toHaveBeenCalledWith("patient-1", "document-1"));
        expect(await screen.findByText("Preview: source.pdf")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Review source: follow-up.pdf" }));
        await waitFor(() => expect(fetchClinicianDocumentSource).toHaveBeenCalledWith("patient-1", "document-2"));
    });

    it("shows the active plan beside a new draft and its source documents", async () => {
        vi.mocked(fetchClinicianCarePlanReviewContext).mockResolvedValue({
            patient_locale: "en-US",
            active_medications: [],
            active: {
                id: "plan-1", patient_id: "patient-1", version_number: 1, status: "approved",
                items: [{
                    id: "old-1", source_fact_id: "fact-1", category: "movement", title: "Walk",
                    instructions: "Walk 20 minutes", frequency: "daily", schedule: {}, medication: {},
                    uncertainty: [], conflict: {}, is_removed: false,
                }],
            },
            latest: {
                id: "plan-2", patient_id: "patient-1", version_number: 2, status: "draft",
                items: [{
                    id: "new-1", source_fact_id: "fact-2", category: "hydration", title: "Drink water",
                    instructions: "Drink water", frequency: "daily", schedule: {}, medication: {},
                    uncertainty: [], conflict: {}, is_removed: false,
                    source: { document_id: "document-2", file_name: "follow-up.pdf", excerpt: "Drink water", location: { page: 1 } },
                }],
            },
        });
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue(null);

        render(<CarePlanPanel patientId="patient-1" />);

        expect(await screen.findByText(/Approved version 1 remains active in Today/)).toBeInTheDocument();
        expect(screen.getByText("follow-up.pdf")).toBeInTheDocument();
        expect(screen.getByText("hydration · new evidence")).toBeInTheDocument();
        expect(screen.getByText(/not an exact Today preview/)).toBeInTheDocument();
    });

    it("does not allow approval while the clinician has unsaved changes", async () => {
        vi.mocked(fetchClinicianCarePlanReviewContext).mockResolvedValue({
            patient_locale: "en-US", active_medications: [], active: null,
            latest: {
                id: "plan-1", patient_id: "patient-1", version_number: 1, status: "draft",
                items: [{
                    id: "item-1", source_fact_id: "fact-1", category: "movement", title: "Walk",
                    instructions: "Walk 20 minutes", frequency: "daily", schedule: {}, medication: {},
                    uncertainty: [], conflict: {}, is_removed: false, reviewed_locale: "en-US",
                }],
            },
        });
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue(null);

        render(<CarePlanPanel patientId="patient-1" />);

        const approve = await screen.findByRole("button", { name: "Approve and publish plan" });
        fireEvent.change(screen.getByPlaceholderText("Record the basis for your approval."), { target: { value: "Verified" } });
        expect(approve).toBeEnabled();
        fireEvent.change(screen.getByDisplayValue("Walk 20 minutes"), { target: { value: "Walk 30 minutes" } });
        expect(approve).toBeDisabled();
        expect(screen.getByText(/Save your edits before approving/)).toBeInTheDocument();
    });

    it("shows a load error instead of incorrectly reporting that generation is waiting", async () => {
        vi.mocked(fetchClinicianCarePlanReviewContext).mockRejectedValue(new Error("Request failed (500)"));
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue(null);

        render(<CarePlanPanel patientId="patient-1" />);

        expect(await screen.findByRole("alert")).toHaveTextContent("Request failed (500)");
        expect(screen.queryByText("Waiting for an automatic evidence draft")).not.toBeInTheDocument();
    });

    it("blocks approval until locale wording and a medication projection are reviewed", async () => {
        vi.mocked(fetchClinicianCarePlanReviewContext).mockResolvedValue({
            patient_locale: "en-US", active_medications: [{ id: "med-1", name: "Metformin", dosage: "500 mg", frequency: "daily", route: "oral" }], active: null,
            latest: {
                id: "plan-1", patient_id: "patient-1", version_number: 1, status: "draft",
                items: [{
                    id: "item-1", source_fact_id: "fact-1", category: "medication", title: "Metformina 500 mg",
                    instructions: "Tome una tableta al día", frequency: "una vez al día", schedule: {},
                    medication: { name: "Metformin", dosage: "500 mg", frequency: "daily", route: "oral" },
                    uncertainty: [], conflict: {}, is_removed: false,
                }],
            },
        });
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue(null);

        render(<CarePlanPanel patientId="patient-1" />);

        const approve = await screen.findByRole("button", { name: "Approve and publish plan" });
        fireEvent.change(screen.getByPlaceholderText("Record the basis for your approval."), { target: { value: "Reviewed" } });
        expect(approve).toBeDisabled();
        expect(screen.getByText(/final patient-facing wording/)).toBeInTheDocument();
        expect(screen.getByText(/Choose whether each medication/)).toBeInTheDocument();
        expect(screen.getByRole("option", { name: /Update Metformin/ })).toBeInTheDocument();
        fireEvent.change(screen.getByLabelText("Publication decision"), { target: { value: "update:med-1" } });
        fireEvent.click(screen.getByRole("checkbox", { name: /I checked this final title/ }));
        expect(approve).toBeDisabled();
        expect(screen.getByText(/Save your edits before approving/)).toBeInTheDocument();
    });
});
