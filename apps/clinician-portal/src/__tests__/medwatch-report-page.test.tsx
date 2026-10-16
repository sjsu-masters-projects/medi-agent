import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MedWatchReportPage from "@/app/(dashboard)/medwatch/[draftId]/page";
import { approvedDraft, makeDraft, makeForm, submittedDraft, ATTESTATION_TEXT } from "./fixtures/medwatch";

const DRAFT_ID = "11111111-2222-4333-8444-555555555555";
const mocks = vi.hoisted(() => ({
    fetchMedWatchDraft: vi.fn(),
    fetchForm3500PreviewPdf: vi.fn(),
    updateMedWatchDraft: vi.fn(),
    approveMedWatchDraft: vi.fn(),
    discardMedWatchDraft: vi.fn(),
    recordMedWatchSubmission: vi.fn(),
    amendMedWatchSubmission: vi.fn(),
    downloadForm3500Pdf: vi.fn(),
    push: vi.fn(),
}));
const query = vi.hoisted(() => ({ value: "" }));
vi.mock("next/navigation", () => ({
    useParams: () => ({ draftId: "11111111-2222-4333-8444-555555555555" }),
    useRouter: () => ({ push: mocks.push, replace: vi.fn() }),
    useSearchParams: () => new URLSearchParams(query.value),
}));
vi.mock("@/services/clinicians", async (importOriginal) => ({
    ...(await importOriginal<typeof import("@/services/clinicians")>()),
    ...mocks,
}));

const createObjectURL = vi.fn(() => "blob:synthetic-preview");
const revokeObjectURL = vi.fn();

const issues = [
    { path: "section_g.occupation", code: "occupation_missing" },
    { path: "section_b.narrative", code: "narrative_missing" },
];

function pdf() {
    return new Blob(["%PDF-synthetic"], { type: "application/pdf" });
}

