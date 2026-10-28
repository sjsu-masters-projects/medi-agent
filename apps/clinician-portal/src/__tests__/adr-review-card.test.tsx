import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ADRReviewCard } from "@/components/features/adr-review-card";
import { formatReviewTimestamp } from "@/components/features/review-time";
import type { ADRReviewEvidence, ADRReviewQueueItem } from "@/services/clinicians";

const RESPONDED_AT = "2026-10-03T15:30:00Z";

const baseItem: ADRReviewQueueItem = {
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
    naranjoAssessment: { missing_questions: [] },
    evidence: [],
    status: "draft",
    requestedInformation: [],
    patientResponses: [],
    createdAt: "2026-10-02T09:53:00Z",
};

const aiEntry: ADRReviewEvidence = {
    question: "event_after_drug",
    answer: "yes",
    evidence: "I became dizzy a few hours after starting the inhaler.",
};

const patientEntry: ADRReviewEvidence = {
    question: "dose_response",
    answer: "yes",
    evidence: "It improved after my clinician lowered the dose.",
    source: "patient_follow_up",
    information_request_id: "request-1",
};

function renderCard(overrides: Partial<ADRReviewQueueItem>) {
    return render(
        <ADRReviewCard
            item={{ ...baseItem, ...overrides }}
            onPrepareDraft={vi.fn()}
            onReview={vi.fn()}
            submitting={false}
        />,
    );
}

/** The rendered evidence entries, in order. */
function evidenceEntries(container: HTMLElement) {
    const heading = within(container).getByRole("heading", {
        name: "Naranjo evidence",
    });
    const section = heading.closest("section")!;
    return within(section).queryAllByRole("listitem");
}

/** `AiChip` is the only element styled with the AI tint on this card. */
function aiChips(root: HTMLElement) {
    return root.querySelectorAll(".bg-ai-tint");
}

/** `ApprovalSeal` renders its check inside the solid `bg-ok` square. */
function approvalSeals(root: HTMLElement) {
    return root.querySelectorAll(".bg-ok");
}

const LABELS = ["AI-extracted", "Patient-confirmed", "Clinician-entered", "Other source"] as const;

function labelsIn(entry: HTMLElement) {
    return LABELS.flatMap((label) =>
        within(entry)
            .queryAllByText(label, { exact: true })
            .map(() => label),
    );
}

afterEach(() => {
    vi.restoreAllMocks();
});

