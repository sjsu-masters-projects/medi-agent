import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CarePlanPanel } from "@/components/features/care-plan-panel";
import {
    fetchClinicianCarePlanReviewContext,
    fetchClinicianCarePlanGeneration,
    fetchClinicianDocumentSource,
    retryClinicianCarePlanGeneration,
    fetchBackTranslation,
    translateClinicianCarePlanItem,
    updateClinicianCarePlan,
} from "@/services/clinicians";

vi.mock("@/services/clinicians", () => ({
    approveClinicianCarePlan: vi.fn(),
    fetchBackTranslation: vi.fn(),
    fetchClinicianCarePlanReviewContext: vi.fn(),
    fetchClinicianCarePlanGeneration: vi.fn(),
    fetchClinicianDocumentSource: vi.fn(),
    retryClinicianCarePlanGeneration: vi.fn(),
    translateClinicianCarePlanItem: vi.fn(),
    updateClinicianCarePlan: vi.fn(),
}));

/** Synthetic item wording checked in both languages, with English as the source. */
const verified = (title: string, instructions: string, frequency: string) => ({
    title, instructions, frequency,
    source_locale: "en-US" as const,
    wording: {
        "en-US": { title, instructions, frequency },
        "es-MX": { title: `${title} (es)`, instructions: `${instructions} (es)`, frequency: `${frequency} (es)` },
    },
    wording_origin: { "en-US": "source" as const, "es-MX": "ai_draft" as const },
    wording_verified: true,
});

vi.mock("@/components/features/document-source-viewer", () => ({
    DocumentSourceViewer: ({ fileName, initialPage }: { fileName: string; initialPage?: number }) => <p>Preview: {fileName} (page {initialPage})</p>,
}));

