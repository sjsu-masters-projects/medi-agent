import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi, beforeEach } from "vitest";
import { PatientDocumentsPanel } from "@/components/features/patient-documents-panel";
import {
    type ExtractedDocumentFact,
    approveDocumentReview,
    fetchExtractedDocumentFacts,
    fetchClinicianDocumentSource,
    rejectDocumentReview,
    retryClinicianDocumentSummary,
} from "@/services/clinicians";
import { simulateNonUsDefaultLocale } from "./fixtures/locale";

vi.mock("@/services/clinicians", () => ({
    approveDocumentReview: vi.fn(),
    fetchExtractedDocumentFacts: vi.fn(),
    fetchClinicianDocumentSource: vi.fn(),
    rejectDocumentReview: vi.fn(),
    retryClinicianDocumentIngestion: vi.fn(),
    retryClinicianDocumentSummary: vi.fn(),
}));

vi.mock("@/components/features/document-summary", () => ({
    DocumentSummary: ({ summaryText }: { summaryText: string }) => (
        <div>{summaryText}</div>
    ),
}));

vi.mock("@/components/features/document-source-viewer", () => ({
    DocumentSourceViewer: ({ sourceUrl }: { sourceUrl?: string | null }) => (
        <div data-testid="source-viewer">{sourceUrl}</div>
    ),
}));

function fieldLabels(scope: ParentNode = document): string[] {
    return Array.from(scope.querySelectorAll("dt")).map((term) => term.textContent ?? "");
}

function candidate(name: string | RegExp): HTMLElement {
    return screen.getByText(name).closest("button") as HTMLElement;
}

async function openFacts(facts: ExtractedDocumentFact[]) {
    vi.mocked(fetchExtractedDocumentFacts).mockResolvedValue(facts);
    vi.mocked(fetchClinicianDocumentSource).mockResolvedValue({
        file_name: "results.pdf",
        file_url: "https://example.test/signed-results.pdf",
        mime_type: "application/pdf",
        preview_status: "not_required",
    });
    render(
        <PatientDocumentsPanel
            documents={[{ id: "doc-results", fileName: "results.pdf", documentType: "lab_report", parseStatus: "completed", createdAt: "2026-10-12T12:00:00Z", uploadedByRole: "clinician" }]}
            onRefresh={vi.fn()}
            patientId="patient-results"
        />,
    );
    fireEvent.click(screen.getByRole("button", { name: /review extracted facts/i }));
    await screen.findByRole("list", { name: "Extracted fact candidates" });
}

function fact(id: string, fact_type: string, value: Record<string, unknown>, excerpt = "synthetic excerpt"): ExtractedDocumentFact {
    return { id, fact_type, value, confidence_score: 0.9, review_state: "pending_review", citations: [{ excerpt, location: { page: 1 } }] };
}

