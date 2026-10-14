import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
    DiscardDraftDialog,
    SubmissionRecordDialog,
} from "@/components/features/medwatch-record-dialogs";
import { MedWatchRequestError } from "@/services/clinicians";
import { approvedDraft, makeDraft, submittedDraft } from "./fixtures/medwatch";

describe("SubmissionRecordDialog", () => {
    beforeEach(() => {
        vi.useFakeTimers({ toFake: ["Date"] });
        vi.setSystemTime(new Date("2026-10-12T19:00:00Z"));
    });
    afterEach(() => vi.useRealTimers());

    function renderRecord() {
        const onRecord = vi.fn().mockResolvedValue(undefined);
        const onClose = vi.fn();
        render(<SubmissionRecordDialog draft={approvedDraft()} onClose={onClose} onRecord={onRecord} open />);
        return { onRecord, onClose, dialog: screen.getByRole("dialog", { name: "Record FDA submission" }) };
    }

    it("records the date, method, reference and attestation with the expected revision", async () => {
        const { dialog, onRecord, onClose } = renderRecord();
        const date = within(dialog).getByLabelText("Date submitted to FDA");
        expect(date).toHaveAttribute("max", "2026-10-12");
        expect(date).toHaveAttribute("min", "2026-10-09");
        const save = within(dialog).getByRole("button", { name: "Record submission" });
        fireEvent.change(date, { target: { value: "2026-10-11" } });
        fireEvent.change(within(dialog).getByLabelText("Submission method"), { target: { value: "fax" } });
        fireEvent.change(within(dialog).getByLabelText("FDA confirmation or reference number (optional)"), {
            target: { value: "MW-0000002" },
        });
        expect(save).toBeDisabled();
        fireEvent.click(within(dialog).getByRole("checkbox", { name: /I submitted this report to FDA myself/ }));
        fireEvent.click(save);
        await waitFor(() =>
            expect(onRecord).toHaveBeenCalledWith("11111111-2222-4333-8444-555555555555", {
                submittedOn: "2026-10-11",
                method: "fax",
                methodDetail: "",
                fdaReference: "MW-0000002",
                expectedRevision: 3,
            }),
        );
        expect(onClose).toHaveBeenCalled();
    });

    it("rejects a future date or one before approval", () => {
        const { dialog } = renderRecord();
        const date = within(dialog).getByLabelText("Date submitted to FDA");
        fireEvent.change(date, { target: { value: "2026-10-13" } });
        expect(within(dialog).getByText("The submission date cannot be in the future.")).toBeInTheDocument();
        fireEvent.change(date, { target: { value: "2026-10-08" } });
        expect(within(dialog).getByText("The submission date cannot be before the draft was approved.")).toBeInTheDocument();
        fireEvent.change(within(dialog).getByLabelText("Submission method"), { target: { value: "mail" } });
        fireEvent.click(within(dialog).getByRole("checkbox", { name: /I submitted this report/ }));
        expect(within(dialog).getByRole("button", { name: "Record submission" })).toBeDisabled();
    });

    it("requires a description when the method is Other", () => {
        const { dialog } = renderRecord();
        fireEvent.change(within(dialog).getByLabelText("Date submitted to FDA"), { target: { value: "2026-10-11" } });
        fireEvent.change(within(dialog).getByLabelText("Submission method"), { target: { value: "other" } });
        fireEvent.click(within(dialog).getByRole("checkbox", { name: /I submitted this report/ }));
        const save = within(dialog).getByRole("button", { name: "Record submission" });
        expect(save).toBeDisabled();
        fireEvent.change(within(dialog).getByLabelText("Describe the method"), { target: { value: "Courier" } });
        expect(save).toBeEnabled();
    });

    it("shows a failed record inline by code and stays open", async () => {
        const { dialog, onRecord, onClose } = renderRecord();
        onRecord.mockRejectedValueOnce(new MedWatchRequestError("VALIDATION_ERROR", 409));
        fireEvent.change(within(dialog).getByLabelText("Date submitted to FDA"), { target: { value: "2026-10-11" } });
        fireEvent.change(within(dialog).getByLabelText("Submission method"), { target: { value: "mail" } });
        fireEvent.click(within(dialog).getByRole("checkbox", { name: /I submitted this report/ }));
        fireEvent.click(within(dialog).getByRole("button", { name: "Record submission" }));
        expect(await within(dialog).findByRole("alert")).toHaveTextContent(/changed since you opened it/);
        expect(onClose).not.toHaveBeenCalled();
    });

    it("amends the current record with a required reason", async () => {
        const onAmend = vi.fn().mockResolvedValue(undefined);
        render(<SubmissionRecordDialog draft={submittedDraft()} onAmend={onAmend} onClose={vi.fn()} open />);
        const dialog = screen.getByRole("dialog", { name: "Amend submission record" });
        expect(within(dialog).getByLabelText("Date submitted to FDA")).toHaveValue("2026-10-10");
        expect(within(dialog).getByLabelText("Submission method")).toHaveValue("medwatch_online");
        expect(within(dialog).queryByRole("checkbox")).not.toBeInTheDocument();
        const save = within(dialog).getByRole("button", { name: "Save amendment" });
        expect(save).toBeDisabled();
        fireEvent.change(within(dialog).getByLabelText("Date submitted to FDA"), { target: { value: "2026-10-09" } });
        fireEvent.change(within(dialog).getByLabelText("Reason for amendment"), { target: { value: "Wrong date entered" } });
        fireEvent.click(save);
        await waitFor(() =>
            expect(onAmend).toHaveBeenCalledWith("11111111-2222-4333-8444-555555555555", {
                submittedOn: "2026-10-09",
                method: "medwatch_online",
                methodDetail: "",
                fdaReference: "MW-0000001",
                amendsId: "submission-1",
                reason: "Wrong date entered",
            }),
        );
    });
});

