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
    DocumentSourceViewer: ({ fileName, initialPage }: { fileName: string; initialPage?: number }) => <p>Preview: {fileName} (page {initialPage})</p>,
}));

describe("CarePlanPanel", () => {
    it("stages imported-record exclusions without changing approved carried items or publishing", async () => {
        const base = {category: "monitoring", title: "Imported record", instructions: "", frequency: "", schedule: {}, medication: {}, uncertainty: [], conflict: {}, is_removed: false, imported_evidence: true};
        const historical = {...base, id: "history", source_fact_id: "old-import"};
        const carried = {...base, id: "carried", source_fact_id: "approved-fact", title: "Approved carried instruction"};
        const plan = {id: "v2", patient_id: "p", version_number: 2, status: "draft" as const, items: [historical, carried]};
        vi.mocked(fetchClinicianCarePlanReviewContext).mockResolvedValue({latest: plan, active: {...plan, id: "v1", version_number: 1, status: "approved", items: [carried]}, patient_locale: "en-US", active_medications: []});
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue(null);
        vi.mocked(updateClinicianCarePlan).mockResolvedValue({...plan, items: [{...historical, is_removed: true}, carried]});
        render(<CarePlanPanel patientId="p" />);
        fireEvent.click(await screen.findByRole("button", {name: "Exclude imported proposals from this draft"}));
        expect(updateClinicianCarePlan).not.toHaveBeenCalled();
        expect(screen.getByRole("checkbox", {name: /Show removed items/})).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", {name: "Save review"}));
        await waitFor(() => expect(updateClinicianCarePlan).toHaveBeenCalledWith("p", "v2", [expect.objectContaining({id: "history", is_removed: true}), expect.objectContaining({id: "carried", is_removed: false})]));
    });
    it("requires an explicit overlap choice and preserves the removed source row on save", async () => {
        const first = {id: "one", category: "movement", title: "Walk", instructions: "Walk 20 minutes", frequency: "daily", schedule: {}, medication: {}, uncertainty: [], conflict: {}, is_removed: false, reviewed_locale: "en-US"};
        const second = {...first, id: "two", title: "Walking activity"};
        const plan = {id: "v2", patient_id: "p", version_number: 2, status: "draft" as const, items: [first, second]};
        vi.mocked(fetchClinicianCarePlanReviewContext).mockResolvedValue({latest: plan, active: null, patient_locale: "en-US", active_medications: []});
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue(null);
        vi.mocked(updateClinicianCarePlan).mockResolvedValue({...plan, items: [first, {...second, is_removed: true}]});
        render(<CarePlanPanel patientId="p" />);
        const buttons = await screen.findAllByRole("button", {name: "Keep this proposal; remove its overlaps"});
        fireEvent.change(screen.getByPlaceholderText("Record the basis for your approval."), {target: {value: "Reviewed"}});
        expect(screen.getByRole("button", {name: "Approve and publish plan"})).toBeDisabled();
        fireEvent.click(buttons[0]);
        expect(screen.queryByText(/2 items overlap/)).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", {name: "Save review"}));
        await waitFor(() => expect(updateClinicianCarePlan).toHaveBeenCalledWith("p", "v2", [expect.objectContaining({id: "one", is_removed: false}), expect.objectContaining({id: "two", is_removed: true})]));
    });
    it("requires replacing an abbreviated source heading even after confirmation", async () => {
        const warning = "Source title exceeds the draft limit; replace it after reviewing the full evidence.";
        vi.mocked(fetchClinicianCarePlanReviewContext).mockResolvedValue({latest: {
            id: "plan-1", patient_id: "patient-1", version_number: 1, status: "draft", items: [{
                id: "item-1", category: "movement", title: "Abbreviated heading…", instructions: "Full source instruction", frequency: "daily",
                schedule: {}, medication: {}, uncertainty: [warning], conflict: {}, is_removed: false, blocker_reason: warning,
            }],
        }, active: null, patient_locale: "en-US", active_medications: []});
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue(null);
        render(<CarePlanPanel patientId="patient-1" />);
        fireEvent.click(await screen.findByRole("checkbox", {name: "Confirm after review"}));
        expect(screen.getByText(/1 unresolved item/)).toBeInTheDocument();
        expect(screen.getByRole("button", {name: "Approve and publish plan"})).toBeDisabled();
        fireEvent.change(screen.getByRole("textbox", {name: "Title"}), {target: {value: "Reviewed activity"}});
        expect(screen.queryByText(/1 unresolved item/)).not.toBeInTheDocument();
    });
    beforeEach(() => {
        vi.mocked(fetchClinicianCarePlanReviewContext).mockReset();
        vi.mocked(fetchClinicianCarePlanGeneration).mockReset();
        vi.mocked(fetchClinicianDocumentSource).mockReset();
        vi.mocked(retryClinicianCarePlanGeneration).mockReset();
        vi.mocked(updateClinicianCarePlan).mockReset();
    });

    it("keeps missing evidence blocked after confirmation and allows removal without invented wording", async () => {
        const incomplete = { id: "item-1", source_fact_id: "fact-1", category: "monitoring" as const,
            title: "Record the activity", instructions: "", frequency: "", schedule: {}, medication: {},
            uncertainty: [], conflict: {}, is_removed: false, blocker_reason: "Missing source wording",
            reviewed_locale: "en-US" };
        const plan = { id: "plan-1", patient_id: "patient-1", version_number: 1, status: "draft" as const, items: [incomplete] };
        vi.mocked(fetchClinicianCarePlanReviewContext).mockResolvedValue({latest: plan, active: null, patient_locale: "en-US", active_medications: []});
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue(null);
        vi.mocked(updateClinicianCarePlan).mockResolvedValue({...plan, items: [{...incomplete, is_removed: true, blocker_reason: null}]});
        render(<CarePlanPanel patientId="patient-1" />);
        const confirm = await screen.findByRole("checkbox", {name: "Confirm after review"});
        fireEvent.click(confirm);
        expect(screen.getByText(/1 unresolved item/)).toBeInTheDocument();
        fireEvent.click(screen.getByRole("checkbox", {name: "Remove from this version"}));
        fireEvent.click(screen.getByRole("button", {name: "Save review"}));
        await waitFor(() => expect(updateClinicianCarePlan).toHaveBeenCalledWith("patient-1", "plan-1", [expect.objectContaining({instructions: "", frequency: "", is_removed: true})]));
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

    it.each(["pending", "failed"] as const)("shows %s revision state alongside the immutable active plan", async (status) => {
        vi.mocked(fetchClinicianCarePlanReviewContext).mockResolvedValue({ latest: { id: "plan-1", patient_id: "patient-1", version_number: 1, status: "approved", items: [] }, active: null, patient_locale: "en-US", active_medications: [] });
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue({ id: "request-1", patient_id: "patient-1", status, attempts: 0, requested_at: "2026-10-01T23:13:00Z" });
        render(<CarePlanPanel patientId="patient-1" />);
        expect(await screen.findByText(/Approved version 1 remains active/)).toBeInTheDocument();
        if (status === "failed") expect(screen.getByRole("button", { name: "Retry generation" })).toBeInTheDocument();
        else expect(screen.getByText(/five-minute evidence quiet window/)).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Approve and publish plan" })).not.toBeInTheDocument();
    });

    it.each(["pending", "processing", "retry", "failed"] as const)("blocks a partial draft with %s generation even after all visible items are reviewed", async (status) => {
        vi.mocked(fetchClinicianCarePlanReviewContext).mockResolvedValue({
            latest: { id: "plan-2", patient_id: "patient-1", version_number: 2, status: "draft", items: [{
                id: "item-1", source_fact_id: "fact-1", category: "movement", title: "Walk", instructions: "Walk 20 minutes", frequency: "daily", schedule: {}, medication: {}, uncertainty: [], conflict: {}, is_removed: false, reviewed_locale: "en-US",
            }] }, active: null, patient_locale: "en-US", active_medications: [],
        });
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue({ id: "request-2", patient_id: "patient-1", status, attempts: 1, requested_at: "2026-10-01T23:13:00Z", failure_code: status === "failed" ? "source_fields_incomplete" : null });
        render(<CarePlanPanel patientId="patient-1" />);
        const approve = await screen.findByRole("button", { name: "Approve and publish plan" });
        fireEvent.change(screen.getByPlaceholderText("Record the basis for your approval."), { target: { value: "All visible items reviewed" } });
        expect(approve).toBeDisabled();
        expect(screen.getByRole("alert")).toHaveTextContent("publication blocked");
        if (status === "failed") {
            expect(screen.getByRole("button", { name: "Retry generation" })).toBeInTheDocument();
            expect(screen.getByText(/Repeating the same request will not repair/)).toBeInTheDocument();
        }
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
        expect(await screen.findByText("Preview: source.pdf (page 2)")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Review source: follow-up.pdf" }));
        await waitFor(() => expect(fetchClinicianDocumentSource).toHaveBeenCalledWith("patient-1", "document-2"));
    });

    it("retries a failed protected source request without reloading the plan", async () => {
        vi.mocked(fetchClinicianCarePlanReviewContext).mockResolvedValue({ latest: {
            id: "plan-1", patient_id: "patient-1", version_number: 1, status: "draft", items: [{
                id: "item-1", source_fact_id: "fact-1", category: "movement", title: "Walk", instructions: "Walk.", frequency: "daily", schedule: {}, medication: {}, confidence_score: 0.9, uncertainty: [], conflict: {}, is_removed: false,
                source: { document_id: "document-1", file_name: "source.pdf", excerpt: "Walk.", location: { page: 2 } },
            }],
        }, active: null, patient_locale: "en-US", active_medications: [] });
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue(null);
        vi.mocked(fetchClinicianDocumentSource).mockRejectedValueOnce(new Error("Temporary source failure"));
        render(<CarePlanPanel patientId="patient-1" />);
        fireEvent.click(await screen.findByRole("button", { name: "Review source: source.pdf" }));
        expect(await screen.findByText("Temporary source failure")).toBeInTheDocument();
        vi.mocked(fetchClinicianDocumentSource).mockResolvedValue({ file_name: "source.pdf", file_url: "https://signed.test/original", mime_type: "application/pdf" });
        fireEvent.click(screen.getByRole("button", { name: "Retry source preview" }));
        expect(await screen.findByText("Preview: source.pdf (page 2)")).toBeInTheDocument();
        expect(fetchClinicianDocumentSource).toHaveBeenCalledTimes(2);
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
        expect(screen.getAllByRole("textbox", { name: "Medication name" })).toHaveLength(1);
        expect(screen.getAllByRole("textbox", { name: "Dose" })).toHaveLength(1);
        expect(screen.getAllByRole("combobox", { name: "Route" })).toHaveLength(1);
        expect(screen.queryByRole("textbox", { name: "Medication dosage" })).not.toBeInTheDocument();
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
