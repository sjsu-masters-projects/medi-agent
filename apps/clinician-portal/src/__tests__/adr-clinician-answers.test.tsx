import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ADRClinicianAnswers } from "@/components/features/adr-clinician-answers";
import { recordADRClinicianAnswers } from "@/services/clinicians";

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
) {
    render(<ADRClinicianAnswers answers={answers} disabled={disabled} onRecord={onRecord} />);
    return onRecord;
}

function group(name: string) {
    return screen.getByRole("radiogroup", { name });
}

const save = () => screen.getByRole("button", { name: "Save clinician answers" });

describe("ADR clinician answers (PV-001-D)", () => {
    it("lists only the five clinical questions with their stored answers and points", () => {
        renderPanel({ alternative_causes: "no", dose_response: "yes" });

        for (const name of [
            "Previous conclusive reports",
            "Alternative causes",
            "Reappeared with placebo",
            "Toxic drug concentration",
            "Objective evidence",
        ]) {
            expect(group(name)).toBeInTheDocument();
        }
        // Patient questions are asked through Request information, never recorded here.
        expect(screen.queryByRole("radiogroup", { name: "Dose-response relationship" })).toBeNull();
        expect(screen.queryByRole("radiogroup", { name: "Event followed medication" })).toBeNull();
        const alternative = group("Alternative causes").closest("fieldset")!;
        expect(within(alternative).getByText(/Recorded: No/)).toBeInTheDocument();
        expect(within(alternative).getByText(/Yes -1, No \+2, Not known 0/)).toBeInTheDocument();
        expect(save()).toBeDisabled();
        expect(screen.queryByRole("textbox")).toBeNull();
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
        renderPanel({}, undefined, true);
        for (const radio of screen.getAllByRole("radio")) expect(radio).toBeDisabled();
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
