import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ADRCasePage from "@/app/(dashboard)/adr-reviews/[assessmentId]/page";
import { makeDraft } from "./fixtures/medwatch";

const mocks = vi.hoisted(() => ({
    createMedWatchDraft: vi.fn(),
    fetchADRAssessment: vi.fn(),
    fetchMedWatchDrafts: vi.fn(),
    recordADRClinicianAnswers: vi.fn(),
    reviewADRAssessment: vi.fn(),
    push: vi.fn(),
}));
const query = vi.hoisted(() => ({ value: "" }));
vi.mock("next/navigation", () => ({
    useParams: () => ({ assessmentId: "adr-1" }),
    useRouter: () => ({ push: mocks.push, replace: vi.fn() }),
    useSearchParams: () => new URLSearchParams(query.value),
}));
vi.mock("@/services/clinicians", async (importOriginal) => ({
    ...(await importOriginal<typeof import("@/services/clinicians")>()),
    createMedWatchDraft: mocks.createMedWatchDraft,
    fetchADRAssessment: mocks.fetchADRAssessment,
    fetchMedWatchDrafts: mocks.fetchMedWatchDrafts,
    recordADRClinicianAnswers: mocks.recordADRClinicianAnswers,
    reviewADRAssessment: mocks.reviewADRAssessment,
}));

const assessment = {
    id: "adr-1",
    patientId: "patient-1",
    patientFirstName: "Maya",
    patientLastName: "Patel",
    symptomReportId: "symptom-1",
    symptom: "dizziness",
    severity: 2,
    onset: "a few hours after starting the inhaler",
    symptomCreatedAt: "2026-10-02T09:52:00Z",
    suspectMedicationId: "medication-1",
    suspectMedicationName: "fluticasone/salmeterol inhaler",
    naranjoScore: 3,
    causality: "Possible",
    naranjoAnswers: { event_after_drug: "yes" },
    naranjoAssessment: {
        missing_questions: ["dose_response"],
        items: [{ question: "event_after_drug", answer: "yes", points: 2 }],
    },
    evidence: [
        {
            question: "event_after_drug",
            answer: "yes",
            evidence: "I became dizzy a few hours after starting the inhaler.",
        },
    ],
    status: "draft",
    requestedInformation: [],
    patientResponses: [],
    createdAt: "2026-10-02T09:53:00Z",
};

