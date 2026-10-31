import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Provider } from "react-redux";
import { beforeEach, expect, it, vi } from "vitest";
import { SymptomIntakePanel } from "@/components/features/symptom-intake-panel";
import { store } from "@/store/store";
import { hydrateSession, logout } from "@/store/slices/auth-slice";
import type { SymptomIntake } from "@/types";
import { ApiClientError } from "@/services/api";
import { getSymptomIntakeCopy } from "@/content/symptom-intake-copy";

const { active, read, start, mutate } = vi.hoisted(() => ({ active: vi.fn(), read: vi.fn(), start: vi.fn(), mutate: vi.fn() }));
vi.mock("@/services/symptom-intakes", () => ({ fetchActiveIntake: active, fetchIntake: read, startIntake: start, mutateIntake: mutate }));
const question = { id: "severity", answer_type: "rating" as const, wording: { "en-US": "Choose your severity", "es-MX": "Elige tu intensidad" } };
const draft: SymptomIntake = { intake_id: "synthetic-intake", status: "collecting", revision: 0, locale: "en-US", timezone: "America/Los_Angeles", timezone_fallback: false,
    answers: {}, current_question: question, questions: [question], library_available: true, can_review: false, can_confirm: false };
function login(id = "patient-A") { store.dispatch(hydrateSession({ accessToken: id, refreshToken: "synthetic", expiresAt: 9999999999, user: { id, email: `${id}@synthetic.invalid`, role: "patient" } })); }
function panel(locale: "en-US" | "es-MX" = "en-US", sessionId = "default") { return <Provider store={store}><SymptomIntakePanel locale={locale} sessionId={sessionId} sourceMessageId="source-turn" /></Provider>; }
beforeEach(() => { vi.resetAllMocks(); login(); active.mockResolvedValue(structuredClone(draft)); });

it.each(["en-US", "es-MX"] as const)("names intake regions by their actual saved state in %s", async (locale) => {
    const copy = getSymptomIntakeCopy(locale);
    for (const [status, title] of [
        ["collecting", copy.title], ["confirmed", copy.saved],
        ["cancelled", copy.cancelled], ["interrupted_safety", copy.interrupted],
    ] as const) {
        active.mockResolvedValue({ ...draft, locale, status, current_question: null });
        const view = render(panel(locale));
        expect(await screen.findByRole("heading", { name: title })).toBeInTheDocument();
        expect(screen.getByRole("region", { name: title })).toHaveAttribute("lang", locale);
        if (status !== "collecting") expect(screen.queryByRole("region", { name: copy.title })).not.toBeInTheDocument();
        expect(mutate).not.toHaveBeenCalled();
        view.unmount();
    }
});

it("recovers the owned draft without writing or mirroring answers into chat", async () => {
    render(panel());
    expect(await screen.findByText("Draft — not submitted")).toBeInTheDocument();
    expect(screen.getByText(/Times use Pacific Time/)).toBeInTheDocument();
    expect(screen.queryByText(/America\/Los_Angeles/)).not.toBeInTheDocument();
    expect(mutate).not.toHaveBeenCalled();
    act(() => window.dispatchEvent(new Event("symptom-intake-updated")));
    await waitFor(() => expect(active).toHaveBeenCalledTimes(2));
});

it.each(["en-US", "es-MX"] as const)("saves unknown as null and never selects a rating in %s", async (locale) => {
    active.mockResolvedValue({ ...draft, locale });
    mutate.mockResolvedValue({ ...draft, answers: { severity: { question_id: "severity", state: "unknown", value: null, wording: "", locale } }, revision: 1, current_question: null });
    render(panel(locale));
    const select = await screen.findByLabelText(question.wording[locale]);
    expect(select).toHaveValue("");
    fireEvent.click(screen.getByText(locale === "es-MX" ? "No sé" : "I don’t know"));
    await waitFor(() => expect(mutate).toHaveBeenCalled());
    expect(mutate.mock.calls[0][3]).toMatchObject({ expected_revision: 0, state: "unknown", value: null, locale });
});

