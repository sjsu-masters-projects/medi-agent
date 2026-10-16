import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MedWatchPage from "@/app/(dashboard)/medwatch/page";
import { approvedDraft, makeDraft, submittedDraft } from "./fixtures/medwatch";

const mocks = vi.hoisted(() => ({
    fetchADRReviewQueue: vi.fn(),
    fetchMedWatchDrafts: vi.fn(),
    discardMedWatchDraft: vi.fn(),
    recordMedWatchSubmission: vi.fn(),
    amendMedWatchSubmission: vi.fn(),
    downloadForm3500Pdf: vi.fn(),
}));
const query = vi.hoisted(() => ({ value: "" }));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(query.value) }));
vi.mock("@/services/clinicians", async (importOriginal) => ({
    ...(await importOriginal<typeof import("@/services/clinicians")>()),
    ...mocks,
}));

const discarded = makeDraft({
    id: "33333333-2222-4333-8444-555555555555",
    discardedAt: "2026-10-11T16:30:00Z",
    discardReason: "Prepared for the wrong suspect product.",
});

function draftsFor(state: string) {
    if (state === "submitted") return [submittedDraft()];
    if (state === "discarded") return [discarded];
    return [makeDraft(), approvedDraft({ id: "22222222-2222-4333-8444-555555555555" })];
}

