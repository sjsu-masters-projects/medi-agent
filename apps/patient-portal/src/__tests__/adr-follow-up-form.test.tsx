import { configureStore } from "@reduxjs/toolkit";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { Provider } from "react-redux";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ADRFollowUpForm } from "@/components/features/adr-follow-up-form";
import { getADRFollowUpCopy } from "@/content/adr-follow-up-copy";
import { ApiClientError } from "@/services/api";
import type {
    ADRFollowUpRequest,
    PatientADRAnswer,
    PatientADRQuestion,
} from "@/services/adr-follow-up";
import { authSlice, hydrateSession } from "@/store/slices/auth-slice";
import type { Locale } from "@/types";

const { respond } = vi.hoisted(() => ({ respond: vi.fn() }));

// Keep the real classifier: only the network call is replaced.
vi.mock("@/services/adr-follow-up", async (importActual) => {
    const actual = await importActual<typeof import("@/services/adr-follow-up")>();
    return { ...actual, respondToADRInformationRequest: respond };
});

function makeRequest(overrides: Partial<ADRFollowUpRequest> = {}): ADRFollowUpRequest {
    return {
        id: "request-1",
        assessmentId: "assessment-1",
        status: "pending",
        symptom: "dizziness",
        suspectMedicationName: "lisinopril",
        requestedInformation: ["dose_response", "similar_previous_reaction"],
        patientMessage: "Please describe what already happened.",
        createdAt: "2026-10-06T10:00:00Z",
        respondedAt: null,
        closedAt: null,
        responses: [],
        replacementRequestId: null,
        ...overrides,
    };
}

function renderForm(request: ADRFollowUpRequest, locale: Locale = "en-US") {
    const testStore = configureStore({ reducer: { auth: authSlice.reducer } });
    testStore.dispatch(
        hydrateSession({
            accessToken: "access-token",
            expiresAt: 9999999999,
            refreshToken: "refresh-token",
            user: {
                email: "maya@example.test",
                id: "patient-1",
                role: "patient",
            },
        }),
    );
    const onSent = vi.fn();
    const onClosed = vi.fn();
    const copy = getADRFollowUpCopy(locale);
    const rendered = render(
        <Provider store={testStore}>
            <ADRFollowUpForm
                copy={copy}
                locale={locale}
                onClosed={onClosed}
                onSent={onSent}
                request={request}
            />
        </Provider>,
    );
    return { ...rendered, copy, onClosed, onSent };
}

/** Answer every question "not sure", open the review step and confirm. */
function reachConfirmedReview(copy: ReturnType<typeof getADRFollowUpCopy>) {
    for (const radio of screen.getAllByLabelText(copy.answers.do_not_know)) {
        fireEvent.click(radio);
    }
    fireEvent.click(screen.getByRole("button", { name: copy.reviewAnswers }));
    fireEvent.click(screen.getByRole("checkbox"));
}