it("does not let speech or a prechecked box establish confirmation", async () => {
    active.mockResolvedValue({ ...draft, status: "ready_for_confirmation", current_question: null, can_review: true, can_confirm: true, preview_hash: "a".repeat(64),
        preview: { schema_version: "symptom-report/1", answers: {}, summary: "Original patient testimony", context: { purpose: "patient_symptom_preview", version: "symptom-context/1", medications: [], facts: [], excerpts: [] }, source_message_id: "source-turn", session_id: "default" } });
    render(panel());
    const confirm = await screen.findByText("Confirm and share with my care team");
    expect(confirm).toBeDisabled();
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(confirm);
    await waitFor(() => expect(mutate).toHaveBeenCalled());
    expect(mutate.mock.calls[0][2]).toBe("confirm");
    expect(mutate.mock.calls[0][3]).toMatchObject({ preview_hash: "a".repeat(64), consent: true });
});

it.each(["en-US", "es-MX"] as const)("reuses the exact confirmation identity after an uncertain save in %s", async (locale) => {
    const copy = getSymptomIntakeCopy(locale);
    const ready = { ...draft, locale, status: "ready_for_confirmation", current_question: null, can_review: true, can_confirm: true, preview_hash: "a".repeat(64),
        preview: { schema_version: "symptom-report/1", answers: {}, summary: "Original patient testimony", context: { purpose: "patient_symptom_preview", version: "symptom-context/1", medications: [], facts: [], excerpts: [] }, source_message_id: "source-turn", session_id: "default" } };
    active.mockResolvedValue(ready); read.mockResolvedValue(ready);
    mutate.mockRejectedValueOnce(new Error("synthetic lost response")).mockResolvedValue({ ...ready, status: "confirmed", confirmed_report_id: "one-report" });
    render(panel(locale)); await screen.findByRole("checkbox"); fireEvent.click(screen.getByRole("checkbox")); fireEvent.click(screen.getByText(copy.confirm));
    await screen.findByText(copy.error);
    const original = mutate.mock.calls[0][3];
    fireEvent.click(screen.getByText(copy.reload)); await waitFor(() => expect(read).toHaveBeenCalled());
    // Reload only reconciles saved truth; it must not re-submit the confirmation.
    expect(mutate).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByText(copy.retry));
    await waitFor(() => expect(mutate).toHaveBeenCalledTimes(2));
    expect(mutate.mock.calls[1][3]).toEqual(original);
});

it("discards late private content from another authenticated session", async () => {
    let resolve: (result: SymptomIntake) => void = () => {};
    active.mockImplementationOnce(() => new Promise<SymptomIntake>((done) => { resolve = done; })).mockResolvedValue(null);
    render(panel());
    act(() => { store.dispatch(logout()); login("patient-B"); });
    await act(async () => resolve(draft));
    expect(screen.queryByText("Choose your severity")).not.toBeInTheDocument();
});

it("binds recovery and manual start to the selected Nora conversation", async () => {
    active.mockResolvedValue(null);
    start.mockResolvedValue(draft);
    render(panel("en-US", "nora-thread-A"));
    await waitFor(() => expect(active).toHaveBeenCalled());
    // Nothing starts or shows until the patient answers a server-issued offer.
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(start).not.toHaveBeenCalled();
    act(() => window.dispatchEvent(new CustomEvent("symptom-intake-start", { detail: { sourceMessageId: "source-turn" } })));
    await waitFor(() => expect(start).toHaveBeenCalled());
    expect(start.mock.calls[0][1]).toBe("source-turn");
    expect(active.mock.calls[0][1]).toBe("nora-thread-A");
    expect(start.mock.calls[0][2]).toBe("nora-thread-A");
});

it("discards late private content when switching Nora conversations", async () => {
    let resolve: (result: SymptomIntake) => void = () => {};
    active.mockImplementationOnce(() => new Promise<SymptomIntake>((done) => { resolve = done; })).mockResolvedValue(null);
    const view = render(panel("en-US", "nora-thread-A"));
    view.rerender(panel("en-US", "nora-thread-B"));
    await act(async () => resolve(draft));
    expect(screen.queryByText("Choose your severity")).not.toBeInTheDocument();
    expect(active.mock.calls.at(-1)?.[1]).toBe("nora-thread-B");
});

it("cancels a private draft and retains an honest chat-history explanation", async () => {
    mutate.mockResolvedValue({ ...draft, status: "cancelled", current_question: null });
    render(panel());
    fireEvent.click(await screen.findByText("Cancel draft"));
    expect(await screen.findByText(/Your chat history was not deleted/)).toBeInTheDocument();
    expect(mutate.mock.calls[0][2]).toBe("cancel");
});