describe("MedWatch Active / Submitted / Discarded states", () => {
    beforeEach(() => {
        Object.values(mocks).forEach((mock) => mock.mockReset());
        mocks.fetchADRReviewQueue.mockResolvedValue([]);
        mocks.fetchMedWatchDrafts.mockImplementation(async (state: string) => draftsFor(state));
        query.value = "";
        window.history.replaceState(null, "", "/medwatch");
    });

    it("switches the list with a segmented control bound to ?state=", async () => {
        render(<MedWatchPage />);
        const control = await screen.findByRole("radiogroup", { name: "MedWatch draft state" });
        expect(within(control).getByRole("radio", { name: "Active" })).toHaveAttribute("aria-checked", "true");
        expect(mocks.fetchMedWatchDrafts).toHaveBeenCalledWith("active");
        expect(await screen.findAllByText("MedWatch Form 3500 draft")).toHaveLength(2);

        fireEvent.click(within(control).getByRole("radio", { name: "Discarded" }));
        await waitFor(() => expect(mocks.fetchMedWatchDrafts).toHaveBeenLastCalledWith("discarded"));
        expect(window.location.search).toBe("?state=discarded");
        expect(within(control).getByRole("radio", { name: "Discarded" })).toHaveAttribute("aria-checked", "true");
        expect(await screen.findByText("Reason: Prepared for the wrong suspect product.")).toBeInTheDocument();

        fireEvent.click(within(control).getByRole("radio", { name: "Active" }));
        await waitFor(() => expect(mocks.fetchMedWatchDrafts).toHaveBeenLastCalledWith("active"));
        expect(window.location.search).toBe("");
    });

    it("shows a submitted draft read-only with its record, history and amendment", async () => {
        query.value = "state=submitted";
        const original = submittedDraft().currentSubmission!;
        const amended = {
            ...original,
            id: "submission-2",
            submittedOn: "2026-10-09",
            amendsId: "submission-1",
            amendReason: "Wrong date entered",
            createdAt: "2026-10-11T17:00:00Z",
        };
        mocks.fetchMedWatchDrafts.mockResolvedValue([
            submittedDraft({ currentSubmission: amended, submissionHistory: [amended, original] }),
        ]);
        mocks.amendMedWatchSubmission.mockResolvedValue(undefined);
        render(<MedWatchPage />);

        const record = await screen.findByRole("region", { name: "FDA submission record" });
        expect(mocks.fetchMedWatchDrafts).toHaveBeenCalledWith("submitted");
        expect(record).toHaveTextContent(
            "Submitted by Dr. Synthetic Clinician outside MediAgent on Oct 9, 2026.",
        );
        expect(within(record).getByText("Amendment reason: Wrong date entered")).toBeInTheDocument();
        expect(within(record).getByText(/original record/)).toBeInTheDocument();
        expect(screen.getByText("Not submitted to FDA by MediAgent")).toBeInTheDocument();
        expect(
            screen.getByLabelText("B5 Describe event, problem or product use/medication error"),
        ).toBeDisabled();
        for (const name of ["Save draft", "Approve for export", "Discard draft", "Record FDA submission"]) {
            expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
        }
        expect(screen.getByRole("button", { name: "Download Form 3500 (PDF)" })).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: "Amend record" }));
        const dialog = screen.getByRole("dialog", { name: "Amend submission record" });
        fireEvent.change(within(dialog).getByLabelText("FDA confirmation or reference number (optional)"), {
            target: { value: "MW-0000009" },
        });
        fireEvent.change(within(dialog).getByLabelText("Reason for amendment"), {
            target: { value: "Reference number corrected" },
        });
        fireEvent.click(within(dialog).getByRole("button", { name: "Save amendment" }));
        await waitFor(() =>
            expect(mocks.amendMedWatchSubmission).toHaveBeenCalledWith(
                "11111111-2222-4333-8444-555555555555",
                expect.objectContaining({ amendsId: "submission-2", fdaReference: "MW-0000009" }),
            ),
        );
        expect(await screen.findByText("Submission record amended. The original record is kept.")).toBeInTheDocument();
    });

    it("shows a discarded draft read-only with reason and date and no export", async () => {
        query.value = "state=discarded";
        render(<MedWatchPage />);
        const record = await screen.findByRole("region", { name: "Discard record" });
        expect(record).toHaveTextContent(/Discarded on .+\. The ADR assessment returned to review\./);
        // The status badge, beside the segmented control's own "Discarded" option.
        expect(screen.getAllByText("Discarded")).toHaveLength(2);
        expect(screen.queryByText("Approved for export")).not.toBeInTheDocument();
        for (const name of ["Save draft", "Approve for export", "Discard draft", "Download Form 3500 (PDF)", "Export approved JSON"]) {
            expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
        }
        expect(screen.getByRole("button", { name: "Preview Form 3500" })).toBeInTheDocument();
    });

    it("discards an active draft, says the assessment returns to review and reloads", async () => {
        mocks.discardMedWatchDraft.mockResolvedValue(undefined);
        render(<MedWatchPage />);
        await screen.findAllByText("MedWatch Form 3500 draft");
        mocks.fetchMedWatchDrafts.mockResolvedValue([approvedDraft({ id: "22222222-2222-4333-8444-555555555555" })]);
        fireEvent.click(screen.getAllByRole("button", { name: "Discard draft" })[0]);
        const dialog = screen.getByRole("dialog", { name: "Discard MedWatch draft" });
        fireEvent.change(within(dialog).getByLabelText("Reason for discarding"), {
            target: { value: "Duplicate draft." },
        });
        fireEvent.click(within(dialog).getByRole("button", { name: "Discard draft" }));
        await waitFor(() =>
            expect(mocks.discardMedWatchDraft).toHaveBeenCalledWith("11111111-2222-4333-8444-555555555555", {
                reason: "Duplicate draft.",
                expectedRevision: 1,
            }),
        );
        expect(
            await screen.findByText("MedWatch draft discarded. Its ADR assessment returned to review."),
        ).toBeInTheDocument();
        await waitFor(() => expect(mocks.fetchADRReviewQueue).toHaveBeenCalledTimes(2));
        await waitFor(() => expect(screen.getAllByText("MedWatch Form 3500 draft")).toHaveLength(1));
    });

    it("records a submission for an approved draft and moves it out of Active", async () => {
        mocks.recordMedWatchSubmission.mockResolvedValue(undefined);
        mocks.fetchMedWatchDrafts.mockResolvedValue([approvedDraft()]);
        render(<MedWatchPage />);
        fireEvent.click(await screen.findByRole("button", { name: "Record FDA submission" }));
        const dialog = screen.getByRole("dialog", { name: "Record FDA submission" });
        fireEvent.change(within(dialog).getByLabelText("Date submitted to FDA"), {
            target: { value: "2026-10-10" },
        });
        fireEvent.change(within(dialog).getByLabelText("Submission method"), {
            target: { value: "medwatch_online" },
        });
        fireEvent.click(within(dialog).getByRole("checkbox", { name: /I submitted this report to FDA myself/ }));
        mocks.fetchMedWatchDrafts.mockResolvedValue([]);
        fireEvent.click(within(dialog).getByRole("button", { name: "Record submission" }));
        await waitFor(() =>
            expect(mocks.recordMedWatchSubmission).toHaveBeenCalledWith(
                "11111111-2222-4333-8444-555555555555",
                expect.objectContaining({ submittedOn: "2026-10-10", method: "medwatch_online", expectedRevision: 3 }),
            ),
        );
        expect(await screen.findByText(/Submission recorded\. The draft is now read-only under Submitted/)).toBeInTheDocument();
        expect(await screen.findByText("No active MedWatch drafts")).toBeInTheDocument();
    });

    it("downloads the PDF after the not-submitted confirmation", async () => {
        Object.assign(URL, { createObjectURL: vi.fn(() => "blob:synthetic"), revokeObjectURL: vi.fn() });
        const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
        mocks.fetchMedWatchDrafts.mockResolvedValue([approvedDraft()]);
        mocks.downloadForm3500Pdf.mockResolvedValue({
            blob: new Blob(["%PDF"], { type: "application/pdf" }),
            filename: "fda-3500-11111111-not-submitted.pdf",
        });
        render(<MedWatchPage />);
        fireEvent.click(await screen.findByRole("button", { name: "Download Form 3500 (PDF)" }));
        const dialog = screen.getByRole("dialog", { name: "Download Form 3500 (PDF)" });
        expect(dialog).toHaveTextContent("MediAgent did not submit this report. You submit it to FDA.");
        fireEvent.click(within(dialog).getByRole("button", { name: "Download PDF" }));
        await waitFor(() => expect(mocks.downloadForm3500Pdf).toHaveBeenCalledWith("11111111-2222-4333-8444-555555555555"));
        expect(await screen.findByText(/Form 3500 PDF downloaded and audited/)).toBeInTheDocument();
        expect(click).toHaveBeenCalledTimes(1);
        click.mockRestore();
    });
});
