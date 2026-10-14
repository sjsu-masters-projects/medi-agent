import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MedWatchDraftCard } from "@/components/features/medwatch-draft-card";
import { formatReviewTimestamp } from "@/components/features/review-time";
import type {
    MedWatchApprovalInput,
    MedWatchDraft,
    MedWatchFormData,
} from "@/services/clinicians";
import { ATTESTATION_TEXT, makeDraft, makeForm } from "./fixtures/medwatch";

const NARRATIVE = "B5 Describe event, problem or product use/medication error";

function renderCard(draft: MedWatchDraft) {
    const onSave = vi.fn<(id: string, form: MedWatchFormData, revision: number) => Promise<void>>()
        .mockResolvedValue(undefined);
    const onApprove = vi.fn<(id: string, input: MedWatchApprovalInput) => Promise<void>>()
        .mockResolvedValue(undefined);
    const onExport = vi.fn<(id: string) => Promise<void>>().mockResolvedValue(undefined);
    const onDiscard = vi.fn().mockResolvedValue(undefined);
    const element = (next: MedWatchDraft) => (
        <MedWatchDraftCard
            busy={false}
            draft={next}
            onApprove={onApprove}
            onDiscard={onDiscard}
            onExport={onExport}
            onSave={onSave}
        />
    );
    const view = render(element(draft));
    return {
        onSave,
        onApprove,
        onExport,
        onDiscard,
        rerender: (next: MedWatchDraft) => view.rerender(element(next)),
        container: view.container,
    };
}

function editNarrative(value: string) {
    fireEvent.change(screen.getByLabelText(NARRATIVE), { target: { value } });
}

describe("MedWatchDraftCard refresh sync", () => {
    it("follows a new object at the same revision when the form is clean", () => {
        const card = renderCard(makeDraft());
        card.rerender(makeDraft({ formData: makeForm({ narrative: "Recovered dizziness." }) }));
        expect(screen.getByLabelText(NARRATIVE)).toHaveValue("Recovered dizziness.");
        expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
    });

    it("keeps edits across a same-revision refresh when the form is dirty", () => {
        const card = renderCard(makeDraft());
        editNarrative("Recovering");
        expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
        card.rerender(makeDraft());
        expect(screen.getByLabelText(NARRATIVE)).toHaveValue("Recovering");
        expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    });

    it("follows a new revision when the form is clean", () => {
        const card = renderCard(makeDraft());
        card.rerender(makeDraft({ revision: 2, formData: makeForm({ outcomes: ["hospitalization"] }) }));
        expect(
            screen.getByRole("checkbox", { name: "Hospitalization (Initial or prolonged)" }),
        ).toBeChecked();
        expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
        expect(screen.getByText(/^Revision/)).toHaveTextContent("Revision 2");
    });

    it("keeps dirty edits on a new revision and saves against the old baseline", async () => {
        const card = renderCard(makeDraft());
        editNarrative("Recovering");
        card.rerender(makeDraft({ revision: 2, formData: makeForm({ outcomes: ["hospitalization"] }) }));
        expect(screen.getByLabelText(NARRATIVE)).toHaveValue("Recovering");
        expect(
            screen.getByRole("checkbox", { name: "Hospitalization (Initial or prolonged)" }),
        ).not.toBeChecked();
        expect(screen.getByText("Unsaved changes")).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
        await waitFor(() => expect(card.onSave).toHaveBeenCalledTimes(1));
        const [id, sent, revision] = card.onSave.mock.calls[0];
        expect(id).toBe("11111111-2222-4333-8444-555555555555");
        expect(sent.section_b.narrative).toBe("Recovering");
        // The stale baseline revision is sent so the server reports the revision conflict.
        expect(revision).toBe(1);
    });

    it("clears the badge when a save returns the saved values at a new revision", async () => {
        const card = renderCard(makeDraft());
        editNarrative("Recovering");
        fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
        await waitFor(() => expect(card.onSave).toHaveBeenCalledTimes(1));
        const saved = card.onSave.mock.calls[0][1];
        card.rerender(makeDraft({ revision: 2, formData: saved }));
        expect(screen.getByLabelText(NARRATIVE)).toHaveValue("Recovering");
        expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
        expect(screen.getByText(/^Revision/)).toHaveTextContent("Revision 2");
    });
});

