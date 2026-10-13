import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MedWatchDraftCard } from "@/components/features/medwatch-draft-card";
import { formatReviewTimestamp } from "@/components/features/review-time";
import type { MedWatchDraft, MedWatchFormData } from "@/services/clinicians";

const OUTCOME = "Outcome (leave empty if unknown)";

function formData(overrides: Partial<MedWatchFormData["event"]> = {}): MedWatchFormData {
    return {
        patient: {
            patient_identifier: "Synthetic Patient A",
            date_of_birth: "1988-04-03",
            sex: "female",
        },
        event: {
            description: "dizziness (patient-reported severity 2/10)",
            onset_date_or_time: "a few hours after starting the inhaler",
            outcome: "",
            seriousness: "",
            ...overrides,
        },
        suspect_product: {
            name: "fluticasone/salmeterol inhaler",
            dose: "1 puff",
            frequency: "twice daily",
            route: "inhaled",
            therapy_start_date: "2026-09-28",
            therapy_end_date: "",
        },
        concomitant_products: { products: "albuterol" },
        tests_and_history: { relevant_tests: "", other_relevant_history: "" },
        reporter: {
            name: "Synthetic Clinician",
            email: "clinician@example.com",
            specialty: "Internal medicine",
            clinic_name: "Synthetic Clinic",
        },
        clinical_review: {
            naranjo_score: 3,
            causality: "Possible",
            reportability_rationale: "Clinically significant new event.",
        },
    };
}

function makeDraft(overrides: Partial<MedWatchDraft> = {}): MedWatchDraft {
    return {
        id: "11111111-2222-4333-8444-555555555555",
        adrAssessmentId: "adr-1",
        patientId: "patient-1",
        formData: formData(),
        sourceEvidence: [
            {
                field_paths: ["event.description"],
                source_type: "patient_symptom_report",
                source_id: "symptom-1",
                attribution: "Patient-reported symptom",
                excerpt: "I became dizzy after starting the inhaler.",
                citation: "symptom_reports/symptom-1",
            },
        ],
        clinicianEditedFields: [],
        status: "draft",
        createdBy: "clinician-1",
        approvedBy: null,
        approvedAt: null,
        approvalNote: null,
        revision: 1,
        exportVersion: "medwatch-3500a-draft-v1",
        createdAt: "2026-10-09T10:00:00Z",
        updatedAt: "2026-10-09T10:00:00Z",
        ...overrides,
    };
}

function renderCard(draft: MedWatchDraft) {
    const onSave = vi.fn<(id: string, form: MedWatchFormData, revision: number) => Promise<void>>()
        .mockResolvedValue(undefined);
    const onApprove = vi.fn<(id: string, note: string, revision: number) => Promise<void>>()
        .mockResolvedValue(undefined);
    const onExport = vi.fn<(id: string) => Promise<void>>().mockResolvedValue(undefined);
    const element = (next: MedWatchDraft) => (
        <MedWatchDraftCard
            busy={false}
            draft={next}
            onApprove={onApprove}
            onExport={onExport}
            onSave={onSave}
        />
    );
    const view = render(element(draft));
    return {
        onSave,
        onApprove,
        onExport,
        rerender: (next: MedWatchDraft) => view.rerender(element(next)),
        container: view.container,
    };
}

function editOutcome(value: string) {
    fireEvent.change(screen.getByLabelText(OUTCOME), { target: { value } });
}