describe("ADR review card evidence provenance", () => {
    it("labels a clinician-entered answer with its recorded time (PV-001-D)", () => {
        const recordedAt = "2026-10-27T14:00:00Z";
        const { container } = renderCard({
            evidence: [
                aiEntry,
                {
                    question: "alternative_causes",
                    answer: "no",
                    evidence: "No other medicine or condition explains it.",
                    source: "clinician_entry",
                    recorded_at: recordedAt,
                },
            ],
        });
        const entries = evidenceEntries(container);
        expect(labelsIn(entries[0])).toEqual(["AI-extracted"]);
        expect(labelsIn(entries[1])).toEqual(["Clinician-entered"]);
        expect(entries[1]).toHaveTextContent("Alternative causes");
        expect(entries[1].querySelector("time")).toHaveAttribute("dateTime", recordedAt);
    });

    it("shows the clinician answers panel only while the case is open and a handler is given", () => {
        const onRecordAnswers = vi.fn();
        const { rerender } = render(
            <ADRReviewCard item={baseItem} onPrepareDraft={vi.fn()} onRecordAnswers={onRecordAnswers} onReview={vi.fn()} submitting={false} />,
        );
        expect(screen.getByRole("heading", { name: "Clinician answers" })).toBeInTheDocument();
        rerender(
            <ADRReviewCard item={{ ...baseItem, status: "reviewed" }} onPrepareDraft={vi.fn()} onRecordAnswers={onRecordAnswers} onReview={vi.fn()} submitting={false} />,
        );
        expect(screen.queryByRole("heading", { name: "Clinician answers" })).toBeNull();
        cleanup();
        renderCard({});
        expect(screen.queryByRole("heading", { name: "Clinician answers" })).toBeNull();
    });

    it("distinguishes repeated patient answers by request without discarding evidence or inventing dates", () => {
        const { container } = renderCard({
            evidence: [
                { ...patientEntry, information_request_id: null },
                { ...patientEntry, information_request_id: "request-older", answer: "no" },
                patientEntry,
            ],
            informationRequestId: "request-1",
            patientRespondedAt: RESPONDED_AT,
        });
        const entries = evidenceEntries(container);
        expect(entries).toHaveLength(3);
        expect(entries[0]).toHaveTextContent("Follow-up request not recorded");
        expect(entries[1]).toHaveTextContent("Different follow-up");
        expect(entries[2]).toHaveTextContent("Current follow-up");
        expect(entries[0].querySelector("time")).toBeNull();
        expect(entries[1].querySelector("time")).toBeNull();
        expect(entries[2].querySelector("time")).toHaveAttribute("dateTime", RESPONDED_AT);
        for (const entry of entries) expect(labelsIn(entry)).toEqual(["Patient-confirmed"]);
        expect(within(entries[1]).getByText("no", { exact: true })).toBeInTheDocument();
    });

    it("labels every entry AI-extracted when no entry records a source", () => {
        const { container } = renderCard({
            evidence: [aiEntry, { ...aiEntry, question: "improved_on_dechallenge" }],
        });

        const entries = evidenceEntries(container);
        expect(entries).toHaveLength(2);
        for (const entry of entries) {
            expect(labelsIn(entry)).toEqual(["AI-extracted"]);
            expect(aiChips(entry)).toHaveLength(1);
        }
        expect(aiChips(container)).toHaveLength(2);
        expect(screen.queryByText("Patient-confirmed")).not.toBeInTheDocument();
        expect(screen.queryByText(/Answered/)).not.toBeInTheDocument();
        expect(approvalSeals(container)).toHaveLength(0);
    });

    it("labels patient answers Patient-confirmed without a sparkle or seal and dates the matching request", () => {
        const { container } = renderCard({
            evidence: [patientEntry, { ...patientEntry, question: "previous_reports" }],
            informationRequestId: "request-1",
            patientRespondedAt: RESPONDED_AT,
        });

        const entries = evidenceEntries(container);
        expect(entries).toHaveLength(2);
        for (const entry of entries) {
            expect(labelsIn(entry)).toEqual(["Patient-confirmed"]);
            const time = entry.querySelector("time");
            expect(time).not.toBeNull();
            expect(time).toHaveAttribute("dateTime", RESPONDED_AT);
            expect(time).toHaveClass("font-mono");
            expect(time).toHaveTextContent(formatReviewTimestamp(RESPONDED_AT));
            expect(time?.textContent).toMatch(/^Oct \d{1,2}, 2026/);
            expect(within(entry).getByText(/Answered/)).toBeInTheDocument();
        }
        expect(aiChips(container)).toHaveLength(0);
        expect(approvalSeals(container)).toHaveLength(0);
    });

    it.each([
        [
            "the entry answers a different request",
            { informationRequestId: "request-2", patientRespondedAt: RESPONDED_AT },
            patientEntry,
        ],
        [
            "the response time is not set",
            { informationRequestId: "request-1", patientRespondedAt: null },
            patientEntry,
        ],
        [
            "neither the entry nor the item records a request",
            { informationRequestId: null, patientRespondedAt: RESPONDED_AT },
            { ...patientEntry, information_request_id: null },
        ],
    ] as const)("omits the answer date when %s", (_case, overrides, entry) => {
        const { container } = renderCard({ ...overrides, evidence: [entry] });

        const [rendered] = evidenceEntries(container);
        expect(labelsIn(rendered)).toEqual(["Patient-confirmed"]);
        expect(rendered.querySelector("time")).toBeNull();
        expect(screen.queryByText(/Answered/)).not.toBeInTheDocument();
    });

    it("renders an AI entry and a later patient answer to the same question with distinct labels", () => {
        const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
        const { container } = renderCard({
            evidence: [aiEntry, { ...patientEntry, question: aiEntry.question }],
            informationRequestId: "request-1",
            patientRespondedAt: RESPONDED_AT,
        });

        const entries = evidenceEntries(container);
        expect(entries).toHaveLength(2);
        expect(labelsIn(entries[0])).toEqual(["AI-extracted"]);
        expect(labelsIn(entries[1])).toEqual(["Patient-confirmed"]);
        expect(screen.getAllByText("Event followed medication")).toHaveLength(2);
        expect(aiChips(container)).toHaveLength(1);
        expect(aiChips(entries[1])).toHaveLength(0);
        expect(entries[1].querySelector("time")).not.toBeNull();
        expect(approvalSeals(container)).toHaveLength(0);
        expect(consoleError).not.toHaveBeenCalled();
    });

    it("gives an unrecognised source a neutral Other source label with no AI claim", () => {
        const { container } = renderCard({
            evidence: [{ ...aiEntry, source: "chat_extraction" }],
        });

        const [entry] = evidenceEntries(container);
        expect(labelsIn(entry)).toEqual(["Other source"]);
        expect(aiChips(container)).toHaveLength(0);
        expect(approvalSeals(container)).toHaveLength(0);
    });

    it("keeps the Naranjo caveat and the decision-support footer", () => {
        renderCard({ evidence: [aiEntry] });

        expect(
            screen.getByText(
                "Naranjo scores support your review; they do not make a clinical decision.",
            ),
        ).toBeInTheDocument();
        expect(screen.getByText(/^Decision support only\./)).toBeInTheDocument();
    });
});