describe("MedWatchDraftCard Form 3500 sections", () => {
    it("groups the editable items by Form 3500 section", () => {
        renderCard(makeDraft());
        for (const legend of [
            "A. Patient information",
            "B. Adverse event or product problem",
            "D. Suspect products",
            "F. Other (concomitant) medical products",
            "G. Reporter",
            "MediAgent review (not part of Form 3500)",
        ]) {
            expect(screen.getByRole("group", { name: legend })).toBeInTheDocument();
        }
        expect(screen.getByLabelText("A1 Patient identifier")).toHaveValue("SP-K7QD");
        expect(screen.getByLabelText("A3 Sex")).toHaveValue("F");
        expect(screen.getByText("Best estimate, confirm")).toBeInTheDocument();
        expect(screen.getByLabelText("Other product 1: name")).toHaveValue("albuterol");
    });

    it("saves structured values from selects, checkbox groups and confirmations", async () => {
        const card = renderCard(makeDraft());
        fireEvent.click(screen.getByRole("checkbox", { name: "I confirm the date of event" }));
        fireEvent.change(screen.getByLabelText("G3 Occupation"), { target: { value: "Physician" } });
        fireEvent.change(screen.getByLabelText("G2 Health professional"), { target: { value: "yes" } });
        fireEvent.click(screen.getByRole("checkbox", { name: "Death" }));
        fireEvent.change(screen.getByLabelText("B2 Date of death"), { target: { value: "2026-10-05" } });
        fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
        await waitFor(() => expect(card.onSave).toHaveBeenCalledTimes(1));
        const sent = card.onSave.mock.calls[0][1];
        expect(sent.section_b.event_date_confirmed).toBe(true);
        expect(sent.section_b.outcomes).toEqual(["death"]);
        expect(sent.section_b.death_date).toBe("2026-10-05");
        expect(sent.section_g.occupation).toBe("Physician");
        expect(sent.section_g.health_professional).toBe("yes");
        expect(screen.queryByText("Best estimate, confirm")).not.toBeInTheDocument();
    });

    it("clears the date of death when Death is unchecked", async () => {
        const card = renderCard(makeDraft());
        fireEvent.click(screen.getByRole("checkbox", { name: "Death" }));
        fireEvent.change(screen.getByLabelText("B2 Date of death"), { target: { value: "2026-10-05" } });
        fireEvent.click(screen.getByRole("checkbox", { name: "Death" }));
        expect(screen.queryByLabelText("B2 Date of death")).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
        await waitFor(() => expect(card.onSave).toHaveBeenCalledTimes(1));
        expect(card.onSave.mock.calls[0][1].section_b.death_date).toBeNull();
    });

    it("requires other text only while Other is the frequency", async () => {
        const card = renderCard(makeDraft());
        const product1 = screen.getByRole("group", { name: "Suspect product 1" });
        expect(within(product1).queryByLabelText("Other frequency")).not.toBeInTheDocument();
        fireEvent.change(within(product1).getByLabelText("Frequency"), { target: { value: "Other" } });
        fireEvent.change(within(product1).getByLabelText("Other frequency"), {
            target: { value: "every 48 hours" },
        });
        fireEvent.change(within(product1).getByLabelText("Frequency"), { target: { value: "TID" } });
        expect(within(product1).queryByLabelText("Other frequency")).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
        await waitFor(() => expect(card.onSave).toHaveBeenCalledTimes(1));
        const product = card.onSave.mock.calls[0][1].section_d.product_1;
        expect(product.frequency).toBe("TID");
        expect(product.frequency_other).toBe("");
    });

    it("adds an optional second suspect product and caps other products at ten", () => {
        renderCard(makeDraft());
        fireEvent.click(screen.getByRole("button", { name: "Add suspect product 2" }));
        expect(screen.getByRole("group", { name: "Suspect product 2" })).toBeInTheDocument();
        for (let count = 1; count < 10; count += 1) {
            fireEvent.click(screen.getByRole("button", { name: "Add other product" }));
        }
        expect(screen.getByLabelText("Other product 10: name")).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Add other product" })).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Remove suspect product 2" }));
        expect(screen.queryByRole("group", { name: "Suspect product 2" })).not.toBeInTheDocument();
    });

    it("shows name warnings beside the field they belong to", () => {
        renderCard(
            makeDraft({
                nameWarnings: [
                    { path: "section_b.narrative", kind: "patient_name" },
                    { path: "section_f.others[0].name", kind: "clinic_name" },
                ],
            }),
        );
        expect(screen.getByLabelText(NARRATIVE)).toHaveAccessibleDescription(
            "Contains the patient's name",
        );
        expect(screen.getByLabelText("Other product 1: name")).toHaveAccessibleDescription(
            "Contains the clinic's name",
        );
        expect(screen.getByLabelText("B7 Other relevant history")).not.toHaveAccessibleDescription();
    });

    it("lists the items missing for approval before the dialog opens", () => {
        renderCard(
            makeDraft({
                missingForApproval: [
                    { path: "section_b.event_date", code: "event_date_unconfirmed" },
                    { path: "section_g.occupation", code: "occupation_missing" },
                ],
            }),
        );
        const missing = screen.getByRole("region", { name: "Missing for approval" });
        expect(within(missing).getByText("B3 Confirm the best-estimate date of event")).toBeInTheDocument();
        expect(within(missing).getByText("G3 Reporter occupation is missing")).toBeInTheDocument();
    });
});

