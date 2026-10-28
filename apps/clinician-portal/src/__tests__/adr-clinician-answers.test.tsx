import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ADRClinicianAnswers } from "@/components/features/adr-clinician-answers";
import { recordADRClinicianAnswers, type ADRReviewEvidence } from "@/services/clinicians";

vi.mock("@/services/auth-session", () => ({
    readStoredSession: () => ({ accessToken: "synthetic-token" }),
}));

afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
});

function renderPanel(
    answers: Record<string, string> = {},
    onRecord = vi.fn().mockResolvedValue(undefined),
    disabled = false,
    evidence: ADRReviewEvidence[] = [],
) {
    render(
        <ADRClinicianAnswers answers={answers} disabled={disabled} evidence={evidence} onRecord={onRecord} />,
    );
    return onRecord;
}

function clinicianEntry(question: string, answer: string, basis?: string): ADRReviewEvidence {
    return { question, answer, evidence: basis, source: "clinician_entry" } as ADRReviewEvidence;
}

const fieldsetOf = (name: string) => screen.getByText(name, { selector: "legend" }).closest("fieldset")!;

function group(name: string) {
    return screen.getByRole("radiogroup", { name });
}

const save = () => screen.getByRole("button", { name: "Save clinician answers" });

describe("ADR clinician answers (PV-001-D)", () => {
    it("lists only the five clinical questions and asks only the ones not yet recorded", () => {
        renderPanel({ alternative_causes: "no", dose_response: "yes" });

        for (const name of [
            "Previous conclusive reports",
            "Reappeared with placebo",
            "Toxic drug concentration",
            "Objective evidence",
        ]) {
            expect(group(name)).toBeInTheDocument();
        }
        // A recorded question is shown as answered, not asked again.
        expect(screen.queryByRole("radiogroup", { name: "Alternative causes" })).toBeNull();
        // Patient questions are asked through Request information, never recorded here.
        expect(screen.queryByRole("radiogroup", { name: "Dose-response relationship" })).toBeNull();
        expect(screen.queryByRole("radiogroup", { name: "Event followed medication" })).toBeNull();
        expect(screen.queryByText("Dose-response relationship", { selector: "legend" })).toBeNull();
        const alternative = fieldsetOf("Alternative causes");
        expect(within(alternative).getByText("No")).toBeInTheDocument();
        expect(within(alternative).getByText(/\+2 toward the score/)).toBeInTheDocument();
        expect(within(alternative).getByRole("button", { name: "Change answer" })).toBeEnabled();
        const open = fieldsetOf("Objective evidence");
        expect(within(open).getByText(/Not recorded yet/)).toBeInTheDocument();
        expect(within(open).getByText(/Yes \+1, No 0, Not known 0/)).toBeInTheDocument();
        expect(save()).toBeDisabled();
        expect(screen.queryByRole("textbox")).toBeNull();
    });

    it("shows the clinician's latest basis for a recorded answer, not an earlier one", () => {
        renderPanel({ toxic_drug_concentration: "no" }, undefined, false, [
            clinicianEntry("toxic_drug_concentration", "yes", "First thought."),
            clinicianEntry("toxic_drug_concentration", "no", "Level was normal."),
        ]);

        const fieldset = fieldsetOf("Toxic drug concentration");
        expect(within(fieldset).getByText(/Level was normal\./)).toBeInTheDocument();
        expect(within(fieldset).queryByText(/First thought\./)).toBeNull();
        expect(within(fieldset).getByText(/0 toward the score/)).toBeInTheDocument();
    });

    it("shows no basis for an answer that did not come from a clinician entry", () => {
        renderPanel({ objective_evidence: "yes" }, undefined, false, [
            { question: "objective_evidence", answer: "yes", evidence: "Quoted from chat." },
        ]);

        const fieldset = fieldsetOf("Objective evidence");
        expect(within(fieldset).getByText("Yes")).toBeInTheDocument();
        expect(within(fieldset).queryByText(/Quoted from chat/)).toBeNull();
    });

    it("changes a recorded answer only on request and sends just that question", async () => {
        const onRecord = renderPanel({ alternative_causes: "no", objective_evidence: "yes" }, undefined, false, [
            clinicianEntry("alternative_causes", "no", "No other cause."),
            clinicianEntry("objective_evidence", "yes", "Positive test."),
        ]);

        const alternative = fieldsetOf("Alternative causes");
        fireEvent.click(within(alternative).getByRole("button", { name: "Change answer" }));
        expect(within(alternative).getByText(/Recording a different answer/)).toBeInTheDocument();
        fireEvent.click(within(group("Alternative causes")).getByLabelText("Yes"));
        fireEvent.change(screen.getByLabelText(/Basis for alternative causes/), {
            target: { value: "A new medicine was started." },
        });
        fireEvent.click(save());

        await waitFor(() =>
            expect(onRecord).toHaveBeenCalledWith([
                { question: "alternative_causes", answer: "yes", basis: "A new medicine was started." },
            ]),
        );
        // The untouched question is not resent, and the changed one returns to the recorded view.
        await waitFor(() => expect(screen.queryByRole("radiogroup", { name: "Alternative causes" })).toBeNull());
        expect(within(fieldsetOf("Alternative causes")).getByRole("button", { name: "Change answer" })).toBeEnabled();
        expect(screen.queryByRole("textbox")).toBeNull();
        expect(save()).toBeDisabled();
    });

    it("keeps the recorded answer when a change is cancelled", () => {
        renderPanel({ alternative_causes: "no" });

        const alternative = fieldsetOf("Alternative causes");
        fireEvent.click(within(alternative).getByRole("button", { name: "Change answer" }));
        fireEvent.click(within(group("Alternative causes")).getByLabelText("Yes"));
        expect(screen.getByRole("status")).toHaveTextContent("Add the basis");
        fireEvent.click(within(alternative).getByRole("button", { name: "Keep recorded answer" }));

        expect(screen.queryByRole("radiogroup", { name: "Alternative causes" })).toBeNull();
        expect(within(alternative).getByText("No")).toBeInTheDocument();
        expect(screen.queryByRole("status")).toBeNull();
        expect(save()).toBeDisabled();
    });

    it("requires a basis for Yes or No and sends only the questions changed here", async () => {
        const onRecord = renderPanel();

        fireEvent.click(within(group("Alternative causes")).getByLabelText("No"));
        expect(save()).toBeDisabled();
        expect(screen.getByRole("status")).toHaveTextContent("Add the basis for each Yes or No answer.");
        const basis = screen.getByLabelText(/Basis for alternative causes/);
        expect(basis).toHaveAttribute("maxlength", "500");
        fireEvent.change(basis, { target: { value: "  No other medicine or condition explains it.  " } });
        fireEvent.click(within(group("Objective evidence")).getByLabelText("Not known"));
        expect(save()).toBeEnabled();

        fireEvent.click(save());

        await waitFor(() =>
            expect(onRecord).toHaveBeenCalledWith([
                {
                    question: "alternative_causes",
                    answer: "no",
                    basis: "No other medicine or condition explains it.",
                },
                { question: "objective_evidence", answer: "do_not_know" },
            ]),
        );
        await waitFor(() => expect(save()).toBeDisabled());
        expect(screen.queryByRole("textbox")).toBeNull();
    });

    it("keeps the staged answers when saving fails", async () => {
        const onRecord = vi.fn().mockRejectedValue(new Error("private diagnostic"));
        renderPanel({}, onRecord);
        fireEvent.click(within(group("Previous conclusive reports")).getByLabelText("Yes"));
        fireEvent.change(screen.getByLabelText(/Basis for previous conclusive reports/), {
            target: { value: "Listed in the product label." },
        });

        fireEvent.click(save());

        await waitFor(() => expect(onRecord).toHaveBeenCalledTimes(1));
        expect(screen.getByLabelText(/Basis for previous conclusive reports/)).toHaveValue(
            "Listed in the product label.",
        );
        expect(within(group("Previous conclusive reports")).getByLabelText("Yes")).toBeChecked();
        expect(screen.queryByText("private diagnostic")).toBeNull();
    });

    it("locks every control while disabled", () => {
        renderPanel({ alternative_causes: "no" }, undefined, true);
        for (const radio of screen.getAllByRole("radio")) expect(radio).toBeDisabled();
        expect(screen.getByRole("button", { name: "Change answer" })).toBeDisabled();
        expect(save()).toBeDisabled();
    });
});

describe("recordADRClinicianAnswers", () => {
    it("posts the answers and team and returns the recalculated score", async () => {
        const fetchMock = vi.fn().mockResolvedValue(
            new Response(JSON.stringify({ naranjo_score: 5, causality: "Probable" }), {
                status: 200,
                headers: { "Content-Type": "application/json" },
            }),
        );
        vi.stubGlobal("fetch", fetchMock);

        const result = await recordADRClinicianAnswers(
            "adr/1",
            [
                { question: "alternative_causes", answer: "no", basis: "Chart review." },
                { question: "objective_evidence", answer: "do_not_know" },
            ],
            "team-1",
        );

        expect(result).toEqual({ naranjoScore: 5, causality: "Probable" });
        const [url, init] = fetchMock.mock.calls[0];
        expect(String(url)).toBe(
            "http://localhost:8000/api/v1/clinicians/me/adr-assessments/adr%2F1/naranjo-answers",
        );
        expect(init.method).toBe("POST");
        expect(JSON.parse(init.body)).toEqual({
            answers: [
                { question: "alternative_causes", answer: "no", basis: "Chart review." },
                { question: "objective_evidence", answer: "do_not_know" },
            ],
            care_team_id: "team-1",
        });
    });
});