it("recovers a completed save without offering another pending confirmation", async () => {
    const ready = { ...draft, status: "ready_for_confirmation" as const, current_question: null, can_review: true, can_confirm: true,
        preview_hash: "a".repeat(64), preview: { schema_version: "symptom-report/1", answers: {}, summary: "Synthetic testimony",
            context: { purpose: "patient_symptom_preview", version: "symptom-context/1", medications: [], facts: [], excerpts: [] }, source_message_id: "source-turn", session_id: "default" } };
    active.mockResolvedValue(ready); read.mockResolvedValue({ ...ready, status: "confirmed", confirmed_report_id: "one-report" });
    mutate.mockRejectedValueOnce(new Error("synthetic lost response"));
    render(panel()); fireEvent.click(await screen.findByRole("checkbox")); fireEvent.click(screen.getByText("Confirm and share with my care team"));
    fireEvent.click(await screen.findByText("Reload saved state"));
    await screen.findByRole("heading", { name: "Report saved for care-team review" });
    expect(screen.queryByText(/one-report/)).not.toBeInTheDocument();
    expect(screen.queryByText("Retry the same action")).not.toBeInTheDocument();
    expect(mutate).toHaveBeenCalledTimes(1);
});

it("focuses the labelled unanswered control and keeps a rating blank", async () => {
    render(panel()); const control = await screen.findByLabelText("Choose your severity");
    expect(control).toHaveFocus(); expect(control).toHaveValue("");
    expect(screen.getByRole("group", { name: "Your answer" })).toBeInTheDocument();
});

it("stops a hung recovery read without claiming the draft is absent or saved", async () => {
    vi.useFakeTimers();
    active.mockImplementation((_token, _session, signal) => new Promise((_resolve, reject) => {
        signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), { once: true });
    }));
    try {
        render(panel());
        await act(async () => { await vi.advanceTimersByTimeAsync(12000); });
        expect(screen.getByText(/We could not load symptom drafts/)).toBeInTheDocument();
        expect(screen.queryByText("Start a symptom draft")).not.toBeInTheDocument();
        expect(screen.queryByText(/Report saved for care-team review/)).not.toBeInTheDocument();
        expect(mutate).not.toHaveBeenCalled();
    } finally { vi.useRealTimers(); }
});

