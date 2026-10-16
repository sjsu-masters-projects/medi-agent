import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Provider } from "react-redux";
import { beforeEach, expect, it, vi } from "vitest";
import { SymptomIntakePanel } from "@/components/features/symptom-intake-panel";
import { store } from "@/store/store";
import { hydrateSession, logout } from "@/store/slices/auth-slice";
import type { SymptomIntake } from "@/types";
import { ApiClientError } from "@/services/api";

const { active, read, start, mutate } = vi.hoisted(() => ({ active: vi.fn(), read: vi.fn(), start: vi.fn(), mutate: vi.fn() }));
vi.mock("@/services/symptom-intakes", () => ({ fetchActiveIntake: active, fetchIntake: read, startIntake: start, mutateIntake: mutate }));
const question = { id: "severity", answer_type: "rating" as const, wording: { "en-US": "Choose your severity", "es-MX": "Elige tu intensidad" } };
const draft: SymptomIntake = { intake_id: "synthetic-intake", status: "collecting", revision: 0, locale: "en-US", timezone: "America/Los_Angeles", timezone_fallback: false,
    answers: {}, current_question: question, questions: [question], library_available: true, can_review: false, can_confirm: false };
function login(id = "patient-A") { store.dispatch(hydrateSession({ accessToken: id, refreshToken: "synthetic", expiresAt: 9999999999, user: { id, email: `${id}@synthetic.invalid`, role: "patient" } })); }
function panel(locale: "en-US" | "es-MX" = "en-US", sessionId = "default") { return <Provider store={store}><SymptomIntakePanel locale={locale} sessionId={sessionId} sourceMessageId="source-turn" /></Provider>; }
beforeEach(() => { vi.resetAllMocks(); login(); active.mockResolvedValue(structuredClone(draft)); });

it("recovers the owned draft without writing or mirroring answers into chat", async () => {
    render(panel());
    expect(await screen.findByText("Draft — not submitted")).toBeInTheDocument();
    expect(screen.getByText(/America\/Los_Angeles/)).toBeInTheDocument();
    expect(mutate).not.toHaveBeenCalled();
    act(() => window.dispatchEvent(new Event("symptom-intake-updated")));
    await waitFor(() => expect(active).toHaveBeenCalledTimes(2));
});

it.each(["en-US", "es-MX"] as const)("saves unknown as null and never selects a rating in %s", async (locale) => {
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

it("reuses the exact confirmation identity after an uncertain save", async () => {
    const ready = { ...draft, status: "ready_for_confirmation", current_question: null, can_review: true, can_confirm: true, preview_hash: "a".repeat(64),
        preview: { schema_version: "symptom-report/1", answers: {}, summary: "Original patient testimony", context: { purpose: "patient_symptom_preview", version: "symptom-context/1", medications: [], facts: [], excerpts: [] }, source_message_id: "source-turn", session_id: "default" } };
    active.mockResolvedValue(ready); read.mockResolvedValue(ready);
    mutate.mockRejectedValueOnce(new Error("synthetic lost response")).mockResolvedValue({ ...ready, status: "confirmed", confirmed_report_id: "one-report" });
    render(panel()); await screen.findByRole("checkbox"); fireEvent.click(screen.getByRole("checkbox")); fireEvent.click(screen.getByText("Confirm and share with my care team"));
    await screen.findByText(/We could not verify/);
    const original = mutate.mock.calls[0][3];
    fireEvent.click(screen.getByText("Reload saved state")); await waitFor(() => expect(read).toHaveBeenCalled());
    fireEvent.click(screen.getByText("Retry the same action"));
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
    fireEvent.click(await screen.findByText("Start a symptom draft"));
    await waitFor(() => expect(start).toHaveBeenCalled());
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
    await screen.findByText("Report saved for care-team review: one-report");
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
    expect(screen.queryByText("Start a symptom draft")).not.toBeInTheDocument();
    let resolve: (result: SymptomIntake | null) => void = () => {};
    active.mockImplementationOnce(() => new Promise<SymptomIntake | null>((done) => { resolve = done; }));
    fireEvent.click(screen.getByRole("button", { name: "Reload saved state" }));
    expect(screen.getByText("Loading your draft…")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    await act(async () => resolve(null));
    expect(await screen.findByText("Start a symptom draft")).toBeEnabled();
    expect(start).not.toHaveBeenCalled();
});

it.each(["en-US", "es-MX"] as const)("preserves unavailable-library feedback on recovery in %s", async (locale) => {
    active.mockRejectedValue(new ApiClientError("Unavailable", 422, { error: { code: "INTAKE_LIBRARY_UNAVAILABLE" } }));
    render(panel(locale));
    expect(await screen.findByText(locale === "en-US" ? /Guided intake is unavailable/ : /La captura guiada no está disponible/)).toBeInTheDocument();
    expect(screen.queryByText(locale === "en-US" ? "Start a symptom draft" : "Iniciar un borrador de síntomas")).not.toBeInTheDocument();
});