describe("ADR follow-up form", () => {
    beforeEach(() => {
        respond.mockReset();
    });

    // Migrated from the removed follow-up panel test ("collects, confirms, and
    // submits only retrospective patient evidence"). The panel fetched and showed
    // its own notice; the form receives the request and reports through onSent.
    it("collects, confirms, and submits only retrospective patient evidence", async () => {
        respond.mockResolvedValue({
            request_id: "request-1",
            adr_assessment_id: "assessment-1",
            status: "answered",
            naranjo_score: 4,
            causality: "Possible",
            responded_at: "2026-10-06T10:05:00Z",
        });

        const { onClosed, onSent } = renderForm(makeRequest());

        expect(screen.getByText('Reported symptom (original wording): “dizziness”')).toBeInTheDocument();
        expect(screen.getByText(/Do not restart, stop, or change/i)).toBeInTheDocument();
        expect(screen.queryByText(/placebo/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/objective evidence/i)).not.toBeInTheDocument();

        const fieldsets = screen.getAllByRole("group");
        fireEvent.click(within(fieldsets[0]).getByLabelText("Yes"));
        fireEvent.change(within(fieldsets[0]).getByRole("textbox"), {
            target: { value: "It improved after my clinician lowered the dose." },
        });
        fireEvent.click(within(fieldsets[1]).getByLabelText("I’m not sure"));

        fireEvent.click(screen.getByRole("button", { name: "Review answers" }));
        fireEvent.click(screen.getByRole("checkbox"));
        fireEvent.click(screen.getByRole("button", { name: "Send to care team" }));

        await waitFor(() =>
            expect(respond).toHaveBeenCalledWith("access-token", "request-1", [
                {
                    question: "dose_response",
                    answer: "yes",
                    evidence: "It improved after my clinician lowered the dose.",
                },
                {
                    question: "similar_previous_reaction",
                    answer: "do_not_know",
                    evidence: undefined,
                },
            ]),
        );
        // The old assertion on the "answers were sent" notice moved to the host
        // view; the form's contract is one onSent call and no close signal.
        await waitFor(() => expect(onSent).toHaveBeenCalledTimes(1));
        expect(onSent).toHaveBeenCalledWith("request-1");
        expect(onClosed).not.toHaveBeenCalled();
    });

    // Migrated from the removed follow-up panel test ("keeps the response visible and
    // retryable when submission fails"). The panel showed the server message; the
    // form shows the localized class copy and never the server text.
    it("keeps the response visible and retryable when submission fails", async () => {
        respond.mockRejectedValue(new Error("The response could not be saved."));

        const { copy, onClosed, onSent } = renderForm(
            makeRequest({ requestedInformation: ["dose_response"] }),
        );

        const fieldset = screen.getByRole("group");
        fireEvent.click(within(fieldset).getByLabelText("I’m not sure"));
        fireEvent.click(screen.getByRole("button", { name: "Review answers" }));
        fireEvent.click(screen.getByRole("checkbox"));
        fireEvent.click(screen.getByRole("button", { name: "Send to care team" }));

        const alert = await screen.findByRole("alert");
        expect(alert.textContent).toBe(copy.errors.other);
        expect(screen.queryByText(/could not be saved/i)).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Send to care team" })).toBeEnabled();
        expect(onClosed).not.toHaveBeenCalled();
        expect(onSent).not.toHaveBeenCalled();
    });

    describe("localized rendering", () => {
        it("renders every visible string in es-MX through the whole flow", async () => {
            respond.mockResolvedValue({});
            const { container, onSent } = renderForm(
                makeRequest({ requestedInformation: ["dose_response"] }),
                "es-MX",
            );

            expect(container.firstElementChild).toHaveAttribute("lang", "es-MX");
            expect(screen.getByText("Seguimiento de tu equipo de atención")).toBeInTheDocument();
            expect(screen.getByText("Síntoma reportado (texto original): «dizziness»")).toBeInTheDocument();
            expect(screen.getByText("Medicamento (nombre registrado): lisinopril.")).toBeInTheDocument();
            expect(screen.getByText("Mensaje de tu equipo de atención")).toBeInTheDocument();
            expect(screen.getByText(/^Responde solo con lo que ya pasó/)).toBeInTheDocument();
            expect(screen.getByText(/^Antes de esta solicitud, ¿el síntoma cambió/)).toBeInTheDocument();
            expect(screen.getByLabelText("Sí")).toBeInTheDocument();
            expect(screen.getByLabelText("No")).toBeInTheDocument();
            expect(screen.getByLabelText("No sé")).toBeInTheDocument();
            for (const english of ["Yes", "I’m not sure", "Review answers", "Care team follow-up"]) {
                expect(screen.queryByText(english)).not.toBeInTheDocument();
            }

            fireEvent.click(screen.getByLabelText("Sí"));
            fireEvent.change(screen.getByLabelText("Describe el cambio de dosis y qué pasó."), {
                target: { value: "Mejoró." },
            });
            expect(screen.getByText("7 de 500 caracteres")).toBeInTheDocument();

            fireEvent.click(screen.getByRole("button", { name: "Revisar respuestas" }));
            expect(screen.getByRole("heading", { name: "Revisa antes de enviar" })).toBeInTheDocument();
            expect(screen.getByText("Qué pasó tras un cambio de dosis anterior")).toBeInTheDocument();
            expect(screen.getByText(/^Tus respuestas solo se guardan cuando las envías/)).toBeInTheDocument();
            expect(screen.getByRole("button", { name: "Editar" })).toBeInTheDocument();
            expect(screen.queryByText("Review before sending")).not.toBeInTheDocument();

            fireEvent.click(screen.getByLabelText(/^Confirmo que estas respuestas describen lo que ya pasó/));
            fireEvent.click(screen.getByRole("button", { name: "Enviar al equipo de atención" }));
            await waitFor(() => expect(onSent).toHaveBeenCalledWith("request-1"));
            expect(respond).toHaveBeenCalledWith("access-token", "request-1", [
                { question: "dose_response", answer: "yes", evidence: "Mejoró." },
            ]);
        });

        it("sets lang to the locale on the root of the form", () => {
            const en = renderForm(makeRequest(), "en-US");
            expect(en.container.firstElementChild).toHaveAttribute("lang", "en-US");
            en.unmount();
            const es = renderForm(makeRequest(), "es-MX");
            expect(es.container.firstElementChild).toHaveAttribute("lang", "es-MX");
        });

        it.each<Locale>(["en-US", "es-MX"])(
            "shows the clinician message, symptom and medication exactly as stored (%s)",
            (locale) => {
                const symptom = 'mareo <b>severo</b> & "agudo" ñ';
                const medication = "Lisinopril/HCTZ 10 mg (½ tab)";
                const message = "Línea uno.\n  Línea dos  con espacios & <i>tags</i>.";
                const { container, copy } = renderForm(
                    makeRequest({
                        symptom,
                        suspectMedicationName: medication,
                        patientMessage: message,
                    }),
                    locale,
                );

                expect(container.querySelector("h2")?.textContent).toBe(copy.heading(symptom));
                expect(screen.getByText(copy.reportedWith(medication))).toBeInTheDocument();
                const messageNode = screen.getByText(message, { normalizer: (text) => text });
                expect(messageNode.textContent).toBe(message);
                expect(screen.getByText(copy.careTeamMessage)).toBeInTheDocument();
                // Stored text is rendered as text, never parsed as markup.
                expect(container.querySelector("b, i")).toBeNull();
            },
        );

        it("omits the care-team message block when the stored message is blank", () => {
            const { copy } = renderForm(makeRequest({ patientMessage: "   " }));
            expect(screen.queryByText(copy.careTeamMessage)).not.toBeInTheDocument();
        });
    });

    describe("touch targets, focus ring and check glyph", () => {
        it("gives every option label and the confirmation label the 44 px height and focus ring", () => {
            const { container, copy } = renderForm(makeRequest());

            const optionLabels = Array.from(
                container.querySelectorAll<HTMLInputElement>('input[type="radio"]'),
            ).map((radio) => radio.closest("label"));
            expect(optionLabels).toHaveLength(6);
            for (const label of optionLabels) {
                expect(label).not.toBeNull();
                expect(label?.classList.contains("min-h-11")).toBe(true);
                expect(label?.classList.contains("has-[:focus-visible]:ring-4")).toBe(true);
            }

            reachConfirmedReview(copy);
            const confirmation = screen.getByRole("checkbox").closest("label");
            expect(confirmation?.classList.contains("min-h-11")).toBe(true);
            expect(confirmation?.classList.contains("has-[:focus-visible]:ring-4")).toBe(true);
        });

        it("shows the check icon only on the selected option", () => {
            const { container, copy } = renderForm(makeRequest());
            const labelOf = (fieldsetIndex: number, answer: PatientADRAnswer) =>
                container
                    .querySelectorAll("fieldset")
                    [fieldsetIndex].querySelector(`input[value="${answer}"]`)
                    ?.closest("label") as HTMLLabelElement;
            const checkedLabels = () =>
                Array.from(container.querySelectorAll("label")).filter((label) =>
                    label.querySelector("svg"),
                );

            expect(checkedLabels()).toHaveLength(0);

            fireEvent.click(screen.getAllByLabelText(copy.answers.yes)[0]);
            expect(checkedLabels()).toEqual([labelOf(0, "yes")]);

            fireEvent.click(screen.getAllByLabelText(copy.answers.no)[0]);
            expect(checkedLabels()).toEqual([labelOf(0, "no")]);

            fireEvent.click(screen.getAllByLabelText(copy.answers.do_not_know)[1]);
            expect(checkedLabels()).toEqual([labelOf(0, "no"), labelOf(1, "do_not_know")]);
        });

        it("renders no AI tint, AI chip or approval seal markup in either step", () => {
            const { container, copy } = renderForm(makeRequest());
            const expectNoAiOrSeal = () => {
                expect(container.querySelector(".bg-ai-tint")).toBeNull();
                // ApprovalSeal: text-brand-ink wrapper with a rounded-[5px] check tile.
                expect(container.querySelector(".text-brand-ink")).toBeNull();
                expect(container.querySelector(".bg-brand-tint")).toBeNull();
                expect(container.querySelector('[class*="rounded-[5px]"]')).toBeNull();
                // AiChip: filled spark glyph.
                expect(container.querySelector('svg[fill="currentColor"]')).toBeNull();
            };
            expectNoAiOrSeal();
            reachConfirmedReview(copy);
            expectNoAiOrSeal();
        });
    });

    describe("focus management", () => {
        it("moves focus to the review heading after Review and back to Review after Edit", () => {
            const { copy } = renderForm(makeRequest({ requestedInformation: ["dose_response"] }));
            expect(document.body).toHaveFocus();

            fireEvent.click(screen.getByLabelText(copy.answers.do_not_know));
            fireEvent.click(screen.getByRole("button", { name: copy.reviewAnswers }));
            expect(screen.getByRole("heading", { name: copy.reviewHeading })).toHaveFocus();

            fireEvent.click(screen.getByRole("button", { name: copy.edit }));
            expect(screen.getByRole("button", { name: copy.reviewAnswers })).toHaveFocus();
            expect(screen.getByLabelText(copy.answers.do_not_know)).toBeChecked();
        });
    });

    describe("failed submissions", () => {
        const SERVER_TEXT = "Server said: request 9f1c already completed";
        const CASES = [
            { errorClass: "closed", status: 422, code: "ADR_REQUEST_CLOSED", terminal: true },
            { errorClass: "notFound", status: 404, code: "NOT_FOUND", terminal: true },
            { errorClass: "unavailable", status: 503, code: "UNAVAILABLE", terminal: false },
            { errorClass: "other", status: 500, code: "INTERNAL_ERROR", terminal: false },
        ] as const;
        const TABLE = (["en-US", "es-MX"] as const).flatMap((locale) =>
            CASES.map((item) => ({ ...item, locale })),
        );

        it.each(TABLE)(
            "$errorClass ($status) shows the $locale copy and never the server text",
            async ({ errorClass, status, code, terminal, locale }) => {
                respond.mockRejectedValueOnce(
                    new ApiClientError(SERVER_TEXT, status, {
                        error: { code, message: SERVER_TEXT },
                    }),
                );
                const { copy, onClosed, onSent } = renderForm(makeRequest(), locale);
                reachConfirmedReview(copy);
                const send = screen.getByRole("button", { name: copy.send });
                fireEvent.click(send);

                const alert = await screen.findByRole("alert");
                expect(alert.textContent).toBe(copy.errors[errorClass]);
                expect(screen.queryByText(/Server said/)).not.toBeInTheDocument();
                expect(onSent).not.toHaveBeenCalled();

                if (terminal) {
                    // Closed and not-found requests are handed back to the host once
                    // and cannot be retried from here.
                    expect(onClosed).toHaveBeenCalledTimes(1);
                    expect(screen.getByRole("button", { name: copy.send })).toBeDisabled();
                    expect(screen.getByRole("button", { name: copy.edit })).toBeDisabled();
                    expect(screen.getByRole("checkbox")).toBeDisabled();
                    fireEvent.click(screen.getByRole("button", { name: copy.send }));
                    expect(respond).toHaveBeenCalledTimes(1);
                    expect(onClosed).toHaveBeenCalledTimes(1);
                } else {
                    expect(onClosed).not.toHaveBeenCalled();
                    expect(screen.getByRole("button", { name: copy.send })).toBeEnabled();
                }
            },
        );

        it("keeps the answers when the service is unavailable and sends the same payload on retry", async () => {
            respond
                .mockRejectedValueOnce(new ApiClientError("Bad gateway", 503, { detail: "x" }))
                .mockResolvedValueOnce({});
            const { copy, onClosed, onSent } = renderForm(makeRequest());
            const fieldsets = screen.getAllByRole("group");
            fireEvent.click(within(fieldsets[0]).getByLabelText(copy.answers.no));
            fireEvent.change(within(fieldsets[0]).getByRole("textbox"), {
                target: { value: "  Nothing changed.  " },
            });
            fireEvent.click(within(fieldsets[1]).getByLabelText(copy.answers.do_not_know));
            fireEvent.click(screen.getByRole("button", { name: copy.reviewAnswers }));
            fireEvent.click(screen.getByRole("checkbox"));

            fireEvent.click(screen.getByRole("button", { name: copy.send }));
            expect((await screen.findByRole("alert")).textContent).toBe(copy.errors.unavailable);

            // Answers survive a trip back to the edit step.
            fireEvent.click(screen.getByRole("button", { name: copy.edit }));
            expect(screen.queryByRole("alert")).not.toBeInTheDocument();
            expect(within(screen.getAllByRole("group")[0]).getByRole("textbox")).toHaveValue(
                "  Nothing changed.  ",
            );
            fireEvent.click(screen.getByRole("button", { name: copy.reviewAnswers }));

            fireEvent.click(screen.getByRole("button", { name: copy.send }));
            await waitFor(() => expect(onSent).toHaveBeenCalledWith("request-1"));
            expect(respond).toHaveBeenCalledTimes(2);
            expect(respond.mock.calls[1]).toEqual(respond.mock.calls[0]);
            expect(respond.mock.calls[1][2]).toEqual([
                { question: "dose_response", answer: "no", evidence: "Nothing changed." },
                { question: "similar_previous_reaction", answer: "do_not_know" },
            ]);
            expect(onClosed).not.toHaveBeenCalled();
            expect(screen.queryByRole("alert")).not.toBeInTheDocument();
        });
    });

    describe("browser storage", () => {
        it("never writes draft answers to localStorage, sessionStorage or cookies", async () => {
            // Node 24 exposes a different global `Storage` constructor from jsdom.
            // Spy on each actual storage prototype so Window's getter can return a
            // fresh wrapper without bypassing the control below.
            const storages = [window.localStorage, window.sessionStorage];
            const targets = Array.from(new Set<Pick<Storage, "setItem">>(storages.map((storage) => {
                const prototype = Object.getPrototypeOf(storage) as object | null;
                return (prototype && "setItem" in prototype ? prototype : storage) as Pick<Storage, "setItem">;
            })));
            const storageSpies = targets.map((target) => vi.spyOn(target, "setItem"));
            const writeCount = () => storageSpies.reduce(
                (count, spy) => count + spy.mock.calls.length,
                0,
            );
            const cookiesBefore = document.cookie;
            try {
                respond
                    .mockRejectedValueOnce(new ApiClientError("Unavailable", 503, null))
                    .mockResolvedValueOnce({});
                const { copy, onSent } = renderForm(makeRequest());
                const fieldsets = screen.getAllByRole("group");
                fireEvent.click(within(fieldsets[0]).getByLabelText(copy.answers.yes));
                fireEvent.change(within(fieldsets[0]).getByRole("textbox"), {
                    target: { value: "It eased after the dose change." },
                });
                fireEvent.click(within(fieldsets[1]).getByLabelText(copy.answers.do_not_know));
                fireEvent.click(screen.getByRole("button", { name: copy.reviewAnswers }));
                fireEvent.click(screen.getByRole("checkbox"));
                fireEvent.click(screen.getByRole("button", { name: copy.send }));
                await screen.findByRole("alert");
                fireEvent.click(screen.getByRole("button", { name: copy.send }));
                await waitFor(() => expect(onSent).toHaveBeenCalledTimes(1));

                expect(writeCount()).toBe(0);
                expect(document.cookie).toBe(cookiesBefore);

                // Control: the spy is live, so the assertions above are meaningful.
                const callsBefore = writeCount();
                window.sessionStorage.setItem("__probe__", "1");
                expect(writeCount()).toBe(callsBefore + 1);
                window.sessionStorage.removeItem("__probe__");
            } finally {
                storageSpies.forEach((spy) => spy.mockRestore());
            }
        });
    });
});