describe("MedWatchDraftCard refresh sync", () => {
    it("follows a new object at the same revision when the form is clean", () => {
        const card = renderCard(makeDraft());
        card.rerender(makeDraft({ formData: formData({ outcome: "Recovered" }) }));
        expect(screen.getByLabelText(OUTCOME)).toHaveValue("Recovered");
        expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
    });

    it("keeps edits across a same-revision refresh when the form is dirty", () => {
        const card = renderCard(makeDraft());
        editOutcome("Recovering");
        expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
        card.rerender(makeDraft());
        expect(screen.getByLabelText(OUTCOME)).toHaveValue("Recovering");
        expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    });

    it("follows a new revision when the form is clean", () => {
        const card = renderCard(makeDraft());
        card.rerender(
            makeDraft({ revision: 2, formData: formData({ seriousness: "Non-serious" }) }),
        );
        expect(screen.getByLabelText("Seriousness (leave empty if unknown)")).toHaveValue(
            "Non-serious",
        );
        expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
        expect(screen.getByText(/^Revision/)).toHaveTextContent("Revision 2");
    });

    it("keeps dirty edits on a new revision and saves against the old baseline", async () => {
        const card = renderCard(makeDraft());
        editOutcome("Recovering");
        card.rerender(
            makeDraft({ revision: 2, formData: formData({ seriousness: "Non-serious" }) }),
        );
        expect(screen.getByLabelText(OUTCOME)).toHaveValue("Recovering");
        expect(screen.getByLabelText("Seriousness (leave empty if unknown)")).toHaveValue("");
        expect(screen.getByText("Unsaved changes")).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
        await waitFor(() => expect(card.onSave).toHaveBeenCalledTimes(1));
        const [id, sent, revision] = card.onSave.mock.calls[0];
        expect(id).toBe("11111111-2222-4333-8444-555555555555");
        expect(sent.event.outcome).toBe("Recovering");
        // The stale baseline revision is sent so the server reports the revision conflict.
        expect(revision).toBe(1);
    });

    it("clears the badge when a save returns the saved values at a new revision", async () => {
        const card = renderCard(makeDraft());
        editOutcome("Recovering");
        fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
        await waitFor(() => expect(card.onSave).toHaveBeenCalledTimes(1));
        const saved = card.onSave.mock.calls[0][1];
        card.rerender(makeDraft({ revision: 2, formData: saved }));
        expect(screen.getByLabelText(OUTCOME)).toHaveValue("Recovering");
        expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();
        expect(screen.getByText(/^Revision/)).toHaveTextContent("Revision 2");
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
        expect(screen.getByLabelText(OUTCOME)).toBeDisabled();
        const time = container.querySelector("time");
        expect(time).toHaveAttribute("dateTime", approvedAt);
        expect(time).toHaveTextContent(formatReviewTimestamp(approvedAt));
        expect(
            screen.getByRole("button", { name: "Export approved JSON" }),
        ).toBeInTheDocument();
    });

    it("shows no seal for a draft awaiting approval", () => {
        renderCard(makeDraft());
        expect(screen.queryByText("Approved for export")).not.toBeInTheDocument();
        expect(screen.getByText("Needs approval")).toBeInTheDocument();
        expect(screen.getByText("Not submitted to FDA")).toBeInTheDocument();
    });

    it("enables approval only with the attestation and a non-blank note", async () => {
        const card = renderCard(makeDraft({ revision: 4 }));
        const approve = screen.getByRole("button", { name: "Approve for export" });
        expect(approve).toBeDisabled();
        fireEvent.change(screen.getByLabelText("Approval note"), {
            target: { value: "   " },
        });
        fireEvent.click(screen.getByRole("checkbox", { name: /I reviewed the draft/i }));
        expect(approve).toBeDisabled();
        fireEvent.change(screen.getByLabelText("Approval note"), {
            target: { value: "  Evidence and form reviewed.  " },
        });
        expect(approve).not.toBeDisabled();
        fireEvent.click(screen.getByRole("checkbox", { name: /I reviewed the draft/i }));
        expect(approve).toBeDisabled();
        fireEvent.click(screen.getByRole("checkbox", { name: /I reviewed the draft/i }));
        fireEvent.click(approve);
        await waitFor(() =>
            expect(card.onApprove).toHaveBeenCalledWith(
                "11111111-2222-4333-8444-555555555555",
                "Evidence and form reviewed.",
                4,
            ),
        );
    });

    it("reports a failed action inline and retains the form values", async () => {
        const card = renderCard(makeDraft());
        card.onSave.mockRejectedValueOnce(new Error("private provider diagnostic"));
        editOutcome("Recovering");
        fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
        expect(await screen.findByRole("alert")).toHaveTextContent(
            "Unable to complete this action. Your unsaved form values are retained.",
        );
        expect(screen.queryByText("private provider diagnostic")).not.toBeInTheDocument();
        expect(screen.getByLabelText(OUTCOME)).toHaveValue("Recovering");
        expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    });
});