describe("PatientDocumentsPanel", () => {
    it("focuses the exact document fragment and explains an unavailable document", () => {
        window.history.replaceState(null, "", "#document-linked");
        const view = render(<PatientDocumentsPanel documents={[{ id: "linked", fileName: "synthetic.pdf", documentType: "other", parseStatus: "completed", uploadedByRole: "clinician", createdAt: "2026-10-11T12:00:00Z" }]} patientId="synthetic" onRefresh={vi.fn()} />);
        expect(document.getElementById("document-linked")).toHaveFocus();
        act(() => { window.history.replaceState(null, "", "#document-missing"); window.dispatchEvent(new Event("hashchange")); });
        expect(screen.getByText(/linked document is unavailable/)).toBeInTheDocument();
        window.history.replaceState(null, "", window.location.pathname);
        view.unmount();
    });
    it("explains skipped duplicates without promising facts or an explanation retry", () => {
        render(<PatientDocumentsPanel documents={[{
            id: "duplicate-doc", fileName: "duplicate.pdf", documentType: "other",
            parseStatus: "duplicate", summaryStatus: "not_required",
            createdAt: "2026-10-10T18:00:00Z", uploadedByRole: "patient", reviewStatus: "pending",
        }]} onRefresh={vi.fn()} patientId="synthetic-patient" />);
        expect(screen.getByText("Duplicate upload — extraction skipped")).toBeInTheDocument();
        expect(screen.getByText(/created no new extracted facts or care-plan proposals/)).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Review extracted facts" })).not.toBeInTheDocument();
        expect(screen.queryByText(/No extracted information in this document/)).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Open source document" })).toBeInTheDocument();
    });

    beforeEach(() => {
        vi.mocked(approveDocumentReview).mockReset();
        vi.mocked(fetchExtractedDocumentFacts).mockReset();
        vi.mocked(fetchClinicianDocumentSource).mockReset();
        vi.mocked(rejectDocumentReview).mockReset();
        vi.mocked(retryClinicianDocumentSummary).mockReset();
    });

    it("renders review metadata for reviewed patient uploads", () => {
        render(
            <PatientDocumentsPanel
                documents={[
                    {
                        id: "doc-1",
                        fileName: "lab.pdf",
                        documentType: "lab_report",
                        parseStatus: "completed",
                        aiSummary: "Summary text",
                        createdAt: "2026-04-21T10:00:00Z",
                        uploadedByRole: "patient",
                        reviewStatus: "rejected",
                        reviewedAt: "2026-04-22T09:00:00Z",
                        reviewNote: "Looks valid",
                        reviewer: {
                            id: "clinician-1",
                            firstName: "Mina",
                            lastName: "Shah",
                        },
                    },
                ]}
                onRefresh={vi.fn()}
                patientId="patient-1"
            />,
        );

        expect(screen.getByText("lab.pdf")).toBeInTheDocument();
        expect(screen.getByText(/Review rejected/i)).toBeInTheDocument();
        expect(screen.getByText(/by Mina Shah/i)).toBeInTheDocument();
        expect(screen.getByText(/Review note: Looks valid/i)).toBeInTheDocument();
    });

    it("approves pending patient uploads and refreshes the deep dive", async () => {
        const onRefresh = vi.fn();
        vi.mocked(approveDocumentReview).mockResolvedValue({
            status: "reviewed",
            document_id: "doc-2",
            patient_id: "patient-2",
            review_status: "approved",
            reviewed_by: "clinician-1",
            reviewed_at: "2026-04-23T10:00:00Z",
            review_note: undefined,
        });

        render(
            <PatientDocumentsPanel
                documents={[
                    {
                        id: "doc-2",
                        fileName: "upload.pdf",
                        documentType: "other",
                        parseStatus: "pending",
                        createdAt: "2026-04-21T10:00:00Z",
                        uploadedByRole: "patient",
                        reviewStatus: "pending",
                    },
                ]}
                onRefresh={onRefresh}
                patientId="patient-2"
            />,
        );

        fireEvent.click(screen.getByRole("button", { name: "Approve" }));

        await waitFor(() =>
            expect(approveDocumentReview).toHaveBeenCalledWith("patient-2", "doc-2"),
        );
        await waitFor(() => expect(onRefresh).toHaveBeenCalled());
    });

    it("loads a fresh, authorized source URL only after the clinician opens a document", async () => {
        vi.mocked(fetchClinicianDocumentSource).mockResolvedValue({
            file_name: "lab.pdf",
            file_url: "https://example.test/signed-lab.pdf",
            mime_type: "application/pdf",
            preview_status: "not_required",
        });

        render(
            <PatientDocumentsPanel
                documents={[
                    {
                        id: "doc-source",
                        fileName: "lab.pdf",
                        documentType: "lab_report",
                        parseStatus: "completed",
                        createdAt: "2026-04-21T10:00:00Z",
                        uploadedByRole: "patient",
                        reviewStatus: "approved",
                    },
                ]}
                onRefresh={vi.fn()}
                patientId="patient-source"
            />,
        );

        fireEvent.click(screen.getByRole("button", { name: /open source document/i }));

        await waitFor(() =>
            expect(fetchClinicianDocumentSource).toHaveBeenCalledWith("patient-source", "doc-source"),
        );
        expect(await screen.findByTestId("source-viewer")).toHaveTextContent("signed-lab.pdf");
    });

    it("reviews formatted pending facts beside the protected source preview", async () => {
        vi.mocked(fetchExtractedDocumentFacts).mockResolvedValue([
            {
                id: "fact-1",
                fact_type: "medication",
                value: {
                    name: "Lisinopril",
                    dosage: "10 mg",
                    route: "oral",
                    instructions: "Take once daily.",
                },
                confidence_score: 0.92,
                review_state: "pending_review",
                citations: [
                    {
                        excerpt: "Lisinopril 10 mg by mouth daily",
                        location: { page: 2 },
                    },
                ],
            },
        ]);
        vi.mocked(fetchClinicianDocumentSource).mockResolvedValue({
            file_name: "follow-up.pdf",
            file_url: "https://example.test/signed-follow-up.pdf",
            mime_type: "application/pdf",
            preview_status: "not_required",
        });

        render(
            <PatientDocumentsPanel
                documents={[
                    {
                        id: "doc-facts",
                        fileName: "follow-up.pdf",
                        documentType: "other",
                        parseStatus: "completed",
                        createdAt: "2026-04-21T10:00:00Z",
                        uploadedByRole: "clinician",
                    },
                ]}
                onRefresh={vi.fn()}
                patientId="patient-facts"
            />,
        );

        fireEvent.click(screen.getByRole("button", { name: /review extracted facts/i }));

        await waitFor(() =>
            expect(fetchExtractedDocumentFacts).toHaveBeenCalledWith("patient-facts", "doc-facts"),
        );
        expect(await screen.findByText("Pending clinician review")).toBeInTheDocument();
        expect(fieldLabels()).toEqual(["Medication", "Dose", "Route", "Instructions"]);
        expect(screen.getByText("10 mg")).toBeInTheDocument();
        expect(screen.getByText(/page 2/i)).toBeInTheDocument();
        expect(screen.getByTestId("source-viewer")).toHaveTextContent("signed-follow-up.pdf");
    });

    it("rejects pending patient uploads with a note and refreshes the deep dive", async () => {
        const onRefresh = vi.fn();
        vi.mocked(rejectDocumentReview).mockResolvedValue({
            status: "reviewed",
            document_id: "doc-3",
            patient_id: "patient-3",
            review_status: "rejected",
            reviewed_by: "clinician-1",
            reviewed_at: "2026-04-23T10:00:00Z",
            review_note: "Unreadable image",
        });

        render(
            <PatientDocumentsPanel
                documents={[
                    {
                        id: "doc-3",
                        fileName: "image.png",
                        documentType: "other",
                        parseStatus: "completed",
                        createdAt: "2026-04-21T10:00:00Z",
                        uploadedByRole: "patient",
                        reviewStatus: "pending",
                    },
                ]}
                onRefresh={onRefresh}
                patientId="patient-3"
            />,
        );

        fireEvent.click(screen.getByRole("button", { name: "Reject" }));
        fireEvent.change(screen.getByRole("textbox", { name: /review note/i }), {
            target: { value: "Unreadable image" },
        });
        fireEvent.click(screen.getByRole("button", { name: /Confirm rejection/i }));

        await waitFor(() =>
            expect(rejectDocumentReview).toHaveBeenCalledWith(
                "patient-3",
                "doc-3",
                "Unreadable image",
            ),
        );
        await waitFor(() => expect(onRefresh).toHaveBeenCalled());
    });

    it("offers a retry when the patient explanation is unavailable", async () => {
        const onRefresh = vi.fn();
        vi.mocked(retryClinicianDocumentSummary).mockResolvedValue({
            id: "doc-1",
            fileName: "lab.pdf",
            documentType: "lab_report",
            parseStatus: "completed",
            summaryStatus: "pending",
            createdAt: "2026-04-21T10:00:00Z",
            uploadedByRole: "patient",
        });

        render(
            <PatientDocumentsPanel
                documents={[
                    {
                        id: "doc-1",
                        fileName: "lab.pdf",
                        documentType: "lab_report",
                        parseStatus: "completed",
                        summaryStatus: "failed",
                        summaryFailureCode: "provider_unavailable",
                        createdAt: "2026-04-21T10:00:00Z",
                        uploadedByRole: "patient",
                    },
                ]}
                onRefresh={onRefresh}
                patientId="patient-1"
            />,
        );

        // The clinician is told the clinical record is intact, not just that a box is empty.
        expect(
            screen.getByText(/Extraction and review candidates are unaffected/i),
        ).toBeInTheDocument();

        fireEvent.click(
            screen.getByRole("button", { name: /retry patient explanation/i }),
        );

        await waitFor(() => {
            expect(retryClinicianDocumentSummary).toHaveBeenCalledWith(
                "patient-1",
                "doc-1",
            );
        });
        expect(onRefresh).toHaveBeenCalled();
    });

    it("does not offer a retry for a document with nothing to explain", () => {
        render(
            <PatientDocumentsPanel
                documents={[
                    {
                        id: "doc-2",
                        fileName: "blank.pdf",
                        documentType: "lab_report",
                        parseStatus: "completed",
                        summaryStatus: "not_required",
                        createdAt: "2026-04-21T10:00:00Z",
                        uploadedByRole: "patient",
                    },
                ]}
                onRefresh={vi.fn()}
                patientId="patient-1"
            />,
        );

        expect(
            screen.getByText(/needs a patient explanation/i),
        ).toBeInTheDocument();
        expect(
            screen.queryByRole("button", { name: /retry patient explanation/i }),
        ).not.toBeInTheDocument();
    });

    it("shows an automatic retry state without offering a duplicate retry", () => {
        render(
            <PatientDocumentsPanel
                documents={[
                    {
                        id: "doc-retrying",
                        fileName: "follow-up.tiff",
                        documentType: "other",
                        parseStatus: "completed",
                        summaryStatus: "pending",
                        summaryFailureCode: "provider_unavailable",
                        summaryAttempts: 1,
                        summaryNextAttemptAt: "2026-04-21T10:02:00Z",
                        createdAt: "2026-04-21T10:00:00Z",
                        uploadedByRole: "clinician",
                    },
                ]}
                onRefresh={vi.fn()}
                patientId="patient-1"
            />,
        );

        expect(screen.getByText(/will retry automatically \(attempt 1 of 3\)/i)).toBeInTheDocument();
        expect(
            screen.queryByRole("button", { name: /retry patient explanation/i }),
        ).not.toBeInTheDocument();
    });

    describe("extracted fact types", () => {
        it("labels a condition as a condition, not a medication", async () => {
            await openFacts([fact("condition-1", "condition", { name: "Type 2 diabetes mellitus", status: "Active" })]);
            const card = candidate("Type 2 diabetes mellitus");
            expect(within(card).getByText("Condition", { selector: "p" })).toBeInTheDocument();
            expect(fieldLabels(card)).toEqual(["Condition", "Status"]);
            expect(within(card).queryByText("Medication")).not.toBeInTheDocument();
        });

        it("gives every extracted type a readable heading and per-type field labels", async () => {
            await openFacts([
                fact("vital-1", "vital_sign", { name: "Blood pressure", value: "142/88", unit: "mmHg" }),
                fact("imm-1", "immunization", { vaccine: "Influenza", administered_at: "2026-09-30" }),
                fact("proc-1", "procedure", { name: "Chest X-ray", result: "No acute cardiopulmonary process." }),
                fact("appt-1", "appointment", { description: "Endocrinology follow-up", scheduled_for: "2026-11-02" }),
                fact("allergy-1", "allergy", { allergen: "NKDA" }),
                fact("obligation-1", "obligation", { description: "Check blood glucose", frequency: "Daily" }),
            ]);
            for (const [text, heading, labels] of [
                ["Blood pressure", "Vital sign", ["Measurement", "Value", "Unit"]],
                ["Influenza", "Immunization", ["Vaccine", "Administered"]],
                ["Chest X-ray", "Procedure", ["Procedure", "Result"]],
                ["Endocrinology follow-up", "Appointment", ["Appointment", "Scheduled for"]],
                ["NKDA", "Allergy", ["Allergen"]],
                ["Check blood glucose", "Instruction", ["Instruction", "Frequency"]],
            ] as const) {
                const card = candidate(text);
                expect(within(card).getByText(heading, { selector: "p" })).toBeInTheDocument();
                expect(fieldLabels(card)).toEqual(labels);
            }
        });

        it("shows a lab result as one compact row with printed range, flag and critical badges", async () => {
            await openFacts([
                fact("lab-1", "lab_result", { test_name: "Potassium", value: "6.8", unit: "mmol/L", reference_range: "3.5-5.1", flag: "HH", panel: "Basic metabolic panel", flag_meaning: "critical", range_status: "above" }),
                fact("med-1", "medication", { name: "Metformin", dosage: "500 mg", medication_action: "continued" }),
                fact("lab-2", "lab_result", { test_name: "Hemoglobin A1c", value: "8.2", unit: "%", reference_range: "4.0-5.6", flag: "H", flag_meaning: "high", range_status: "above" }),
                fact("lab-3", "lab_result", { test_name: "Sodium", value: "139", unit: "mmol/L", reference_range: "136-145", panel: "Basic metabolic panel", range_status: "within" }),
            ]);
            const panel = screen.getByRole("list", { name: "Basic metabolic panel results" });
            expect(within(panel).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
                expect.stringContaining("Potassium"),
                expect.stringContaining("Sodium"),
            ]);
            const potassium = candidate("Potassium");
            expect(within(potassium).getByText("Lab result", { selector: "p" })).toBeInTheDocument();
            expect(fieldLabels(potassium)).toEqual(["Test", "Result", "Reference range", "Flag"]);
            expect(within(potassium).getByText("6.8")).toBeInTheDocument();
            expect(within(potassium).getByText("3.5-5.1")).toBeInTheDocument();
            expect(within(potassium).getByText("Critical")).toHaveClass("bg-risk-strong");
            expect(within(potassium).getByText("HH")).toHaveClass("bg-risk-soft");
            const a1c = candidate("Hemoglobin A1c");
            expect(within(a1c).getByText("H")).toHaveClass("bg-risk-soft");
            expect(within(a1c).queryByText("Critical")).not.toBeInTheDocument();
            for (const derived of ["flag meaning", "Flag meaning", "range status", "Range status", "above", "critical"]) {
                expect(screen.queryByText(derived)).not.toBeInTheDocument();
            }
        });

        it("shows the consistency warning instead of a raw derived field", async () => {
            const warning = "The printed flag says high, but the value is within the printed reference range.";
            await openFacts([fact("lab-4", "lab_result", { test_name: "Glucose", value: "92", unit: "mg/dL", reference_range: "70-99", flag: "H", flag_meaning: "high", range_status: "within", consistency: warning })]);
            const card = candidate("Glucose");
            expect(within(card).getByText(warning).closest("p")).toHaveClass("bg-warn-soft", "text-warn-ink");
            expect(fieldLabels(card)).not.toContain("Consistency");
        });

        it("marks stopped and held medications so they cannot read as active", async () => {
            await openFacts([
                fact("med-stop", "medication", { name: "Glipizide", dosage: "5 mg", status: "STOP", medication_action: "stopped" }),
                fact("med-hold", "medication", { name: "Lisinopril", dosage: "10 mg", status: "Hold", medication_action: "held" }),
                fact("med-new", "medication", { name: "Empagliflozin", dosage: "10 mg", status: "New", medication_action: "new" }),
                fact("med-continue", "medication", { name: "Metformin", dosage: "500 mg", status: "Continue", medication_action: "continued" }),
            ]);
            const stopped = candidate("Glipizide");
            expect(within(stopped).getByText("Stop")).toHaveClass("bg-risk-strong");
            expect(within(stopped).getByText(/source says to stop this medication/)).toHaveClass("sr-only");
            expect(fieldLabels(stopped)).toEqual(["Medication", "Dose", "Printed status"]);
            expect(within(candidate("Lisinopril")).getByText("Hold", { selector: "span" })).toHaveClass("bg-warn-strong");
            expect(within(candidate("Empagliflozin")).getByText("New", { selector: "span" })).toHaveClass("bg-sunken");
            const continued = candidate("Metformin");
            expect(within(continued).queryByText("Stop")).not.toBeInTheDocument();
            expect(fieldLabels(continued)).not.toContain("Medication action");
        });
    });

    describe("dates", () => {
        afterEach(() => vi.restoreAllMocks());

        it("formats upload and review dates as en-US regardless of the default locale", () => {
            simulateNonUsDefaultLocale();
            render(
                <PatientDocumentsPanel
                    documents={[{ id: "doc-dated", fileName: "dated.pdf", documentType: "other", parseStatus: "completed", createdAt: "2026-10-12T12:00:00Z", uploadedByRole: "patient", reviewStatus: "approved", reviewedAt: "2026-10-13T12:00:00Z" }]}
                    onRefresh={vi.fn()}
                    patientId="patient-dated"
                />,
            );
            expect(document.querySelector('time[datetime="2026-10-12T12:00:00Z"]')).toHaveTextContent(/^10\/12\/2026$/);
            expect(screen.getByText(/Approved on 10\/13\/2026, /)).toBeInTheDocument();
            expect(screen.queryByText(/12\/10\/2026/)).not.toBeInTheDocument();
        });
    });
});