it("distinguishes a failed initial read from a save and clears its error while reloading", async () => {
    active.mockRejectedValueOnce(new ApiClientError("Unavailable", 422, { error: { code: "INTAKE_PERSISTENCE_UNAVAILABLE" } }));
    render(panel());
    await screen.findByText(/We could not load symptom drafts/);
    expect(screen.queryByText(/We could not verify this action/)).not.toBeInTheDocument();
    let resolve: (result: SymptomIntake | null) => void = () => {};
    active.mockImplementationOnce(() => new Promise<SymptomIntake | null>((done) => { resolve = done; }));
    fireEvent.click(screen.getByRole("button", { name: "Reload saved state" }));
    expect(screen.getByText("Loading your draft…")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await act(async () => resolve(null));
    await waitFor(() => expect(screen.queryByText("Loading your draft…")).not.toBeInTheDocument());
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(start).not.toHaveBeenCalled();
});

it.each(["en-US", "es-MX"] as const)("preserves unavailable-library feedback on recovery in %s", async (locale) => {
    active.mockRejectedValue(new ApiClientError("Unavailable", 422, { error: { code: "INTAKE_LIBRARY_UNAVAILABLE" } }));
    render(panel(locale));
    expect(await screen.findByText(locale === "en-US" ? /Guided intake is unavailable/ : /La captura guiada no está disponible/)).toBeInTheDocument();
    expect(screen.queryByText(locale === "en-US" ? "Start a symptom draft" : "Iniciar un borrador de síntomas")).not.toBeInTheDocument();
});

it("routes spoken answers privately and never treats spoken assent as confirmation", async () => {
    const register = vi.fn();
    const reader = vi.fn();
    mutate.mockResolvedValue({ ...draft, revision: 1 });
    render(<Provider store={store}><SymptomIntakePanel locale="en-US" registerReply={register} onReadAloud={reader} handsFree /></Provider>);
    await screen.findByText("Type or speak your answer below. You can say “not sure” or “skip”.");
    await waitFor(() => expect(reader).toHaveBeenCalledWith(expect.stringContaining("Choose your severity"), "en-US"));
    const handler = register.mock.calls.at(-1)?.[0];
    act(() => { expect(handler("cinco", "voice", "es-MX")).toBe("handled"); });
    await waitFor(() => expect(mutate).toHaveBeenCalled());
    expect(mutate.mock.calls[0][2]).toBe("reply");
    expect(mutate.mock.calls[0][3]).toMatchObject({ text: "cinco", input_mode: "voice", question_id: "severity", locale: "es-MX" });
});

it("requires a separate acceptance of source suggestions", async () => {
    active.mockResolvedValue({ ...draft, suggestions: { severity: 5 } });
    render(panel());
    await screen.findByText("From your message");
    expect(mutate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Use this answer"));
    await waitFor(() => expect(mutate).toHaveBeenCalled());
    expect(mutate.mock.calls[0][3]).toMatchObject({ value: 5, state: "answered" });
});

it("does not carry an unsaved answer into another draft at the same revision", async () => {
    const register = vi.fn();
    mutate.mockRejectedValue(new Error("synthetic connection loss"));
    render(<Provider store={store}><SymptomIntakePanel locale="en-US" registerReply={register} /></Provider>);
    await screen.findByText("Type or speak your answer below. You can say “not sure” or “skip”.");
    act(() => { register.mock.calls.at(-1)?.[0]("five", "typed"); });
    await screen.findByText("Your answer — not yet verified as saved");
    active.mockResolvedValue({ ...draft, intake_id: "another-synthetic-intake" });
    act(() => window.dispatchEvent(new Event("symptom-intake-updated")));
    await waitFor(() => expect(screen.queryByText("Your answer — not yet verified as saved")).not.toBeInTheDocument());
    expect(screen.queryByText("five")).not.toBeInTheDocument();
});

it("does not carry a correction question into a new draft", async () => {
    const register = vi.fn();
    active.mockResolvedValue({ ...draft, current_question: null, can_review: true,
        answers: { severity: { question_id: "severity", state: "unknown", value: null, wording: "", locale: "en-US" } } });
    render(<Provider store={store}><SymptomIntakePanel locale="en-US" registerReply={register} /></Provider>);
    await screen.findByText("What you reported");
    fireEvent.click(screen.getByText("What you reported"));
    fireEvent.click(screen.getByRole("button", { name: /^Edit$/ }));
    expect(screen.getByText("Type or speak your answer below. You can say “not sure” or “skip”.")).toBeInTheDocument();
    const description = { id: "description", answer_type: "text" as const, wording: { "en-US": "Describe the new symptom", "es-MX": "Describe el nuevo síntoma" } };
    active.mockResolvedValue({ ...draft, intake_id: "new-draft", current_question: description, questions: [description, question] });
    act(() => window.dispatchEvent(new Event("symptom-intake-updated")));
    expect(await screen.findByText("Describe the new symptom", { selector: "p" })).toBeInTheDocument();
});

it("preserves an uncertain mutation identity across a token refresh", async () => {
    mutate.mockRejectedValueOnce(new Error("synthetic response lost"));
    render(panel());
    fireEvent.click(await screen.findByText("I don’t know"));
    await screen.findByText(/We could not verify/);
    const original = mutate.mock.calls[0][3];
    act(() => store.dispatch(hydrateSession({ accessToken: "refreshed-token", refreshToken: "synthetic", expiresAt: 9999999999,
        user: { id: "patient-A", email: "patient-A@synthetic.invalid", role: "patient" } })));
    await waitFor(() => expect(active).toHaveBeenCalledTimes(2));
    mutate.mockResolvedValue({ ...draft, revision: 1 });
    fireEvent.click(screen.getByText("Retry the same action"));
    await waitFor(() => expect(mutate).toHaveBeenCalledTimes(2));
    expect(mutate.mock.calls[1][3]).toEqual(original);
});

it("blocks a spoken confirm reply and hides internal identifiers in the preview", async () => {
    const register = vi.fn();
    active.mockResolvedValue({ ...draft, status: "ready_for_confirmation", current_question: null, can_review: true, can_confirm: true,
        preview_hash: "a".repeat(64), preview: { schema_version: "symptom-report/1", answers: {}, summary: "My original account",
            context: { purpose: "patient_symptom_preview", version: "symptom-context/1", medications: [{ name: "Test medicine", source_id: "private-source-uuid" }],
                facts: [
                    { fact_type: "dose", value: { amount: "5 mg" }, source_id: "private-fact-uuid" },
                    { fact_type: "lab_result", value: { value: "5.8", unit: "mmol/L", reference_range: "3.5–5.1" }, source_id: "private-result-uuid" },
                ], excerpts: [] },
            source_message_id: "private-source-turn", session_id: "default" } });
    render(<Provider store={store}><SymptomIntakePanel locale="en-US" registerReply={register} /></Provider>);
    await screen.findByText("My original account");
    act(() => { expect(register.mock.calls.at(-1)?.[0]("confirm", "voice")).toBe("blocked"); });
    expect(mutate).not.toHaveBeenCalled();
    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(screen.getByText("Confirm and share with my care team")).toBeDisabled();
    expect(screen.queryByText(/private-source-uuid|private-fact-uuid|private-source-turn/)).not.toBeInTheDocument();
    // Record details name the kind of fact in words and show values without internal keys.
    expect(screen.getByText(/Dose: 5 mg/)).toBeInTheDocument();
    expect(screen.queryByText(/amount:/)).not.toBeInTheDocument();
    expect(screen.getByText(/Test result: Result: 5.8 · Unit: mmol\/L · Report range: 3.5–5.1/)).toBeInTheDocument();
    expect(screen.queryByText(/reference_range|private-result-uuid/)).not.toBeInTheDocument();
    // A medication with no dose or frequency has no dangling separators.
    expect(screen.getByText("Test medicine")).toBeInTheDocument();
});

it("shows no start control or placeholder on an ordinary chat with no draft", async () => {
    active.mockResolvedValue(null);
    const { container } = render(panel());
    await waitFor(() => expect(active).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText("Start a symptom draft")).not.toBeInTheDocument();
});

it.each([
    ["en-US", "yes", "yes"], ["en-US", "Yes, let’s do it!", "yes"], ["es-MX", "Sí", "yes"], ["es-MX", "sí, hagámoslo", "yes"],
    ["en-US", "Not now", "no"], ["es-MX", "Ahora no", "no"],
] as const)("answers the note offer by typed or spoken %s reply %s", async (locale, text, answer) => {
    active.mockResolvedValue(null); start.mockResolvedValue({ ...draft, locale });
    const register = vi.fn(); const answered = vi.fn();
    render(<Provider store={store}><SymptomIntakePanel locale={locale} offerSourceId="source-turn" registerReply={register} onOfferAnswered={answered} /></Provider>);
    await waitFor(() => expect(active).toHaveBeenCalled());
    await act(async () => { await Promise.resolve(); });
    const handler = register.mock.calls.filter(([fn]) => fn).at(-1)![0];
    let result = "";
    await act(async () => { result = handler(text, "voice", locale); });
    expect(result).toBe("handled");
    if (answer === "yes") { await waitFor(() => expect(start).toHaveBeenCalledWith("patient-A", "source-turn", "default", expect.anything())); }
    else expect(start).not.toHaveBeenCalled();
    await waitFor(() => expect(answered).toHaveBeenCalledWith("source-turn"));
});

it("leaves ordinary messages alone while an offer is pending", async () => {
    active.mockResolvedValue(null);
    const register = vi.fn();
    render(<Provider store={store}><SymptomIntakePanel locale="en-US" offerSourceId="source-turn" registerReply={register} /></Provider>);
    await waitFor(() => expect(active).toHaveBeenCalled());
    await act(async () => { await Promise.resolve(); });
    const handler = register.mock.calls.filter(([fn]) => fn).at(-1)![0];
    expect(handler("When is my appointment?", "typed")).toBe("unhandled");
    expect(handler("yes I also have a cough since Monday", "typed")).toBe("unhandled");
    expect(start).not.toHaveBeenCalled();
});

it("keeps the conversation questions inside chat bubbles with a private tag", async () => {
    render(<Provider store={store}><SymptomIntakePanel locale="en-US" registerReply={vi.fn()} /></Provider>);
    expect((await screen.findAllByText("Choose your severity")).length).toBeGreaterThan(0);
    expect(screen.getByText("Private until you confirm")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Draft — not submitted" }).className).not.toMatch(/bg-surface-2|border/);
});