describe("ADR case page", () => {
    beforeEach(() => {
        Object.values(mocks).forEach((mock) => mock.mockReset());
        mocks.fetchMedWatchDrafts.mockResolvedValue([]);
        query.value = "";
    });

    it("shows the summary, evidence with provenance, score and a back link to the queue", async () => {
        query.value = "from=tab%3Dreviewed%26q%3Dmaya";
        mocks.fetchADRAssessment.mockResolvedValue(assessment);
        render(<ADRCasePage />);

        expect(await screen.findByRole("heading", { level: 1, name: "Maya Patel" })).toBeInTheDocument();
        expect(screen.getByRole("link", { name: "ADR Reviews" })).toHaveAttribute(
            "href",
            "/adr-reviews?tab=reviewed&q=maya",
        );
        expect(screen.getByText("Event followed medication")).toBeInTheDocument();
        expect(screen.getByText("AI-extracted")).toBeInTheDocument();
        expect(screen.getByText(/I became dizzy a few hours/)).toBeInTheDocument();
        expect(screen.getByText("Awaiting review")).toBeInTheDocument();
        expect(screen.getByText(/Naranjo scores support your review/)).toBeInTheDocument();
        expect(screen.getByText("Show scoring details")).toBeInTheDocument();
        expect(screen.getByRole("link", { name: /open patient record/i })).toHaveAttribute(
            "href",
            "/patients/patient-1",
        );
        // One primary action for an open case; Dismiss is a quiet text button.
        expect(screen.getByRole("button", { name: "Mark reviewed" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Dismiss" })).toBeInTheDocument();
    });

    it("shows a safe error with a way back when the case is unavailable", async () => {
        mocks.fetchADRAssessment.mockRejectedValue(new Error("private diagnostic"));
        render(<ADRCasePage />);
        expect(await screen.findByText("Unable to load this ADR case")).toBeInTheDocument();
        expect(screen.queryByText("private diagnostic")).not.toBeInTheDocument();
        expect(screen.getByRole("link", { name: "Back to ADR Reviews" })).toHaveAttribute("href", "/adr-reviews");
    });

    it("marks the case reviewed and reloads it", async () => {
        mocks.fetchADRAssessment
            .mockResolvedValueOnce(assessment)
            .mockResolvedValueOnce({ ...assessment, status: "reviewed", reviewedAt: "2026-10-03T10:00:00Z" });
        mocks.reviewADRAssessment.mockResolvedValue({ status: "reviewed" });
        render(<ADRCasePage />);

        fireEvent.click(await screen.findByRole("button", { name: "Mark reviewed" }));
        fireEvent.change(screen.getByLabelText(/review note/i), {
            target: { value: "Evidence reviewed with the medication history." },
        });
        fireEvent.click(screen.getByRole("button", { name: "Mark reviewed" }));

        await waitFor(() =>
            expect(mocks.reviewADRAssessment).toHaveBeenCalledWith("adr-1", {
                action: "mark_reviewed",
                note: "Evidence reviewed with the medication history.",
                requestedInformation: [],
            }),
        );
        expect(await screen.findByText("ADR review saved and audited.")).toBeInTheDocument();
        expect(await screen.findByText("This assessment has been reviewed.")).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Mark reviewed" })).not.toBeInTheDocument();
    });

    it("links a reviewed case to its MedWatch report when one exists", async () => {
        mocks.fetchADRAssessment.mockResolvedValue({ ...assessment, status: "reviewed" });
        mocks.fetchMedWatchDrafts.mockImplementation(async (state: string) =>
            state === "active" ? [makeDraft({ id: "draft-9", adrAssessmentId: "adr-1" })] : [],
        );
        render(<ADRCasePage />);
        expect(await screen.findByRole("link", { name: "Open MedWatch report →" })).toHaveAttribute(
            "href",
            "/medwatch/draft-9",
        );
        expect(screen.queryByRole("button", { name: "Prepare MedWatch draft" })).not.toBeInTheDocument();
    });

    it("requires a note and sends selected missing questions for information requests", async () => {
        mocks.fetchADRAssessment.mockResolvedValue(assessment);
        mocks.reviewADRAssessment.mockResolvedValue({ status: "draft" });
        render(<ADRCasePage />);

        fireEvent.click(await screen.findByRole("button", { name: "Request information" }));
        const submit = screen.getByRole("button", { name: "Request information" });
        expect(submit).toBeDisabled();
        fireEvent.change(screen.getByLabelText(/review note/i), {
            target: { value: "Please describe what happened after the prior dose change." },
        });
        fireEvent.click(submit);
        await waitFor(() =>
            expect(mocks.reviewADRAssessment).toHaveBeenCalledWith("adr-1", {
                action: "request_information",
                note: "Please describe what happened after the prior dose change.",
                requestedInformation: ["dose_response"],
            }),
        );
    });

    it.each([
        ["dismiss", "Dismiss", "Dismiss assessment"],
        ["mark_reviewed", "Mark reviewed", "Mark reviewed"],
    ] as const)("retains a failed %s draft and retries the same decision", async (action, begin, submit) => {
        mocks.fetchADRAssessment.mockResolvedValue(assessment);
        mocks.reviewADRAssessment
            .mockRejectedValueOnce(new Error("private provider diagnostic"))
            .mockResolvedValueOnce({ status: "reviewed" });
        render(<ADRCasePage />);
        fireEvent.click(await screen.findByRole("button", { name: begin }));
        fireEvent.change(screen.getByLabelText(/review note/i), {
            target: { value: "Retain this clinical rationale." },
        });
        fireEvent.click(screen.getByRole("button", { name: submit }));
        expect(await screen.findByRole("alert")).toHaveTextContent(
            "Unable to save the ADR review. Your draft is retained. Try again.",
        );
        expect(screen.queryByText("private provider diagnostic")).not.toBeInTheDocument();
        expect(screen.getByLabelText(/review note/i)).toHaveValue("Retain this clinical rationale.");
        fireEvent.click(screen.getByRole("button", { name: submit }));
        await waitFor(() => expect(mocks.reviewADRAssessment).toHaveBeenCalledTimes(2));
        expect(mocks.reviewADRAssessment).toHaveBeenNthCalledWith(2, "adr-1", {
            action,
            note: "Retain this clinical rationale.",
            requestedInformation: [],
        });
    });

    it.each([
        ["Dismiss", "Dismiss assessment"],
        ["Mark reviewed", "Mark reviewed"],
    ])("enforces the 2000-character note boundary for %s", async (begin, submit) => {
        mocks.fetchADRAssessment.mockResolvedValue(assessment);
        mocks.reviewADRAssessment.mockResolvedValue({ status: "reviewed" });
        render(<ADRCasePage />);
        fireEvent.click(await screen.findByRole("button", { name: begin }));
        const note = screen.getByRole("textbox");
        expect(note).toHaveAttribute("maxlength", "2000");
        fireEvent.change(note, { target: { value: "a".repeat(2001) } });
        expect(screen.getByRole("button", { name: submit })).toBeDisabled();
        fireEvent.change(note, { target: { value: "a".repeat(2000) } });
        fireEvent.click(screen.getByRole("button", { name: submit }));
        await waitFor(() => expect(mocks.reviewADRAssessment).toHaveBeenCalledTimes(1));
        expect(mocks.reviewADRAssessment.mock.calls[0][1].note).toHaveLength(2000);
    });

    it("locks the form while a write is pending and sends it once", async () => {
        let resolveWrite!: () => void;
        mocks.fetchADRAssessment.mockResolvedValue(assessment);
        mocks.reviewADRAssessment.mockImplementationOnce(
            () => new Promise<void>((resolve) => { resolveWrite = resolve; }),
        );
        render(<ADRCasePage />);
        fireEvent.click(await screen.findByRole("button", { name: "Request information" }));
        fireEvent.change(screen.getByLabelText(/review note/i), { target: { value: "Pending rationale." } });
        const form = screen.getByRole("textbox").closest("form")!;
        fireEvent.submit(form);
        fireEvent.submit(form);
        expect(mocks.reviewADRAssessment).toHaveBeenCalledTimes(1);
        expect(screen.getByRole("textbox")).toBeDisabled();
        expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
        await act(async () => resolveWrite());
    });

    it("shows confirmed patient answers and the rescored decision support", async () => {
        mocks.fetchADRAssessment.mockResolvedValue({
            ...assessment,
            naranjoScore: 4,
            lastReviewAction: "request_information",
            reviewNote: "Please describe the prior dose change.",
            informationRequestStatus: "answered",
            patientResponses: [
                { question: "dose_response", answer: "yes", evidence: "It improved after my clinician lowered the dose." },
            ],
        });
        render(<ADRCasePage />);
        expect(await screen.findByText("Patient answered")).toBeInTheDocument();
        expect(screen.getByText(/It improved after my clinician lowered the dose/)).toBeInTheDocument();
        expect(screen.getByText(/calculated score above includes/i)).toBeInTheDocument();
        expect(screen.getByText("Information requested")).toBeInTheDocument();
    });

    it("prepares a draft only after a rationale and opens its report", async () => {
        mocks.fetchADRAssessment.mockResolvedValue(assessment);
        mocks.createMedWatchDraft.mockResolvedValue(makeDraft({ id: "draft-1" }));
        render(<ADRCasePage />);

        fireEvent.click(await screen.findByRole("button", { name: "Prepare MedWatch draft" }));
        const submit = screen.getByRole("button", { name: "Create editable draft" });
        expect(submit).toBeDisabled();
        fireEvent.change(screen.getByLabelText(/clinical rationale/i), {
            target: { value: "Clinically significant new event." },
        });
        fireEvent.click(submit);
        await waitFor(() =>
            expect(mocks.createMedWatchDraft).toHaveBeenCalledWith("adr-1", "Clinically significant new event."),
        );
        await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/medwatch/draft-1"));
    });

    it("shows a failed preparation once, inline, and keeps the rationale", async () => {
        mocks.fetchADRAssessment.mockResolvedValue(assessment);
        mocks.createMedWatchDraft.mockRejectedValueOnce(new Error("private provider diagnostic"));
        render(<ADRCasePage />);
        fireEvent.click(await screen.findByRole("button", { name: "Prepare MedWatch draft" }));
        fireEvent.change(screen.getByLabelText(/clinical rationale/i), {
            target: { value: "Clinically significant new event." },
        });
        fireEvent.click(screen.getByRole("button", { name: "Create editable draft" }));
        const alert = await screen.findByRole("alert");
        expect(alert).toHaveTextContent("Unable to prepare the MedWatch draft. Your rationale is retained. Try again.");
        expect(screen.getAllByRole("alert")).toHaveLength(1);
        expect(screen.queryByText("private provider diagnostic")).not.toBeInTheDocument();
        expect(screen.getByLabelText(/clinical rationale/i)).toHaveValue("Clinically significant new event.");
        expect(mocks.push).not.toHaveBeenCalled();
    });

    it("records clinician answers, reloads the rescored case and keeps them when saving fails (PV-001-D)", async () => {
        mocks.fetchADRAssessment.mockResolvedValue(assessment);
        mocks.recordADRClinicianAnswers
            .mockRejectedValueOnce(new Error("private provider diagnostic"))
            .mockResolvedValueOnce({ naranjoScore: 5, causality: "Probable" });
        render(<ADRCasePage />);

        const group = await screen.findByRole("radiogroup", { name: "Alternative causes" });
        fireEvent.click(within(group).getByLabelText("No"));
        fireEvent.change(screen.getByLabelText(/Basis for alternative causes/), {
            target: { value: "No other medicine or condition explains it." },
        });
        fireEvent.click(screen.getByRole("button", { name: "Save clinician answers" }));
        expect(await screen.findByRole("alert")).toHaveTextContent(
            "Unable to save the clinician answers. Your answers are retained. Try again.",
        );
        expect(screen.queryByText("private provider diagnostic")).not.toBeInTheDocument();
        expect(screen.getByLabelText(/Basis for alternative causes/)).toHaveValue(
            "No other medicine or condition explains it.",
        );

        fireEvent.click(screen.getByRole("button", { name: "Save clinician answers" }));

        await waitFor(() => expect(mocks.recordADRClinicianAnswers).toHaveBeenCalledTimes(2));
        expect(mocks.recordADRClinicianAnswers).toHaveBeenLastCalledWith("adr-1", [
            { question: "alternative_causes", answer: "no", basis: "No other medicine or condition explains it." },
        ]);
        expect(await screen.findByText("Clinician answers saved and audited. The score was recalculated.")).toBeInTheDocument();
        expect(mocks.fetchADRAssessment).toHaveBeenCalledTimes(2);
    });
});
