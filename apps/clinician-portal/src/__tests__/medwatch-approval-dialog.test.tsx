import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MedWatchApprovalDialog } from "@/components/features/medwatch-approval-dialog";
import { MedWatchRequestError, type MedWatchDraft } from "@/services/clinicians";
import { ATTESTATION_TEXT, makeDraft, makeForm } from "./fixtures/medwatch";

function renderDialog(draft: MedWatchDraft, unsaved = false) {
    const onApprove = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();
    render(
        <MedWatchApprovalDialog draft={draft} onApprove={onApprove} onClose={onClose} open unsaved={unsaved} />,
    );
    const dialog = screen.getByRole("dialog", { name: "Approve Form 3500 draft" });
    return { onApprove, onClose, dialog };
}

function fillNoteAndAttest(dialog: HTMLElement) {
    fireEvent.change(within(dialog).getByLabelText("Approval note"), {
        target: { value: "Evidence and form reviewed." },
    });
    fireEvent.click(within(dialog).getByRole("checkbox", { name: ATTESTATION_TEXT }));
}

const serious = makeForm({ outcomes: ["hospitalization"] });

describe("MedWatchApprovalDialog", () => {
    it("shows the attestation text returned by the API and sends its version", async () => {
        const { dialog, onApprove, onClose } = renderDialog(makeDraft({ formData: serious, revision: 5 }));
        expect(within(dialog).getByText(ATTESTATION_TEXT)).toBeInTheDocument();
        const confirm = within(dialog).getByRole("button", { name: "Confirm approval" });
        expect(confirm).toBeDisabled();
        fillNoteAndAttest(dialog);
        fireEvent.click(confirm);
        await waitFor(() =>
            expect(onApprove).toHaveBeenCalledWith("11111111-2222-4333-8444-555555555555", {
                approvalNote: "Evidence and form reviewed.",
                expectedRevision: 5,
                attestationVersion: "medwatch-3500-approval-v1",
                nonSeriousAttested: false,
                acknowledgedWarnings: [],
            }),
        );
        expect(onClose).toHaveBeenCalled();
    });

    it("lists missing items and blocks approval until they are complete", () => {
        const { dialog } = renderDialog(
            makeDraft({
                formData: serious,
                missingForApproval: [
                    { path: "section_g.occupation", code: "occupation_missing" },
                    { path: "section_b.event_date", code: "event_date_unconfirmed" },
                ],
            }),
        );
        const missing = within(dialog).getByRole("region", { name: "Missing for approval" });
        expect(within(missing).getByText("G3 Reporter occupation is missing")).toBeInTheDocument();
        expect(within(missing).getByText("B3 Confirm the best-estimate date of event")).toBeInTheDocument();
        fillNoteAndAttest(dialog);
        expect(within(dialog).getByRole("button", { name: "Confirm approval" })).toBeDisabled();
    });

    it("requires the D12 non-serious attestation when no B2 outcome is checked", async () => {
        const { dialog, onApprove } = renderDialog(
            makeDraft({
                missingForApproval: [
                    { path: "section_b.outcomes", code: "non_serious_attestation_required" },
                ],
            }),
        );
        // The attestation issue is cleared in the dialog, so it is not listed as missing.
        expect(within(dialog).queryByRole("region", { name: "Missing for approval" })).not.toBeInTheDocument();
        fillNoteAndAttest(dialog);
        const confirm = within(dialog).getByRole("button", { name: "Confirm approval" });
        expect(confirm).toBeDisabled();
        fireEvent.click(within(dialog).getByRole("checkbox", { name: /I attest that this event is not serious/ }));
        fireEvent.click(confirm);
        await waitFor(() =>
            expect(onApprove).toHaveBeenCalledWith(
                expect.any(String),
                expect.objectContaining({ nonSeriousAttested: true }),
            ),
        );
    });

    it("lists name warnings and sends them once acknowledged", async () => {
        const warnings = [
            { path: "section_b.narrative", kind: "patient_name" },
            { path: "section_f.others[0].name", kind: "clinic_name" },
        ];
        const { dialog, onApprove } = renderDialog(makeDraft({ formData: serious, nameWarnings: warnings }));
        const region = within(dialog).getByRole("region", { name: "Name warnings" });
        expect(
            within(region).getByText(
                "B5 Describe event, problem or product use/medication error: Contains the patient's name",
            ),
        ).toBeInTheDocument();
        expect(within(region).getByText("F Other product 1: Product name: Contains the clinic's name")).toBeInTheDocument();
        fillNoteAndAttest(dialog);
        const confirm = within(dialog).getByRole("button", { name: "Confirm approval" });
        expect(confirm).toBeDisabled();
        fireEvent.click(within(dialog).getByRole("checkbox", { name: /I reviewed these name warnings/ }));
        fireEvent.click(confirm);
        await waitFor(() =>
            expect(onApprove).toHaveBeenCalledWith(
                expect.any(String),
                expect.objectContaining({ acknowledgedWarnings: warnings }),
            ),
        );
    });

    it("blocks approval while the card holds unsaved edits", () => {
        const { dialog } = renderDialog(makeDraft({ formData: serious }), true);
        expect(within(dialog).getByRole("note")).toHaveTextContent("Save your changes before approving.");
        fillNoteAndAttest(dialog);
        expect(within(dialog).getByRole("button", { name: "Confirm approval" })).toBeDisabled();
    });

    it("shows a rejected approval inline without server text and stays open", async () => {
        const { dialog, onApprove, onClose } = renderDialog(makeDraft({ formData: serious }));
        onApprove.mockRejectedValueOnce(new MedWatchRequestError("MEDWATCH_APPROVAL_INCOMPLETE", 422));
        fillNoteAndAttest(dialog);
        fireEvent.click(within(dialog).getByRole("button", { name: "Confirm approval" }));
        expect(await within(dialog).findByRole("alert")).toHaveTextContent(
            /Approval is blocked until the missing items are complete/,
        );
        expect(onClose).not.toHaveBeenCalled();
        expect(within(dialog).getByLabelText("Approval note")).toHaveValue("Evidence and form reviewed.");
    });

    it("refuses to approve without an attestation from the API", () => {
        const { dialog } = renderDialog(makeDraft({ formData: serious, attestation: null }));
        expect(within(dialog).getByRole("alert")).toHaveTextContent(/attestation could not be loaded/);
        expect(within(dialog).getByRole("button", { name: "Confirm approval" })).toBeDisabled();
    });

    it("closes with Escape", () => {
        const { onClose } = renderDialog(makeDraft({ formData: serious }));
        fireEvent.keyDown(document, { key: "Escape" });
        expect(onClose).toHaveBeenCalled();
    });
});
