import {
    act,
    fireEvent,
    render,
    screen,
    waitFor,
    within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MedWatchPage from "@/app/(dashboard)/medwatch/page";
import { ATTESTATION_TEXT, makeDraft } from "./fixtures/medwatch";

const {
    approveMedWatchDraftMock,
    createMedWatchDraftMock,
    exportMedWatchDraftMock,
    fetchADRReviewQueueMock,
    fetchMedWatchDraftsMock,
    reviewADRAssessmentMock,
    updateMedWatchDraftMock,
} = vi.hoisted(() => ({
    approveMedWatchDraftMock: vi.fn(),
    createMedWatchDraftMock: vi.fn(),
    exportMedWatchDraftMock: vi.fn(),
    fetchADRReviewQueueMock: vi.fn(),
    fetchMedWatchDraftsMock: vi.fn(),
    reviewADRAssessmentMock: vi.fn(),
    updateMedWatchDraftMock: vi.fn(),
}));
const query = vi.hoisted(() => ({ value: "" }));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(query.value) }));

vi.mock("@/services/clinicians", async (importOriginal) => ({
    ...(await importOriginal<typeof import("@/services/clinicians")>()),
    approveMedWatchDraft: approveMedWatchDraftMock,
    createMedWatchDraft: createMedWatchDraftMock,
    exportMedWatchDraft: exportMedWatchDraftMock,
    fetchADRReviewQueue: fetchADRReviewQueueMock,
    fetchMedWatchDrafts: fetchMedWatchDraftsMock,
    reviewADRAssessment: reviewADRAssessmentMock,
    updateMedWatchDraft: updateMedWatchDraftMock,
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
    naranjoAnswers: {
        event_after_drug: "yes",
        improved_on_dechallenge: "yes",
    },
    naranjoAssessment: {
        missing_questions: ["dose_response"],
    },
    evidence: [
        {
            question: "event_after_drug",
            answer: "yes",
            evidence: "I became dizzy a few hours after starting the inhaler.",
        },
        {
            question: "improved_on_dechallenge",
            answer: "yes",
            evidence: "The dizziness improved after I stopped using it.",
        },
    ],
    status: "draft",
    createdAt: "2026-10-02T09:53:00Z",
};

const medwatchDraft = makeDraft({
    id: "draft-1",
    formData: {
        ...makeDraft().formData,
        section_b: {
            ...makeDraft().formData.section_b,
            outcomes: ["hospitalization"],
        },
    },
});

describe("ADR review queue", () => {
    it("focuses the exact assessment and explains an unavailable target", async () => {
        query.value = "assessment=adr-1";
        fetchADRReviewQueueMock.mockResolvedValue([assessment]);
        const view = render(<MedWatchPage />);
        await waitFor(() => expect(document.getElementById("assessment-adr-1")).toHaveFocus());
        query.value = "assessment=missing";
        view.rerender(<MedWatchPage />);
        expect(screen.getByText(/linked assessment is no longer awaiting review/)).toBeInTheDocument();
    });
    beforeEach(() => {
        approveMedWatchDraftMock.mockReset();
        createMedWatchDraftMock.mockReset();
        exportMedWatchDraftMock.mockReset();
        fetchADRReviewQueueMock.mockReset();
        fetchMedWatchDraftsMock.mockReset();
        fetchMedWatchDraftsMock.mockResolvedValue([]);
        reviewADRAssessmentMock.mockReset();
        updateMedWatchDraftMock.mockReset();
        query.value = "";
    });

    it("shows the Naranjo score and patient-grounded evidence", async () => {
        fetchADRReviewQueueMock.mockResolvedValue([assessment]);

        render(<MedWatchPage />);

        expect(await screen.findByText("Maya Patel")).toBeInTheDocument();
        expect(screen.getByText("Naranjo 3")).toBeInTheDocument();
        expect(screen.getByText("Possible")).toBeInTheDocument();
        expect(screen.getByText("dizziness")).toBeInTheDocument();
        expect(
            screen.getByText("fluticasone/salmeterol inhaler"),
        ).toBeInTheDocument();
        expect(
            screen.getByText("Event followed medication"),
        ).toBeInTheDocument();
        expect(
            screen.getByText(/I became dizzy a few hours/),
        ).toBeInTheDocument();
        expect(screen.getByText("Dose-response relationship")).toBeInTheDocument();
        expect(
            screen.getByRole("link", { name: /open patient record/i }),
        ).toHaveAttribute("href", "/patients/patient-1");
    });

    it("shows a truthful empty state when no ADR review is pending", async () => {
        fetchADRReviewQueueMock.mockResolvedValue([]);

        render(<MedWatchPage />);

        expect(
            await screen.findByText("No ADR assessments awaiting review"),
        ).toBeInTheDocument();
        expect(
            screen.queryByText("No MedWatch drafts"),
        ).not.toBeInTheDocument();
    });

    it("offers a retry when the queue request fails", async () => {
        fetchADRReviewQueueMock.mockRejectedValue(
            new Error("Service unavailable"),
        );

        render(<MedWatchPage />);

        expect(
            await screen.findByText("Unable to load ADR reviews"),
        ).toBeInTheDocument();
        expect(
            screen.getByText(
                "Unable to refresh ADR assessments. Try loading the queue again.",
            ),
        ).toBeInTheDocument();
        expect(
            screen.queryByText("Service unavailable"),
        ).not.toBeInTheDocument();
        expect(
            screen.getByRole("button", { name: /try again/i }),
        ).toBeInTheDocument();
    });

    it("marks an assessment reviewed and refreshes the pending queue", async () => {
        fetchADRReviewQueueMock
            .mockResolvedValueOnce([assessment])
            .mockResolvedValueOnce([]);
        reviewADRAssessmentMock.mockResolvedValue({ status: "reviewed" });

        render(<MedWatchPage />);

        fireEvent.click(
            await screen.findByRole("button", { name: "Mark reviewed" }),
        );
        fireEvent.change(screen.getByLabelText(/review note/i), {
            target: { value: "Evidence reviewed with the medication history." },
        });
        fireEvent.click(screen.getByRole("button", { name: "Mark reviewed" }));

        await waitFor(() =>
            expect(reviewADRAssessmentMock).toHaveBeenCalledWith("adr-1", {
                action: "mark_reviewed",
                note: "Evidence reviewed with the medication history.",
                requestedInformation: [],
            }),
        );
        expect(
            await screen.findByText("ADR review saved and audited."),
        ).toBeInTheDocument();
        expect(
            await screen.findByText("No ADR assessments awaiting review"),
        ).toBeInTheDocument();
    });

    it("requires a note and sends selected missing questions for information requests", async () => {
        fetchADRReviewQueueMock.mockResolvedValue([assessment]);
        reviewADRAssessmentMock.mockResolvedValue({ status: "draft" });

        render(<MedWatchPage />);

        fireEvent.click(
            await screen.findByRole("button", { name: "Request information" }),
        );
        const submit = screen.getByRole("button", {
            name: "Request information",
        });
        expect(submit).toBeDisabled();
        fireEvent.change(screen.getByLabelText(/review note/i), {
            target: { value: "Please describe what happened after the prior dose change." },
        });
        fireEvent.click(submit);

        await waitFor(() =>
            expect(reviewADRAssessmentMock).toHaveBeenCalledWith("adr-1", {
                action: "request_information",
                note: "Please describe what happened after the prior dose change.",
                requestedInformation: ["dose_response"],
            }),
        );
    });

    it.each([
        ["dismiss", "Dismiss", "Dismiss assessment"],
        ["mark_reviewed", "Mark reviewed", "Mark reviewed"],
        ["request_information", "Request information", "Request information"],
    ] as const)(
        "retains a failed %s draft and retries the same decision",
        async (action, begin, submit) => {
            fetchADRReviewQueueMock.mockResolvedValue([
                {
                    ...assessment,
                    naranjoAssessment: {
                        missing_questions: ["dose_response", "similar_previous_reaction"],
                    },
                },
            ]);
            reviewADRAssessmentMock
                .mockRejectedValueOnce(new Error("private provider diagnostic"))
                .mockResolvedValueOnce({ status: "draft" });
            render(<MedWatchPage />);
            fireEvent.click(await screen.findByRole("button", { name: begin }));
            fireEvent.change(screen.getByLabelText(/review note/i), {
                target: { value: "Retain this clinical rationale." },
            });
            if (action === "request_information")
                fireEvent.click(
                    screen.getByRole("checkbox", {
                        name: "similar previous reaction",
                    }),
                );
            fireEvent.click(screen.getByRole("button", { name: submit }));
            expect(await screen.findByRole("alert")).toHaveTextContent(
                "Unable to save the ADR review. Your draft is retained. Try again.",
            );
            expect(
                screen.queryByText("private provider diagnostic"),
            ).not.toBeInTheDocument();
            expect(screen.getByLabelText(/review note/i)).toHaveValue(
                "Retain this clinical rationale.",
            );
            if (action === "request_information") {
                expect(
                    screen.getByRole("checkbox", {
                        name: "dose response",
                    }),
                ).toBeChecked();
                expect(
                    screen.getByRole("checkbox", {
                        name: "similar previous reaction",
                    }),
                ).not.toBeChecked();
            }
            expect(fetchADRReviewQueueMock).toHaveBeenCalledTimes(1);
            fireEvent.click(screen.getByRole("button", { name: submit }));
            await waitFor(() =>
                expect(reviewADRAssessmentMock).toHaveBeenCalledTimes(2),
            );
            const expected = {
                action,
                note: "Retain this clinical rationale.",
                requestedInformation:
                    action === "request_information"
                        ? ["dose_response"]
                        : [],
            };
            expect(reviewADRAssessmentMock).toHaveBeenNthCalledWith(
                1,
                "adr-1",
                expected,
            );
            expect(reviewADRAssessmentMock).toHaveBeenNthCalledWith(
                2,
                "adr-1",
                expected,
            );
            expect(
                await screen.findByText(/saved and audited/),
            ).toBeInTheDocument();
            await waitFor(() =>
                expect(screen.queryByRole("textbox")).not.toBeInTheDocument(),
            );
        },
    );

    it("keeps the draft mounted during refresh, failure, and successful retry", async () => {
        let rejectRefresh!: (reason: Error) => void;
        fetchADRReviewQueueMock
            .mockResolvedValueOnce([assessment])
            .mockImplementationOnce(
                () =>
                    new Promise((_, reject) => {
                        rejectRefresh = reject;
                    }),
            )
            .mockResolvedValueOnce([assessment]);
        render(<MedWatchPage />);
        fireEvent.click(
            await screen.findByRole("button", { name: "Request information" }),
        );
        fireEvent.change(screen.getByLabelText(/review note/i), {
            target: { value: "Unsent clarification." },
        });
        fireEvent.click(
            screen.getByRole("checkbox", { name: "dose response" }),
        );
        const note = screen.getByLabelText(/review note/i);
        fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
        expect(screen.getByLabelText(/review note/i)).toBe(note);
        expect(note).toBeDisabled();
        expect(screen.getByRole("checkbox")).toBeDisabled();
        expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "Refresh" })).toBeDisabled();
        await act(async () =>
            rejectRefresh(new Error("private refresh diagnostic")),
        );
        expect(screen.getByRole("alert")).toHaveTextContent(
            "Unable to refresh ADR assessments",
        );
        expect(
            screen.queryByText("private refresh diagnostic"),
        ).not.toBeInTheDocument();
        expect(note).toHaveValue("Unsent clarification.");
        expect(screen.getByRole("checkbox")).not.toBeChecked();
        expect(
            screen.getByRole("button", { name: "Request information" }),
        ).toBeDisabled();
        fireEvent.click(screen.getByRole("button", { name: "Try again" }));
        await waitFor(() => expect(note).not.toBeDisabled());
        expect(screen.getByLabelText(/review note/i)).toBe(note);
        expect(note).toHaveValue("Unsent clarification.");
        expect(screen.getByRole("checkbox")).not.toBeChecked();
        expect(reviewADRAssessmentMock).not.toHaveBeenCalled();
    });

    it.each([
        ["dismiss", "Dismiss", "Dismiss assessment"],
        ["mark_reviewed", "Mark reviewed", "Mark reviewed"],
        ["request_information", "Request information", "Request information"],
    ] as const)(
        "retries only the queue after a saved %s and failed reload",
        async (action, begin, submit) => {
            const other = {
                ...assessment,
                id: "adr-2",
                patientFirstName: "Elena",
            };
            fetchADRReviewQueueMock
                .mockResolvedValueOnce([assessment])
                .mockRejectedValueOnce(
                    new Error("private saved reload diagnostic"),
                )
                .mockResolvedValueOnce([other]);
            reviewADRAssessmentMock.mockResolvedValue({
                status: action === "request_information" ? "draft" : "reviewed",
            });
            render(<MedWatchPage />);
            fireEvent.click(await screen.findByRole("button", { name: begin }));
            fireEvent.change(screen.getByLabelText(/review note/i), {
                target: { value: "Confirmed decision." },
            });
            fireEvent.click(screen.getByRole("button", { name: submit }));
            expect(
                await screen.findByText(/saved and audited/),
            ).toBeInTheDocument();
            expect(
                await screen.findByText(
                    "Unable to refresh ADR assessments. Try loading the queue again.",
                ),
            ).toBeInTheDocument();
            await waitFor(() =>
                expect(screen.queryByRole("textbox")).not.toBeInTheDocument(),
            );
            expect(
                screen.queryByText("private saved reload diagnostic"),
            ).not.toBeInTheDocument();
            expect(
                screen.queryByText(/Unable to save the ADR review/),
            ).not.toBeInTheDocument();
            if (action === "request_information") {
                expect(
                    screen.getByRole("button", { name: "Request information" }),
                ).toBeDisabled();
            } else
                expect(
                    screen.queryByText("Maya Patel"),
                ).not.toBeInTheDocument();
            fireEvent.click(screen.getByRole("button", { name: /try again/i }));
            expect(await screen.findByText("Elena Patel")).toBeInTheDocument();
            expect(reviewADRAssessmentMock).toHaveBeenCalledTimes(1);
            expect(fetchADRReviewQueueMock).toHaveBeenCalledTimes(3);
        },
    );

    it.each([
        ["Dismiss", "Dismiss assessment"],
        ["Mark reviewed", "Mark reviewed"],
        ["Request information", "Request information"],
    ])(
        "enforces the 2000-character note boundary for %s",
        async (begin, submit) => {
            fetchADRReviewQueueMock
                .mockResolvedValueOnce([assessment])
                .mockResolvedValueOnce([]);
            reviewADRAssessmentMock.mockResolvedValue({ status: "reviewed" });
            render(<MedWatchPage />);
            fireEvent.click(await screen.findByRole("button", { name: begin }));
            const note = screen.getByRole("textbox");
            expect(note).toHaveAttribute("maxlength", "2000");
            fireEvent.change(note, { target: { value: "a".repeat(2001) } });
            expect(screen.getByRole("button", { name: submit })).toBeDisabled();
            fireEvent.submit(note.closest("form")!);
            expect(reviewADRAssessmentMock).not.toHaveBeenCalled();
            fireEvent.change(note, { target: { value: "a".repeat(2000) } });
            expect(
                screen.getByRole("button", { name: submit }),
            ).not.toBeDisabled();
            fireEvent.click(screen.getByRole("button", { name: submit }));
            await waitFor(() =>
                expect(reviewADRAssessmentMock).toHaveBeenCalledTimes(1),
            );
            expect(reviewADRAssessmentMock.mock.calls[0][1].note).toHaveLength(
                2000,
            );
            expect(
                await screen.findByText(/saved and audited/),
            ).toBeInTheDocument();
        },
    );

    it("locks inputs, other reviews, cancel, and refresh while a write is pending", async () => {
        let resolveWrite!: () => void;
        fetchADRReviewQueueMock.mockResolvedValue([
            assessment,
            { ...assessment, id: "adr-2" },
        ]);
        reviewADRAssessmentMock.mockImplementationOnce(
            () =>
                new Promise<void>((resolve) => {
                    resolveWrite = resolve;
                }),
        );
        render(<MedWatchPage />);
        fireEvent.click(
            (
                await screen.findAllByRole("button", {
                    name: "Request information",
                })
            )[0],
        );
        fireEvent.change(screen.getByLabelText(/review note/i), {
            target: { value: "Pending rationale." },
        });
        const form = screen.getByRole("textbox").closest("form")!;
        fireEvent.submit(form);
        fireEvent.submit(form);
        expect(reviewADRAssessmentMock).toHaveBeenCalledTimes(1);
        expect(screen.getByRole("textbox")).toBeDisabled();
        expect(screen.getByRole("checkbox")).toBeDisabled();
        expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "Refresh" })).toBeDisabled();
        expect(
            screen.getByRole("button", { name: "Mark reviewed" }),
        ).toBeDisabled();
        await act(async () => resolveWrite());
        await waitFor(() =>
            expect(screen.queryByRole("textbox")).not.toBeInTheDocument(),
        );
        expect(reviewADRAssessmentMock).toHaveBeenCalledTimes(1);
    });

    it("shows confirmed patient answers and the rescored decision support", async () => {
        fetchADRReviewQueueMock.mockResolvedValue([
            {
                ...assessment,
                naranjoScore: 4,
                lastReviewAction: "request_information",
                reviewNote: "Please describe the prior dose change.",
                informationRequestStatus: "answered",
                patientResponses: [
                    {
                        question: "dose_response",
                        answer: "yes",
                        evidence: "It improved after my clinician lowered the dose.",
                    },
                ],
            },
        ]);

        render(<MedWatchPage />);

        expect(await screen.findByText("Patient answered")).toBeInTheDocument();
        expect(
            screen.getByText(/It improved after my clinician lowered the dose/),
        ).toBeInTheDocument();
        expect(screen.getByText(/deterministic score above includes/i)).toBeInTheDocument();
        expect(screen.getByText("Naranjo 4")).toBeInTheDocument();
    });

    it("creates an evidence-backed draft only after a clinician rationale", async () => {
        fetchADRReviewQueueMock.mockResolvedValue([assessment]);
        createMedWatchDraftMock.mockResolvedValue(medwatchDraft);

        render(<MedWatchPage />);

        fireEvent.click(
            await screen.findByRole("button", { name: "Prepare MedWatch draft" }),
        );
        const submit = screen.getByRole("button", {
            name: "Create editable draft",
        });
        expect(submit).toBeDisabled();
        fireEvent.change(screen.getByLabelText(/clinical rationale/i), {
            target: { value: "Clinically significant new event." },
        });
        fireEvent.click(submit);

        await waitFor(() =>
            expect(createMedWatchDraftMock).toHaveBeenCalledWith(
                "adr-1",
                "Clinically significant new event.",
            ),
        );
        expect(
            await screen.findByText("MedWatch Form 3500 draft"),
        ).toBeInTheDocument();
        expect(
            screen.getAllByText("Not submitted to FDA").length,
        ).toBeGreaterThan(0);
        expect(screen.getByText("Patient-reported symptom")).toBeInTheDocument();
    });

    it("announces the initial load with the skeleton queue", async () => {
        let resolveQueue!: (items: unknown[]) => void;
        fetchADRReviewQueueMock.mockImplementationOnce(
            () =>
                new Promise((resolve) => {
                    resolveQueue = resolve;
                }),
        );

        render(<MedWatchPage />);

        expect(
            screen.getByRole("status", { name: "Loading ADR reviews" }),
        ).toBeInTheDocument();
        await act(async () => resolveQueue([assessment]));
        expect(await screen.findByText("Maya Patel")).toBeInTheDocument();
        expect(
            screen.queryByRole("status", { name: "Loading ADR reviews" }),
        ).not.toBeInTheDocument();
        expect(
            screen.getByRole("region", { name: "ADR assessments awaiting review" }),
        ).toBeInTheDocument();
        expect(
            screen.getByRole("region", { name: "ADR review summary" }),
        ).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Refresh" })).toBeEnabled();
    });

    it("shows a failed preparation once, inline, and keeps the rationale", async () => {
        fetchADRReviewQueueMock.mockResolvedValue([assessment]);
        createMedWatchDraftMock.mockRejectedValueOnce(
            new Error("private provider diagnostic"),
        );

        render(<MedWatchPage />);

        fireEvent.click(
            await screen.findByRole("button", { name: "Prepare MedWatch draft" }),
        );
        fireEvent.change(screen.getByLabelText(/clinical rationale/i), {
            target: { value: "Clinically significant new event." },
        });
        fireEvent.click(
            screen.getByRole("button", { name: "Create editable draft" }),
        );

        const alert = await screen.findByRole("alert");
        expect(alert).toHaveTextContent(
            "Unable to prepare the MedWatch draft. Your rationale is retained. Try again.",
        );
        expect(screen.getAllByRole("alert")).toHaveLength(1);
        expect(
            screen.getByRole("form", { name: "Record reportability decision" }),
        ).toContainElement(alert);
        expect(screen.getAllByText(/Unable to prepare the MedWatch draft/)).toHaveLength(1);
        expect(screen.queryByText("Unable to load ADR reviews")).not.toBeInTheDocument();
        expect(screen.queryByText("private provider diagnostic")).not.toBeInTheDocument();
        expect(screen.getByLabelText(/clinical rationale/i)).toHaveValue(
            "Clinically significant new event.",
        );
        expect(screen.getByText("Maya Patel")).toBeInTheDocument();
        expect(
            screen.getByRole("button", { name: "Create editable draft" }),
        ).toBeEnabled();
    });

    it("saves edits and requires attestation before approval", async () => {
        fetchADRReviewQueueMock.mockResolvedValue([]);
        fetchMedWatchDraftsMock.mockResolvedValue([medwatchDraft]);
        updateMedWatchDraftMock.mockImplementation(async (_id, formData) => ({
            ...medwatchDraft,
            formData,
            revision: 2,
            clinicianEditedFields: ["event.outcome"],
        }));
        approveMedWatchDraftMock.mockResolvedValue({
            ...medwatchDraft,
            status: "reviewed",
            revision: 3,
            approvedBy: "clinician-1",
            approvedAt: "2026-10-09T11:00:00Z",
            approvalNote: "Evidence and form reviewed.",
        });

        render(<MedWatchPage />);

        const narrative = await screen.findByLabelText(
            "B5 Describe event, problem or product use/medication error",
        );
        expect(fetchMedWatchDraftsMock).toHaveBeenCalledWith("active");
        fireEvent.change(narrative, { target: { value: "Recovering" } });
        fireEvent.click(screen.getByRole("button", { name: "Save draft" }));
        await waitFor(() =>
            expect(updateMedWatchDraftMock).toHaveBeenCalledWith(
                "draft-1",
                expect.objectContaining({
                    section_b: expect.objectContaining({ narrative: "Recovering" }),
                }),
                1,
            ),
        );
        expect(await screen.findByText("MedWatch draft changes saved and audited.")).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: "Approve for export" }));
        const dialog = screen.getByRole("dialog", { name: "Approve Form 3500 draft" });
        const confirm = within(dialog).getByRole("button", { name: "Confirm approval" });
        expect(confirm).toBeDisabled();
        fireEvent.change(within(dialog).getByLabelText("Approval note"), {
            target: { value: "Evidence and form reviewed." },
        });
        fireEvent.click(
            within(dialog).getByRole("checkbox", { name: ATTESTATION_TEXT }),
        );
        fireEvent.click(confirm);

        await waitFor(() =>
            expect(approveMedWatchDraftMock).toHaveBeenCalledWith("draft-1", {
                approvalNote: "Evidence and form reviewed.",
                expectedRevision: 2,
                attestationVersion: "medwatch-3500-approval-v1",
                nonSeriousAttested: false,
                acknowledgedWarnings: [],
            }),
        );
        expect(await screen.findByText("Approved for export")).toBeInTheDocument();
    });
});