// Feature: adr-loop-gap-fixes, Property 6: Each evidence entry carries exactly one truthful provenance label
describe("Property 6: each evidence entry carries exactly one truthful provenance label", () => {
    /**
     * **Validates: Requirements 7.1, 7.2, 7.4, 1.15**
     *
     * Exhaustive table: every evidence list of length 0-3 over the source values
     * below, each paired with two question layouts (all repeated, alternating).
     */
    const SOURCES = [undefined, null, "patient_follow_up", "chat_extraction", ""] as const;
    const QUESTION_LAYOUTS = {
        repeated: () => "event_after_drug",
        alternating: (index: number) => (index % 2 === 0 ? "event_after_drug" : "dose_response"),
    } as const;

    type Source = (typeof SOURCES)[number];

    function sourceLists(maxLength: number): Source[][] {
        const lists: Source[][] = [[]];
        let frontier: Source[][] = [[]];
        for (let length = 1; length <= maxLength; length += 1) {
            frontier = frontier.flatMap((list) => SOURCES.map((source) => [...list, source]));
            lists.push(...frontier);
        }
        return lists;
    }

    function expectedLabel(source: Source) {
        if (source === undefined || source === null) return "AI-extracted";
        if (source === "patient_follow_up") return "Patient-confirmed";
        return "Other source";
    }

    function toEvidence(sources: Source[], layout: keyof typeof QUESTION_LAYOUTS) {
        return sources.map((source, index): ADRReviewEvidence => {
            const entry: ADRReviewEvidence = {
                question: QUESTION_LAYOUTS[layout](index),
                answer: index % 2 === 0 ? "yes" : "no",
                evidence: `Entry ${index}`,
                information_request_id: "request-1",
            };
            // `undefined` means the key is absent, as stored AI extraction entries are.
            return source === undefined ? entry : { ...entry, source };
        });
    }

    const cases = sourceLists(3).flatMap((sources) =>
        (Object.keys(QUESTION_LAYOUTS) as Array<keyof typeof QUESTION_LAYOUTS>).map(
            (layout) => ({ sources, layout }),
        ),
    );

    it(`holds for all ${cases.length} generated evidence lists`, () => {
        expect(cases.length).toBe(2 * (1 + 5 + 25 + 125));
        const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

        for (const { sources, layout } of cases) {
            const evidence = toEvidence(sources, layout);
            const { container } = renderCard({
                evidence,
                informationRequestId: "request-1",
                patientRespondedAt: RESPONDED_AT,
            });
            const caseName = `${layout} ${JSON.stringify(sources.map((s) => s ?? String(s)))}`;

            const entries = evidenceEntries(container);
            expect(entries, caseName).toHaveLength(evidence.length);
            entries.forEach((entry, index) => {
                expect(labelsIn(entry), `${caseName} entry ${index}`).toEqual([
                    expectedLabel(sources[index]),
                ]);
            });
            const aiCount = sources.filter((s) => s === undefined || s === null).length;
            expect(aiChips(container), caseName).toHaveLength(aiCount);
            expect(approvalSeals(container), caseName).toHaveLength(0);

            cleanup();
        }

        const keyWarnings = consoleError.mock.calls.filter((args) =>
            args.some((arg) => typeof arg === "string" && /same key|unique "key"/i.test(arg)),
        );
        expect(keyWarnings).toEqual([]);
    }, 30_000); // 312 full renders: CI runners take longer than the 5-second default.
});