// ── Property 5 ──────────────────────────────────────────────

// Fixed, non-alphabetical order so the payload order is the request order.
const REQUEST_ORDER: PatientADRQuestion[] = [
    "similar_previous_reaction",
    "dose_response",
    "reappeared_on_rechallenge",
];
const ANSWER_CHOICES = ["unanswered", "yes", "no", "do_not_know"] as const;
const EVIDENCE_CHOICES = ["", "   ", "x", "e".repeat(500)] as const;

interface Cell {
    answer: (typeof ANSWER_CHOICES)[number];
    evidence: string;
}

// Evidence is only enterable once "Yes" or "No" is chosen, so "unanswered" has
// one cell. "do_not_know" keeps all four: the text is typed under "Yes" first and
// the answer is then switched, which must not leak the text into the payload.
const CELLS: Cell[] = ANSWER_CHOICES.flatMap((answer): Cell[] =>
    answer === "unanswered"
        ? [{ answer, evidence: "" }]
        : EVIDENCE_CHOICES.map((evidence) => ({ answer, evidence })),
);

function product<T>(items: readonly T[], size: number): T[][] {
    let combos: T[][] = [[]];
    for (let position = 0; position < size; position += 1) {
        combos = combos.flatMap((prefix) => items.map((item) => [...prefix, item]));
    }
    return combos;
}