describe("DiscardDraftDialog", () => {
    it("asks for a reason, says the assessment returns to review and sends the revision", async () => {
        const onDiscard = vi.fn().mockResolvedValue(undefined);
        const onClose = vi.fn();
        render(<DiscardDraftDialog draft={makeDraft({ revision: 2 })} onClose={onClose} onDiscard={onDiscard} open />);
        const dialog = screen.getByRole("dialog", { name: "Discard MedWatch draft" });
        expect(dialog).toHaveTextContent(/ADR assessment returns to\s+review/);
        const discard = within(dialog).getByRole("button", { name: "Discard draft" });
        expect(discard).toBeDisabled();
        fireEvent.change(within(dialog).getByLabelText("Reason for discarding"), { target: { value: "   " } });
        expect(discard).toBeDisabled();
        fireEvent.change(within(dialog).getByLabelText("Reason for discarding"), {
            target: { value: " Prepared for the wrong suspect product. " },
        });
        fireEvent.click(discard);
        await waitFor(() =>
            expect(onDiscard).toHaveBeenCalledWith("11111111-2222-4333-8444-555555555555", {
                reason: "Prepared for the wrong suspect product.",
                expectedRevision: 2,
            }),
        );
        expect(onClose).toHaveBeenCalled();
    });

    it("shows a refused discard inline", async () => {
        const onDiscard = vi.fn().mockRejectedValue(new MedWatchRequestError("VALIDATION_ERROR", 422));
        render(<DiscardDraftDialog draft={makeDraft()} onClose={vi.fn()} onDiscard={onDiscard} open />);
        fireEvent.change(screen.getByLabelText("Reason for discarding"), { target: { value: "Duplicate" } });
        fireEvent.click(screen.getByRole("button", { name: "Discard draft" }));
        expect(await screen.findByRole("alert")).toHaveTextContent(/not allowed for the draft in its current state/);
    });
});