describe("ADR review card replaced clinician answers", () => {
    const answer = (value: string, basis: string, recordedAt: string): ADRReviewEvidence => ({
        question: "toxic_drug_concentration",
        answer: value,
        evidence: basis,
        source: "clinician_entry",
        recorded_at: recordedAt,
    });

    function evidenceSection(container: HTMLElement) {
        return within(container)
            .getByRole("heading", { name: "Naranjo evidence" })
            .closest("section")!;
    }

    it("lists the current clinician answer and keeps replaced ones under their own heading", () => {
        const { container } = renderCard({
            evidence: [
                aiEntry,
                answer("yes", "First thought.", "2026-10-28T18:42:00Z"),
                answer("yes", "Second thought.", "2026-10-28T18:42:30Z"),
                answer("no", "Level was normal.", "2026-10-28T18:43:00Z"),
            ],
        });

        const section = evidenceSection(container);
        const current = section.querySelector("ul")!;
        expect(within(current).getAllByRole("listitem")).toHaveLength(2);
        expect(current).toHaveTextContent("Level was normal.");
        expect(current).toHaveTextContent("I became dizzy");
        expect(current).not.toHaveTextContent("First thought.");
        expect(current).not.toHaveTextContent("Second thought.");

        const earlier = within(section).getByText("Earlier clinician answers (2)").closest("details")!;
        expect(earlier).toHaveTextContent("First thought.");
        expect(earlier).toHaveTextContent("Second thought.");
        expect(within(earlier).getAllByText("Replaced")).toHaveLength(2);
        expect(earlier).toHaveTextContent("the score uses the current answers");
    });

    it("adds no earlier-answers heading when no clinician answer was replaced", () => {
        const { container } = renderCard({
            evidence: [
                aiEntry,
                answer("no", "Level was normal.", "2026-10-28T18:43:00Z"),
                { ...answer("yes", "Positive test.", "2026-10-28T18:44:00Z"), question: "objective_evidence" },
            ],
        });

        expect(screen.queryByText(/Earlier clinician answers/)).toBeNull();
        expect(evidenceEntries(container)).toHaveLength(3);
    });

    it("never regroups repeated patient answers", () => {
        const { container } = renderCard({
            evidence: [
                { ...patientEntry, information_request_id: "request-1" },
                { ...patientEntry, information_request_id: "request-2", evidence: "Said again." },
            ],
        });

        expect(screen.queryByText(/Earlier clinician answers/)).toBeNull();
        expect(screen.queryByText("Replaced")).toBeNull();
        expect(evidenceEntries(container)).toHaveLength(2);
    });
});