function cellComplete(cell: Cell): boolean {
    if (cell.answer === "unanswered") return false;
    return cell.answer === "do_not_know" || cell.evidence.trim() !== "";
}

function describeCombo(combo: Cell[]): string {
    return combo
        .map((cell) => `${cell.answer}:${JSON.stringify(cell.evidence.slice(0, 5))}(${cell.evidence.length})`)
        .join(" | ");
}

function fillCell(container: HTMLElement, index: number, cell: Cell, typed: string) {
    if (cell.answer === "unanswered") return;
    const fieldset = container.querySelectorAll("fieldset")[index];
    const choose = (answer: PatientADRAnswer) => {
        const radio = fieldset.querySelector(`input[type="radio"][value="${answer}"]`);
        if (!radio) throw new Error(`Missing ${answer} option for question ${index}`);
        fireEvent.click(radio);
    };
    const type = () => {
        const textarea = fieldset.querySelector("textarea");
        if (!textarea) throw new Error(`Missing evidence field for question ${index}`);
        fireEvent.change(textarea, { target: { value: typed } });
    };
    if (cell.answer === "do_not_know") {
        if (typed) {
            choose("yes");
            type();
        }
        choose("do_not_know");
        return;
    }
    choose(cell.answer);
    if (typed) type();
}