describe("CarePlanPanel", () => {
    it("shows grounded source titles while preserving document identity and page navigation", async () => {
        const source = { document_id: "document-title", file_name: "scan-01.pdf",
            display_title: { "en-US": "Walking instructions", "es-MX": "Indicaciones para caminar" },
            excerpt: "Walk for 20 minutes.", location: { page: 2 } };
        vi.mocked(fetchClinicianCarePlanReviewContext).mockResolvedValue({ latest: {
            id: "plan-title", patient_id: "patient-1", version_number: 1, status: "approved", items: [{
                id: "item-title", category: "movement", ...verified("Walk", "Walk for 20 minutes.", "daily"),
                schedule: {}, medication: {}, uncertainty: [], conflict: {}, is_removed: false, source,
            }],
        }, active: null, patient_locale: "en-US", active_medications: [] });
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue(null);
        vi.mocked(fetchClinicianDocumentSource).mockResolvedValue({ file_name: "scan-01.pdf",
            file_url: "https://signed.test/source", mime_type: "application/pdf" });
        render(<CarePlanPanel patientId="patient-1" />);
        const review = await screen.findByRole("button", { name: "Review source: Walking instructions (scan-01.pdf)" });
        fireEvent.click(screen.getByText("Source excerpts and confidence (1)"));
        expect(screen.getByText("Walking instructions (scan-01.pdf) · page 2")).toBeVisible();
        fireEvent.click(review);
        await waitFor(() => expect(fetchClinicianDocumentSource).toHaveBeenCalledWith("patient-1", "document-title"));
        expect(await screen.findByText("Preview: scan-01.pdf (page 2)")).toBeInTheDocument();
    });

    it("focuses a message-linked activity once without stealing focus during edits", async () => {
        const previous = window.location.href;
        window.history.replaceState(null, "", "/patients/patient-1?tab=care-plan#care-plan-item-item-1");
        vi.mocked(fetchClinicianCarePlanReviewContext).mockResolvedValue({ latest: {
            id: "plan-1", patient_id: "patient-1", version_number: 2, status: "draft", items: [{
                id: "item-first", category: "medication", title: "Atorvastatin", instructions: "Take one tablet", frequency: "daily",
                schedule: {}, medication: {}, uncertainty: [], conflict: {}, is_removed: false,
            }, {
                id: "item-1", category: "hydration", title: "Drink water", instructions: "Approved source text", frequency: "daily",
                schedule: {}, medication: {}, uncertainty: [], conflict: {}, is_removed: false,
            }],
        }, active: null, patient_locale: "en-US", active_medications: [] });
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue(null);
        try {
            render(<CarePlanPanel patientId="patient-1" />);
            const heading = await screen.findByRole("heading", { name: "Drink water" });
            await waitFor(() => expect(heading).toHaveFocus());
            const title = screen.getByRole("textbox", { name: /^Title$/ });
            expect(title).toHaveValue("Drink water");
            title.focus();
            fireEvent.change(title, { target: { value: "Reviewed activity title" } });
            await act(async () => { await new Promise<void>((resolve) => requestAnimationFrame(() => resolve())); });
            expect(title).toHaveFocus();
        } finally { window.history.replaceState(null, "", previous); }
    });
    it("asks for both languages when a draft item has wording in one language only", async () => {
        const instruction = "Caminar durante veinte minutos";
        const item = { id: "item", category: "movement", title: instruction, instructions: instruction,
            frequency: "diariamente", schedule: {}, medication: {}, uncertainty: [], conflict: {}, is_removed: false,
            confidence_score: 1, source: { document_id: "internal-document-id", excerpt: instruction } };
        vi.mocked(fetchClinicianCarePlanReviewContext).mockResolvedValue({ latest: {
            id: "plan", patient_id: "p", version_number: 1, status: "draft", items: [item],
        }, active: null, patient_locale: "es-MX", active_medications: [] });
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue(null);
        render(<CarePlanPanel patientId="p" />);
        expect(await screen.findByText(/Patient reads Español \(México\)/)).toBeInTheDocument();
        expect(screen.getByText(/wording in one language only/)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /Español \(México\) · draft English \(US\)/ })).toBeEnabled();
        expect(screen.getByRole("checkbox", { name: /I verified the English wording/ })).toBeDisabled();
        expect(screen.getByRole("textbox", { name: "Instructions" })).toHaveValue(instruction);
        expect(screen.getByRole("textbox", { name: "Instructions" }).tagName).toBe("TEXTAREA");
        expect(screen.getByText("100% extraction confidence")).toBeInTheDocument();
        expect(screen.getByText(/not medical certainty/)).toBeInTheDocument();
        expect(screen.queryByText(/internal-document-id/)).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Review source: Uploaded document" })).toHaveTextContent("Review source");
        expect(screen.getByRole("button", { name: "Approve and publish plan" })).toBeDisabled();
        expect(screen.getByRole("region", { name: "Publication requirements" })).toHaveTextContent("1 item needs wording in both English and Spanish");
        const retained = screen.getByText("Review retained instructions (1)").closest("details");
        expect(retained).not.toHaveAttribute("open");
        expect(retained?.querySelector("li")).toHaveTextContent(`${instruction} · diariamente`);
        expect(retained?.querySelector("li")?.textContent?.split(instruction)).toHaveLength(2);
    });
    it("does not ask for a medication publication decision on an approved plan", async () => {
        const plan = { id: "approved", patient_id: "p", version_number: 1, status: "approved" as const, items: [{
            id: "med", category: "medication", title: "Metformin", instructions: "With dinner", frequency: "daily",
            schedule: {}, medication: { name: "Metformin" }, uncertainty: [], conflict: {}, is_removed: false,
        }] };
        vi.mocked(fetchClinicianCarePlanReviewContext).mockResolvedValue({ latest: plan, active: plan, patient_locale: "en-US", active_medications: [] });
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue(null);
        render(<CarePlanPanel patientId="p" />);
        expect((await screen.findAllByText("Metformin")).length).toBeGreaterThan(0);
        expect(screen.queryByText(/Choose whether each medication/)).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Approve and publish plan" })).not.toBeInTheDocument();
    });
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
        vi.mocked(fetchBackTranslation).mockReset();
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

    it("visibly associates multiple source excerpts with filenames, pages, and the selected preview", async () => {
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
        vi.mocked(fetchClinicianDocumentSource).mockResolvedValueOnce({
            file_name: "source.pdf", file_url: "https://signed.test/original", mime_type: "application/pdf", preview_status: "ready", preview_url: "https://signed.test/preview", preview_mime_type: "application/pdf",
        }).mockResolvedValueOnce({
            file_name: "follow-up.pdf", file_url: "https://signed.test/follow-up", mime_type: "application/pdf",
        });

        render(<CarePlanPanel patientId="patient-1" />);

        expect(await screen.findAllByRole("button", { name: "Review source: source.pdf" })).toHaveLength(1);
        fireEvent.click(screen.getByText("Source excerpts and confidence (2)"));
        expect(screen.getByText("source.pdf · page 2")).toBeVisible();
        expect(screen.getByText("follow-up.pdf · page 1")).toBeVisible();
        expect(screen.getByText("“Walk for 20 minutes.”")).toBeVisible();
        expect(screen.getByText("“Continue walking.”")).toBeVisible();
        expect(screen.getByRole("button", { name: "Review source: source.pdf" })).toHaveTextContent(/^Review source 1$/);
        expect(screen.getByRole("button", { name: "Review source: follow-up.pdf" })).toHaveTextContent(/^Review source 2$/);
        fireEvent.click(await screen.findByRole("button", { name: "Review source: source.pdf" }));
        await waitFor(() => expect(fetchClinicianDocumentSource).toHaveBeenCalledWith("patient-1", "document-1"));
        expect(await screen.findByText("Preview: source.pdf (page 2)")).toBeInTheDocument();
        expect(screen.getByText("Selected source: source.pdf")).toBeVisible();
        fireEvent.click(screen.getByRole("button", { name: "Review source: follow-up.pdf" }));
        await waitFor(() => expect(fetchClinicianDocumentSource).toHaveBeenCalledWith("patient-1", "document-2"));
        expect(await screen.findByText("Preview: follow-up.pdf (page 1)")).toBeInTheDocument();
        expect(screen.getByText("Selected source: follow-up.pdf")).toBeVisible();
        expect(screen.queryByText("Selected source: source.pdf")).not.toBeInTheDocument();
        expect(updateClinicianCarePlan).not.toHaveBeenCalled();
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
        expect(screen.getByRole("region", { name: "Proposed Today preview" })).toBeInTheDocument();
        expect(screen.getByText(/Read-only view using the saved draft/)).toBeInTheDocument();
    });

    it("does not allow approval while the clinician has unsaved changes", async () => {
        vi.mocked(fetchClinicianCarePlanReviewContext).mockResolvedValue({
            patient_locale: "en-US", active_medications: [], active: null,
            latest: {
                id: "plan-1", patient_id: "patient-1", version_number: 1, status: "draft",
                items: [{
                    id: "item-1", source_fact_id: "fact-1", category: "movement",
                    schedule: {}, medication: {}, ...verified("Walk", "Walk 20 minutes", "daily"),
                    uncertainty: [], conflict: {}, is_removed: false,
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
        expect(screen.getByText(/need wording in both English and Spanish|needs wording in both English and Spanish/)).toBeInTheDocument();
        expect(screen.getByText(/Choose whether each medication/)).toBeInTheDocument();
        expect(screen.getByRole("option", { name: /Update Metformin/ })).toBeInTheDocument();
        fireEvent.change(screen.getByLabelText("Publication decision"), { target: { value: "update:med-1" } });
        expect(screen.getByRole("checkbox", { name: /I verified the English wording/ })).toBeDisabled();
        expect(approve).toBeDisabled();
        expect(screen.getByText(/Save your edits before approving/)).toBeInTheDocument();
    });

    it("labels the source by the evidence language, not the authored wording (DV-004)", async () => {
        // An English order that produced Spanish-authored wording (Morgan's Metformin case):
        // source_locale is es-MX but the evidence is English, so no "Translated from Spanish".
        const englishSource = {
            id: "item-en", source_fact_id: "fact-en", category: "hydration",
            title: "Tome un vaso de agua", instructions: "Tome un vaso con cada comida", frequency: "tres veces al día",
            schedule: {}, medication: {}, uncertainty: [], conflict: {}, is_removed: false,
            source_locale: "es-MX" as const, source_evidence_locale: "en-US" as const,
            wording: {
                "en-US": { title: "Drink a glass of water", instructions: "Drink a glass with each meal", frequency: "three times a day" },
                "es-MX": { title: "Tome un vaso de agua", instructions: "Tome un vaso con cada comida", frequency: "tres veces al día" },
            },
            wording_origin: { "es-MX": "source" as const, "en-US": "ai_draft" as const }, wording_verified: true,
        };
        const spanishSource = {
            id: "item-es", source_fact_id: "fact-es", category: "movement",
            title: "Camine 20 minutos", instructions: "Camine después de cenar", frequency: "diario",
            schedule: {}, medication: {}, uncertainty: [], conflict: {}, is_removed: false,
            source_locale: "es-MX" as const, source_evidence_locale: "es-MX" as const,
            wording: {
                "en-US": { title: "Walk 20 minutes", instructions: "Walk after dinner", frequency: "daily" },
                "es-MX": { title: "Camine 20 minutos", instructions: "Camine después de cenar", frequency: "diario" },
            },
            wording_origin: { "es-MX": "source" as const, "en-US": "ai_draft" as const }, wording_verified: true,
        };
        vi.mocked(fetchClinicianCarePlanReviewContext).mockResolvedValue({ latest: {
            id: "plan-1", patient_id: "patient-1", version_number: 1, status: "draft", items: [englishSource, spanishSource],
        }, active: null, patient_locale: "es-MX", active_medications: [] });
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue(null);
        vi.mocked(fetchBackTranslation).mockResolvedValue({ back_translation: { title: "x", instructions: "x", frequency: "x" }, guards: { numbers_match: true, medication_names_match: true } });
        render(<CarePlanPanel patientId="patient-1" />);

        // English-first titles in the sidebar, and the "Translated from Spanish" badge only on
        // the genuinely Spanish-sourced item.
        expect(await screen.findByRole("heading", { name: "Drink a glass of water" })).toBeInTheDocument();
        expect(screen.getAllByText("Translated from Spanish")).toHaveLength(1);

        // The English-sourced item (selected first) names an English source, never Spanish.
        expect(screen.getByText("English source")).toBeInTheDocument();
        expect(screen.queryByText("Spanish source")).not.toBeInTheDocument();

        // Selecting the Spanish-sourced item shows a Spanish source label.
        fireEvent.click(screen.getByText("Walk 20 minutes"));
        expect(await screen.findByText("Spanish source")).toBeInTheDocument();
    });

    it("reviews English and Spanish side by side and re-checks both after an edit", async () => {
        const item = { id: "item-1", source_fact_id: "fact-1", category: "movement", schedule: {}, medication: {},
            uncertainty: [], conflict: {}, is_removed: false,
            ...verified("Walk", "Walk 20 minutes", "daily"), wording_verified: false };
        const plan = { id: "plan-1", patient_id: "patient-1", version_number: 2, status: "draft" as const, items: [item] };
        vi.mocked(fetchClinicianCarePlanReviewContext).mockResolvedValue({ latest: plan, active: null, patient_locale: "es-MX", active_medications: [] });
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue(null);
        vi.mocked(updateClinicianCarePlan).mockImplementation(async (_patient, _plan, items) => ({ ...plan, items: [{ ...item, ...items[0], wording_origin: { "en-US": "source", "es-MX": "clinician_edited" } }] }));
        vi.mocked(translateClinicianCarePlanItem).mockResolvedValue(plan);
        vi.mocked(fetchBackTranslation).mockResolvedValue({ back_translation: { title: "Walk", instructions: "Walk 20 minutes", frequency: "daily" }, guards: { numbers_match: true, medication_names_match: true } });
        render(<CarePlanPanel patientId="patient-1" />);

        expect(await screen.findByText("From source")).toBeInTheDocument();
        expect(screen.getByText(/AI translation · check it/)).toBeInTheDocument();
        expect(screen.getByText("Shown in patient's Today")).toBeInTheDocument();
        const check = screen.getByRole("checkbox", { name: /I verified the English wording/ });
        // Not tickable until the back-translation of the saved Spanish has loaded and passed.
        expect(check).toBeDisabled();
        await waitFor(() => expect(check).toBeEnabled());
        fireEvent.click(check);
        expect(check).toBeChecked();
        fireEvent.change(screen.getByDisplayValue("Walk 20 minutes (es)"), { target: { value: "Camine 20 minutos" } });
        expect(check).not.toBeChecked();
        expect(check).toBeDisabled();
        expect(screen.getAllByText("Save your changes first").length).toBeGreaterThan(0);
        expect(screen.getByRole("button", { name: /Re-translate from English/ })).toBeDisabled();
        fireEvent.click(screen.getByRole("button", { name: "Save review" }));
        await waitFor(() => expect(updateClinicianCarePlan).toHaveBeenCalledTimes(1));
        expect(vi.mocked(updateClinicianCarePlan).mock.calls[0][2][0]).toEqual(expect.objectContaining({ wording_verified: false }));
        // The saved Spanish is back-translated again before it can be attested.
        await waitFor(() => expect(fetchBackTranslation).toHaveBeenCalledTimes(2));
        await waitFor(() => expect(screen.getByRole("checkbox", { name: /I verified the English wording/ })).toBeEnabled());
        fireEvent.click(screen.getByRole("checkbox", { name: /I verified the English wording/ }));
        fireEvent.click(screen.getByRole("button", { name: "Save review" }));
        await waitFor(() => expect(updateClinicianCarePlan).toHaveBeenLastCalledWith("patient-1", "plan-1", [expect.objectContaining({
            title: "Walk", wording_verified: true, source_locale: "en-US",
            wording: expect.objectContaining({ "es-MX": expect.objectContaining({ instructions: "Camine 20 minutos" }) }),
        })]));
        expect(await screen.findByText("Edited by clinician")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: /Re-translate from English/ }));
        await waitFor(() => expect(translateClinicianCarePlanItem).toHaveBeenCalledWith("patient-1", "plan-1", "item-1", "en-US"));
    });

    it.each([
        ["failed guards", () => vi.mocked(fetchBackTranslation).mockResolvedValue({ back_translation: { title: "Walk", instructions: "Walk 30 minutes", frequency: "daily" }, guards: { numbers_match: false, medication_names_match: true } }), "Numbers or medication names differ — fix the Spanish"],
        ["an unavailable back-translation", () => vi.mocked(fetchBackTranslation).mockRejectedValue(new Error("down")), "Back-translation unavailable — retry"],
        ["a pending back-translation", () => vi.mocked(fetchBackTranslation).mockReturnValue(new Promise(() => undefined)), "Back-translation is loading"],
    ])("keeps the attestation disabled with %s", async (_name, arrange, reason) => {
        const item = { id: "item-1", source_fact_id: "fact-1", category: "movement", schedule: {}, medication: {},
            uncertainty: [], conflict: {}, is_removed: false, ...verified("Walk", "Walk 20 minutes", "daily"), wording_verified: false };
        const plan = { id: "plan-1", patient_id: "patient-1", version_number: 2, status: "draft" as const, items: [item] };
        vi.mocked(fetchClinicianCarePlanReviewContext).mockResolvedValue({ latest: plan, active: null, patient_locale: "es-MX", active_medications: [] });
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue(null);
        arrange();
        render(<CarePlanPanel patientId="patient-1" />);
        const check = await screen.findByRole("checkbox", { name: /I verified the English wording/ });
        await waitFor(() => expect(check.closest("label")).toHaveTextContent(reason));
        expect(check).toBeDisabled();
    });
});