describe("MedWatchDraftCard status and approval", () => {
    it("shows the approval seal only for a reviewed draft", () => {
        const approvedAt = "2026-10-09T11:00:00Z";
        const { container } = renderCard(
            makeDraft({
                status: "reviewed",
                revision: 3,
                approvedBy: "clinician-1",
                approvedAt,
                approvalNote: "Evidence and form reviewed.",
            }),
        );
        expect(screen.getByText("Approved for export")).toBeInTheDocument();
        expect(screen.getByText("Not submitted to FDA")).toBeInTheDocument();
        expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
        expect(screen.queryByText("Needs approval")).not.toBeInTheDocument();
        expect(screen.getByLabelText(NARRATIVE)).toBeDisabled();
        const time = container.querySelector("time");
        expect(time).toHaveAttribute("dateTime", approvedAt);
        expect(time).toHaveTextContent(formatReviewTimestamp(approvedAt));
        expect(screen.getByRole("button", { name: "Export approved JSON" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Download Form 3500 (PDF)" })).toBeInTheDocument();
        expect(screen.getByText("MediAgent did not submit this report.")).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Save draft" })).not.toBeInTheDocument();
    });

    it("shows no seal and no AI chip for a draft awaiting approval", () => {
        renderCard(makeDraft());
        expect(screen.queryByText("Approved for export")).not.toBeInTheDocument();
        expect(screen.getByText("Needs approval")).toBeInTheDocument();
        expect(screen.getByText("Not submitted to FDA")).toBeInTheDocument();
        expect(screen.queryByText(/AI-extracted/)).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Download Form 3500 (PDF)" })).not.toBeInTheDocument();
    });

    it("approves through the dialog with the attestation version and a note", async () => {
        const card = renderCard(makeDraft({ revision: 4, formData: makeForm({ outcomes: ["hospitalization"] }) }));
        fireEvent.click(screen.getByRole("button", { name: "Approve for export" }));
        const dialog = screen.getByRole("dialog", { name: "Approve Form 3500 draft" });
        const confirm = within(dialog).getByRole("button", { name: "Confirm approval" });
        expect(confirm).toBeDisabled();
        fireEvent.change(within(dialog).getByLabelText("Approval note"), {
            target: { value: "   " },
        });
        fireEvent.click(within(dialog).getByRole("checkbox", { name: /I have reviewed this draft/i }));
        expect(confirm).toBeDisabled();
        fireEvent.change(within(dialog).getByLabelText("Approval note"), {
            target: { value: "  Evidence and form reviewed.  " },
        });
        expect(confirm).not.toBeDisabled();
        expect(within(dialog).getByText(ATTESTATION_TEXT)).toBeInTheDocument();
        fireEvent.click(confirm);
        await waitFor(() =>
            expect(card.onApprove).toHaveBeenCalledWith("11111111-2222-4333-8444-555555555555", {
                approvalNote: "Evidence and form reviewed.",
                expectedRevision: 4,
                attestationVersion: "medwatch-3500-approval-v1",
                nonSeriousAttested: false,
                acknowledgedWarnings: [],
            }),
        );
        await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    });

    it("reports a failed action inline and retains the form values", async () => {
        const card = renderCard(makeDraft());
        card.onSave.mockRejectedValueOnce(new Error("private provider diagnostic"));
        editNarrative("Recovering");
        fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
        expect(await screen.findByRole("alert")).toHaveTextContent(
            "Unable to complete this action. Your unsaved form values are retained.",
        );
        expect(screen.queryByText("private provider diagnostic")).not.toBeInTheDocument();
        expect(screen.getByLabelText(NARRATIVE)).toHaveValue("Recovering");
        expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    });
});

describe("MedWatchDraftCard earlier drafts", () => {
    it("explains why an approved earlier draft has no PDF and keeps JSON and preview", () => {
        renderCard(
            makeDraft({
                status: "reviewed",
                revision: 3,
                approvedAt: "2026-10-09T11:00:00Z",
                pdfAvailable: false,
            }),
        );
        expect(screen.getByRole("note")).toHaveTextContent(/cannot be downloaded as Form 3500/);
        expect(screen.queryByRole("button", { name: "Download Form 3500 (PDF)" })).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Export approved JSON" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Preview Form 3500" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Discard draft" })).toBeInTheDocument();
    });
});
