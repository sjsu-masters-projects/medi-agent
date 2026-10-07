import {
    act,
    fireEvent,
    render,
    screen,
    waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MedWatchPage from "@/app/(dashboard)/medwatch/page";

const { fetchADRReviewQueueMock, reviewADRAssessmentMock } = vi.hoisted(() => ({
    fetchADRReviewQueueMock: vi.fn(),
    reviewADRAssessmentMock: vi.fn(),
}));

vi.mock("@/services/clinicians", () => ({
    fetchADRReviewQueue: fetchADRReviewQueueMock,
    reviewADRAssessment: reviewADRAssessmentMock,
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
        missing_questions: ["alternative_causes"],
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

describe("ADR review queue", () => {
    beforeEach(() => {
        fetchADRReviewQueueMock.mockReset();
        reviewADRAssessmentMock.mockReset();
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
        expect(screen.getByText("Alternative causes")).toBeInTheDocument();
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
            target: { value: "Please clarify other possible causes." },
        });
        fireEvent.click(submit);

        await waitFor(() =>
            expect(reviewADRAssessmentMock).toHaveBeenCalledWith("adr-1", {
                action: "request_information",
                note: "Please clarify other possible causes.",
                requestedInformation: ["alternative_causes"],
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
                        missing_questions: [
                            "alternative_causes",
                            "objective_evidence",
                        ],
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
                        name: "objective evidence",
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
                        name: "alternative causes",
                    }),
                ).toBeChecked();
                expect(
                    screen.getByRole("checkbox", {
                        name: "objective evidence",
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
                        ? ["alternative_causes"]
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
            screen.getByRole("checkbox", { name: "alternative causes" }),
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
});