describe("MedWatch report workspace", () => {
    beforeEach(() => {
        Object.values(mocks).forEach((mock) => mock.mockReset());
        createObjectURL.mockClear();
        revokeObjectURL.mockClear();
        Object.assign(URL, { createObjectURL, revokeObjectURL });
        mocks.fetchForm3500PreviewPdf.mockResolvedValue(pdf());
        query.value = "";
    });

    it("opens a draft on Complete with the gate issues first and every section collapsed", async () => {
        mocks.fetchMedWatchDraft.mockResolvedValue(makeDraft({ missingForApproval: issues }));
        render(<MedWatchReportPage />);

        expect(await screen.findByRole("heading", { level: 1, name: "Form FDA 3500 report" })).toBeInTheDocument();
        expect(screen.getByRole("link", { name: "MedWatch" })).toHaveAttribute("href", "/medwatch");
        expect(screen.getByRole("button", { name: /Complete/ })).toHaveAttribute("aria-current", "step");
        expect(screen.getByText(/Step 1 of 4/)).toBeInTheDocument();
        const callout = screen.getByRole("region", { name: "Items needing attention" });
        expect(callout).toHaveTextContent("2 items need attention before approval");
        for (const detail of document.querySelectorAll("details[id^='section-']")) {
            expect(detail).not.toHaveAttribute("open");
        }
        expect(screen.getAllByText("1 missing")).toHaveLength(2);
        expect(screen.getAllByText("Complete").length).toBeGreaterThan(1);

        fireEvent.click(within(callout).getByRole("button", { name: "G3 Reporter occupation is missing" }));
        expect(document.getElementById("section-G")).toHaveAttribute("open");
        expect(screen.getByLabelText("G3 Occupation")).toHaveFocus();
    });

    it("collapses the stepper to one line on 390 px and spreads it on 1280 px", async () => {
        mocks.fetchMedWatchDraft.mockResolvedValue(makeDraft());
        const { container } = render(<MedWatchReportPage />);
        await screen.findByRole("button", { name: "Continue to preview" });
        const steps = screen.getByRole("navigation", { name: "Report steps" });
        expect(steps.querySelector(".md\\:hidden")).toHaveTextContent("Step 1 of 4");
        expect(steps.querySelector("ol.hidden.md\\:flex")).not.toBeNull();
        expect(container.querySelector("[class*='overflow-x-auto']")).toBeNull();
    });

    it("shows the watermarked PDF inline from an authenticated blob and revokes it on leaving", async () => {
        mocks.fetchMedWatchDraft.mockResolvedValue(makeDraft());
        const view = render(<MedWatchReportPage />);
        fireEvent.click(await screen.findByRole("button", { name: "Continue to preview" }));

        const frame = await screen.findByTitle("Form FDA 3500 draft preview");
        expect(frame).toHaveAttribute("src", "blob:synthetic-preview");
        expect(mocks.fetchForm3500PreviewPdf).toHaveBeenCalledWith(DRAFT_ID);
        expect(screen.getByText("Draft preview — watermarked, not for submission")).toBeInTheDocument();
        expect(screen.getByRole("link", { name: /Open in new tab/ })).toHaveAttribute("href", "blob:synthetic-preview");
        expect(screen.getByText(/Step 2 of 4/)).toBeInTheDocument();
        // A preview is not an export and not a download.
        expect(mocks.downloadForm3500Pdf).not.toHaveBeenCalled();

        view.unmount();
        expect(revokeObjectURL).toHaveBeenCalledWith("blob:synthetic-preview");
    });

    it("saves unsaved edits before it previews, so the PDF matches the screen", async () => {
        const draft = makeDraft();
        mocks.fetchMedWatchDraft.mockResolvedValue(draft);
        mocks.updateMedWatchDraft.mockImplementation(async (_id, formData) => ({ ...draft, formData, revision: 2 }));
        render(<MedWatchReportPage />);
        await screen.findByRole("button", { name: "Continue to preview" });
        fireEvent.change(
            screen.getByLabelText("B5 Describe event, problem or product use/medication error"),
            { target: { value: "Recovering" } },
        );
        fireEvent.click(screen.getByRole("button", { name: "Continue to preview" }));

        await waitFor(() =>
            expect(mocks.updateMedWatchDraft).toHaveBeenCalledWith(
                DRAFT_ID,
                expect.objectContaining({ section_b: expect.objectContaining({ narrative: "Recovering" }) }),
                1,
            ),
        );
        expect(await screen.findByTitle("Form FDA 3500 draft preview")).toBeInTheDocument();
    });

    it("stays on Complete and says so when saving before the preview fails", async () => {
        mocks.fetchMedWatchDraft.mockResolvedValue(makeDraft());
        mocks.updateMedWatchDraft.mockRejectedValue(new Error("private diagnostic"));
        render(<MedWatchReportPage />);
        await screen.findByRole("button", { name: "Continue to preview" });
        fireEvent.change(
            screen.getByLabelText("B5 Describe event, problem or product use/medication error"),
            { target: { value: "Edited" } },
        );
        fireEvent.click(screen.getByRole("button", { name: "Continue to preview" }));
        expect(await screen.findByRole("alert")).toHaveTextContent("Your unsaved form values are retained.");
        expect(screen.queryByTitle("Form FDA 3500 draft preview")).not.toBeInTheDocument();
        expect(screen.queryByText("private diagnostic")).not.toBeInTheDocument();
    });

    it("shows a clear preview error and retries", async () => {
        mocks.fetchMedWatchDraft.mockResolvedValue(makeDraft());
        mocks.fetchForm3500PreviewPdf.mockRejectedValueOnce(new Error("renderer detail"));
        render(<MedWatchReportPage />);
        fireEvent.click(await screen.findByRole("button", { name: "Continue to preview" }));
        expect(await screen.findByRole("alert")).toHaveTextContent("The preview could not be produced");
        expect(screen.queryByText("renderer detail")).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Try again" }));
        expect(await screen.findByTitle("Form FDA 3500 draft preview")).toBeInTheDocument();
        expect(mocks.fetchForm3500PreviewPdf).toHaveBeenCalledTimes(2);
    });

    it("blocks approval while gate issues remain and sends the user back to fix them", async () => {
        mocks.fetchMedWatchDraft.mockResolvedValue(makeDraft({ missingForApproval: issues }));
        render(<MedWatchReportPage />);
        await screen.findByRole("button", { name: "Continue to preview" });
        fireEvent.click(screen.getByRole("button", { name: /^3\s*Approve/ }));
        expect(await screen.findByRole("note")).toHaveTextContent("2 items need attention before approval.");
        expect(screen.getByRole("button", { name: "Approve for export" })).toBeDisabled();
    });

    it("approves through the attestation dialog and moves to the download step", async () => {
        const draft = makeDraft({ formData: makeForm({ outcomes: ["hospitalization"] }) });
        mocks.fetchMedWatchDraft.mockResolvedValue(draft);
        mocks.approveMedWatchDraft.mockResolvedValue(
            approvedDraft({ revision: 2, approvalNote: "Evidence and form reviewed." }),
        );
        render(<MedWatchReportPage />);
        await screen.findByRole("button", { name: "Continue to preview" });
        fireEvent.click(screen.getByRole("button", { name: /^3\s*Approve/ }));
        fireEvent.click(await screen.findByRole("button", { name: "Approve for export" }));

        const dialog = screen.getByRole("dialog", { name: "Approve Form 3500 draft" });
        const confirm = within(dialog).getByRole("button", { name: "Confirm approval" });
        expect(confirm).toBeDisabled();
        fireEvent.change(within(dialog).getByLabelText("Approval note"), {
            target: { value: "Evidence and form reviewed." },
        });
        fireEvent.click(within(dialog).getByRole("checkbox", { name: ATTESTATION_TEXT }));
        fireEvent.click(confirm);

        await waitFor(() =>
            expect(mocks.approveMedWatchDraft).toHaveBeenCalledWith(DRAFT_ID, expect.objectContaining({
                approvalNote: "Evidence and form reviewed.",
                expectedRevision: 1,
            })),
        );
        expect(await screen.findByRole("button", { name: "Download Form 3500 (PDF)" })).toBeInTheDocument();
        expect(screen.getByText(/Step 4 of 4/)).toBeInTheDocument();
    });

    it("opens an approved report on Download and downloads the audited PDF", async () => {
        const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
        mocks.fetchMedWatchDraft.mockResolvedValue(approvedDraft());
        mocks.downloadForm3500Pdf.mockResolvedValue({ blob: pdf(), filename: "fda-3500-11111111-not-submitted.pdf" });
        render(<MedWatchReportPage />);
        fireEvent.click(await screen.findByRole("button", { name: "Download Form 3500 (PDF)" }));
        const dialog = screen.getByRole("dialog", { name: "Download Form 3500 (PDF)" });
        expect(dialog).toHaveTextContent("MediAgent did not submit this report. You submit it to FDA.");
        fireEvent.click(within(dialog).getByRole("button", { name: "Download PDF" }));
        await waitFor(() => expect(mocks.downloadForm3500Pdf).toHaveBeenCalledWith(DRAFT_ID));
        expect(await screen.findByText(/Form 3500 PDF downloaded and audited/)).toBeInTheDocument();
        expect(click).toHaveBeenCalledTimes(1);
        expect(mocks.fetchForm3500PreviewPdf).not.toHaveBeenCalled();
        click.mockRestore();
    });

    it("records a submission and shows the report as submitted", async () => {
        mocks.fetchMedWatchDraft
            .mockResolvedValueOnce(approvedDraft())
            .mockResolvedValueOnce(submittedDraft());
        mocks.recordMedWatchSubmission.mockResolvedValue(undefined);
        render(<MedWatchReportPage />);
        fireEvent.click(await screen.findByRole("button", { name: "Record FDA submission" }));
        const dialog = screen.getByRole("dialog", { name: "Record FDA submission" });
        fireEvent.change(within(dialog).getByLabelText("Date submitted to FDA"), { target: { value: "2026-10-10" } });
        fireEvent.change(within(dialog).getByLabelText("Submission method"), { target: { value: "medwatch_online" } });
        fireEvent.click(within(dialog).getByRole("checkbox", { name: /I submitted this report to FDA myself/ }));
        fireEvent.click(within(dialog).getByRole("button", { name: "Record submission" }));
        await waitFor(() =>
            expect(mocks.recordMedWatchSubmission).toHaveBeenCalledWith(
                DRAFT_ID,
                expect.objectContaining({ submittedOn: "2026-10-10", method: "medwatch_online", expectedRevision: 3 }),
            ),
        );
        expect(await screen.findByText(/Submission recorded\. The report is now read-only under Submitted/)).toBeInTheDocument();
        expect(await screen.findByRole("region", { name: "FDA submission record" })).toBeInTheDocument();
    });

    it("shows a submitted report read-only and amends its record", async () => {
        const original = submittedDraft().currentSubmission!;
        mocks.fetchMedWatchDraft.mockResolvedValue(submittedDraft());
        mocks.amendMedWatchSubmission.mockResolvedValue(undefined);
        render(<MedWatchReportPage />);
        const record = await screen.findByRole("region", { name: "FDA submission record" });
        expect(record).toHaveTextContent("Submitted by Dr. Synthetic Clinician outside MediAgent on Oct 10, 2026.");
        expect(screen.getByText("Not submitted to FDA by MediAgent")).toBeInTheDocument();
        for (const name of ["Approve for export", "Discard draft", "Record FDA submission"]) {
            expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
        }
        fireEvent.click(screen.getByRole("button", { name: "Amend record" }));
        const dialog = screen.getByRole("dialog", { name: "Amend submission record" });
        fireEvent.change(within(dialog).getByLabelText("FDA confirmation or reference number (optional)"), {
            target: { value: "MW-0000009" },
        });
        fireEvent.change(within(dialog).getByLabelText("Reason for amendment"), { target: { value: "Corrected" } });
        fireEvent.click(within(dialog).getByRole("button", { name: "Save amendment" }));
        await waitFor(() =>
            expect(mocks.amendMedWatchSubmission).toHaveBeenCalledWith(
                DRAFT_ID,
                expect.objectContaining({ amendsId: original.id, fdaReference: "MW-0000009" }),
            ),
        );
        expect(await screen.findByText("Submission record amended. The original record is kept.")).toBeInTheDocument();
    });

    it("shows a discarded report read-only with its reason", async () => {
        mocks.fetchMedWatchDraft.mockResolvedValue(
            makeDraft({ discardedAt: "2026-10-11T16:30:00Z", discardReason: "Wrong suspect product." }),
        );
        render(<MedWatchReportPage />);
        const record = await screen.findByRole("region", { name: "Discard record" });
        expect(record).toHaveTextContent("Reason: Wrong suspect product.");
        expect(screen.getByText("Discarded")).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Save draft" })).not.toBeInTheDocument();
    });

    it("discards a draft and returns to the Discarded tab", async () => {
        mocks.fetchMedWatchDraft.mockResolvedValue(makeDraft());
        mocks.discardMedWatchDraft.mockResolvedValue(undefined);
        render(<MedWatchReportPage />);
        fireEvent.click(await screen.findByRole("button", { name: "Discard draft" }));
        const dialog = screen.getByRole("dialog", { name: "Discard MedWatch draft" });
        fireEvent.change(within(dialog).getByLabelText("Reason for discarding"), { target: { value: "Duplicate draft." } });
        fireEvent.click(within(dialog).getByRole("button", { name: "Discard draft" }));
        await waitFor(() =>
            expect(mocks.discardMedWatchDraft).toHaveBeenCalledWith(DRAFT_ID, { reason: "Duplicate draft.", expectedRevision: 1 }),
        );
        await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/medwatch?tab=discarded"));
    });

    it("explains on the download step that approval comes first", async () => {
        mocks.fetchMedWatchDraft.mockResolvedValue(makeDraft());
        mocks.discardMedWatchDraft.mockResolvedValue(undefined);
        render(<MedWatchReportPage />);
        await screen.findByRole("button", { name: "Continue to preview" });
        fireEvent.click(screen.getByRole("button", { name: /^4\s*Download/ }));
        // Not yet approved: the download step only points back to approval.
        expect(await screen.findByRole("button", { name: "Go to approval" })).toBeInTheDocument();
    });

    it("offers a way back when the report is unavailable", async () => {
        query.value = "from=tab%3Dapproved";
        mocks.fetchMedWatchDraft.mockRejectedValue(new Error("not found"));
        render(<MedWatchReportPage />);
        expect(await screen.findByText("Unable to load this report")).toBeInTheDocument();
        expect(screen.getByRole("link", { name: "Back to MedWatch" })).toHaveAttribute("href", "/medwatch?tab=approved");
        await act(async () => undefined);
    });
});