function reviewButton(container: HTMLElement, label: string): HTMLButtonElement {
    const button = within(container).getByText(label).closest("button");
    if (!button) throw new Error(`Missing button ${label}`);
    return button;
}

/** Every `step`-th item starting at `offset`: a deterministic sample. */
function everyNth<T>(items: readonly T[], step: number, offset = 0): T[] {
    return items.filter((_, position) => position % step === offset);
}

// Feature: adr-loop-gap-fixes, Property 5: Review is enabled exactly for complete answers, with an unchanged payload
// **Validates: Requirements 3.9**
describe("Property 5: Review is enabled exactly for complete answers, with an unchanged payload", () => {
    beforeEach(() => {
        respond.mockReset();
    });

    function checkReviewEnabled(size: number, combos: Cell[][]) {
        const questions = REQUEST_ORDER.slice(0, size);
        const outcomes = new Set<boolean>();
        for (const combo of combos) {
            const { container, copy, unmount } = renderForm(
                makeRequest({ requestedInformation: questions }),
            );
            combo.forEach((cell, index) => fillCell(container, index, cell, cell.evidence));
            const expected = combo.every(cellComplete);
            outcomes.add(expected);
            expect(
                reviewButton(container, copy.reviewAnswers).disabled,
                `Review answers should be ${expected ? "enabled" : "disabled"} for ${describeCombo(combo)}`,
            ).toBe(!expected);
            unmount();
        }
        return outcomes;
    }

    it("is exhaustive for one question (13 cells)", () => {
        const outcomes = checkReviewEnabled(1, product(CELLS, 1));
        expect(outcomes).toEqual(new Set([true, false]));
    }, 20_000);

    it("is exhaustive for two questions (169 combinations)", () => {
        const combos = product(CELLS, 2);
        expect(combos).toHaveLength(CELLS.length ** 2);
        const outcomes = checkReviewEnabled(2, combos);
        expect(outcomes).toEqual(new Set([true, false]));
    }, 25_000);

    it("holds on a deterministic sample for three questions", () => {
        const combos = everyNth(product(CELLS, 3), 7);
        expect(combos.length).toBeGreaterThan(70);
        const outcomes = checkReviewEnabled(3, combos);
        expect(outcomes).toEqual(new Set([true, false]));
    }, 25_000);

    function checkPayload(size: number, combos: Cell[][]) {
        const questions = REQUEST_ORDER.slice(0, size);
        return async () => {
            for (const combo of combos) {
                respond.mockReset();
                respond.mockResolvedValue({});
                const typedByCell = combo.map((cell) =>
                    // Pad short text so trimming is observable; the 500-character
                    // value is already at the field limit.
                    cell.evidence.trim() && cell.evidence.length < 500
                        ? `  ${cell.evidence} \n`
                        : cell.evidence,
                );
                const { container, copy, onSent, unmount } = renderForm(
                    makeRequest({ requestedInformation: questions }),
                );
                combo.forEach((cell, index) => fillCell(container, index, cell, typedByCell[index]));
                fireEvent.click(reviewButton(container, copy.reviewAnswers));
                fireEvent.click(within(container).getByRole("checkbox"));
                fireEvent.click(reviewButton(container, copy.send));
                await waitFor(() => expect(onSent).toHaveBeenCalledTimes(1));

                expect(respond).toHaveBeenCalledTimes(1);
                const [token, requestId, payload] = respond.mock.calls[0];
                expect(token).toBe("access-token");
                expect(requestId).toBe("request-1");
                expect(payload).toHaveLength(size);
                payload.forEach(
                    (
                        item: { question: string; answer: string; evidence?: string },
                        index: number,
                    ) => {
                        const cell = combo[index];
                        const label = `${describeCombo(combo)} @${index}`;
                        expect(Object.keys(item).sort().every((key) =>
                            ["answer", "evidence", "question"].includes(key),
                        ), label).toBe(true);
                        expect(item.question, label).toBe(questions[index]);
                        expect(item.answer, label).toBe(cell.answer);
                        if (cell.answer === "do_not_know") {
                            expect(item.evidence, label).toBeUndefined();
                        } else {
                            expect(item.evidence, label).toBe(typedByCell[index].trim());
                        }
                    },
                );
                unmount();
            }
        };
    }

    const completeCombos = (size: number) =>
        product(CELLS, size).filter((combo) => combo.every(cellComplete));

    it("sends [{question, answer, evidence?}] in request order, trimmed (1 question, all 8 complete cells)", async () => {
        const combos = completeCombos(1);
        expect(combos).toHaveLength(8);
        await checkPayload(1, combos)();
    }, 20_000);

    it("sends the same payload shape for two questions (sample of 32 of 64 complete combinations)", async () => {
        const combos = everyNth(completeCombos(2), 2);
        expect(combos.length).toBeGreaterThan(10);
        await checkPayload(2, combos)();
    }, 25_000);

    it("sends the same payload shape for three questions (sample of 47 of 512 complete combinations)", async () => {
        const combos = everyNth(completeCombos(3), 11);
        expect(combos.length).toBeGreaterThan(10);
        await checkPayload(3, combos)();
    }, 25_000);
});
