import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CareConversations } from "@/components/features/care-conversations";
import { careConversations } from "@/services/care-conversations";
import type { CareConversation, CareConversationMessage } from "@/types/care-conversations";

const auth = vi.hoisted(() => ({ accessToken: "synthetic-token", user: { id: "patient" } }));
vi.mock("react-redux", () => ({ useSelector: (select: (state: unknown) => unknown) => select({ auth }) }));
vi.mock("@/services/care-conversations", () => ({
  careConversations: { recipients: vi.fn(), list: vi.fn(), open: vi.fn(), messages: vi.fn(), send: vi.fn(), read: vi.fn(), translate: vi.fn(), preview: vi.fn() },
}));
const thread: CareConversation = {
  id: "thread-one", patient_id: "patient", clinician_id: "clinician-one",
  patient_name: "Synthetic Patient", clinician_name: "Dr. One", clinic_name: "Clinic One",
  last_message_at: null, last_message_preview: null, unread_count: 2, writable: true,
};
const message = (id: string, body = id, created_at = "2026-10-09T10:00:00Z"): CareConversationMessage => ({
  id, body, created_at, conversation_id: thread.id, sender_id: "clinician-one", sender_role: "clinician", sender_name: "Dr. One",
});
async function select() {
  fireEvent.click(await screen.findByRole("button", { name: /Dr. One · Clinic One/ }));
  await screen.findByText("Newest reply");
}
beforeEach(() => {
  vi.resetAllMocks();
  auth.accessToken = "synthetic-token"; auth.user = { id: "patient" };
  vi.mocked(careConversations.recipients).mockResolvedValue([
    { id: "clinician-one", name: "Dr. One", clinic_name: "Clinic One", role: "clinician" },
    { id: "clinician-two", name: "Dr. Two", clinic_name: "Clinic Two", role: "clinician" },
  ]);
  vi.mocked(careConversations.list).mockResolvedValue([thread]);
  vi.mocked(careConversations.open).mockResolvedValue(thread);
  vi.mocked(careConversations.messages).mockResolvedValue({ items: [message("newest", "Newest reply")], next_cursor: null });
  vi.mocked(careConversations.read).mockResolvedValue({ read_at: "2026-10-09T10:00:00Z" });
  vi.mocked(careConversations.send).mockResolvedValue(message("sent", "My question", "2026-10-09T11:00:00Z"));
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("non-blocking message translation", () => {
  const pendingMessage = (id: string, body = "Tomo 5 mg al dia") => ({ ...message(id, body), sender_role: "patient", translation_pending: true });
  const result = (id: string, overrides = {}) => ({
    message_id: id, translation: "I take 5 mg daily", translation_locale: "en-US", translation_guard_passed: true, translation_pending: false, ...overrides,
  });
  async function open() {
    render(<CareConversations audience="clinician" />);
    fireEvent.click(await screen.findByRole("button", { name: /Synthetic Patient · Clinic One/ }));
  }
  it("shows the original with a subtle Translating note, then swaps in the translation", async () => {
    let finish!: (value: ReturnType<typeof result>) => void;
    vi.mocked(careConversations.messages).mockResolvedValue({ items: [pendingMessage("m1")], next_cursor: null });
    vi.mocked(careConversations.translate).mockReturnValue(new Promise((done) => { finish = done; }));
    await open();
    expect(await screen.findByText("Tomo 5 mg al dia")).toBeInTheDocument();
    expect(screen.getByText("Translating…")).toBeInTheDocument();
    await waitFor(() => expect(careConversations.translate).toHaveBeenCalledWith("synthetic-token", "thread-one", "m1"));
    await act(async () => finish(result("m1")));
    await screen.findByText("I take 5 mg daily");
    expect(screen.queryByText("Translating…")).not.toBeInTheDocument();
  });
  it("keeps the original when the safety check fails or the request errors", async () => {
    vi.mocked(careConversations.messages).mockResolvedValue({ items: [pendingMessage("m1"), pendingMessage("m2", "Tomo 5 mg al dia two")], next_cursor: null });
    vi.mocked(careConversations.translate).mockImplementation(async (_t, _c, id) => {
      if (id === "m2") throw new Error("provider down");
      return result(id, { translation_guard_passed: false });
    });
    await open();
    await screen.findByText("Automatic translation unavailable for this message");
    expect(screen.getByText("Tomo 5 mg al dia")).toBeInTheDocument();
    expect(screen.queryByText("I take 5 mg daily")).not.toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Translating…")).not.toBeInTheDocument());
    expect(screen.getByText("Tomo 5 mg al dia two")).toBeInTheDocument();
  });
  it("asks for at most three translations at a time and does not block the reader", async () => {
    const gates: Array<() => void> = [];
    vi.mocked(careConversations.messages).mockResolvedValue({
      items: ["m1", "m2", "m3", "m4", "m5"].map((id, index) => ({ ...pendingMessage(id, `Tomo 5 mg al dia ${index}`), created_at: `2026-10-09T10:0${index}:00Z` })),
      next_cursor: null,
    });
    vi.mocked(careConversations.translate).mockImplementation((_t, _c, id) => new Promise((done) => { gates.push(() => done(result(id))); }));
    await open();
    await waitFor(() => expect(careConversations.translate).toHaveBeenCalledTimes(3));
    expect(screen.getByRole("textbox")).toBeEnabled();
    await act(async () => gates.shift()!());
    await waitFor(() => expect(careConversations.translate).toHaveBeenCalledTimes(4));
  });
  it("makes no translation request when nothing is pending", async () => {
    vi.mocked(careConversations.messages).mockResolvedValue({ items: [message("m1", "Hello, how are you today?")], next_cursor: null });
    await open();
    await screen.findByText("Hello, how are you today?");
    expect(careConversations.translate).not.toHaveBeenCalled();
  });
});

describe("human conversations", () => {
  it("retains exact confirmed translation for an uncertain clinician retry after switching threads", async () => {
    const other = { ...thread, id: "thread-two", patient_name: "Second Patient" };
    vi.mocked(careConversations.list).mockResolvedValue([thread, other]);
    vi.mocked(careConversations.preview).mockResolvedValue({
      needed: true, target_locale: "es-MX", translation: "Toma 500 mg", back_translation: "Take 500 mg",
      guard_passed: true, guard_failure_code: null, model_id: "test-model",
    });
    vi.mocked(careConversations.send).mockRejectedValueOnce(new Error("uncertain"));
    render(<CareConversations audience="clinician" />);
    fireEvent.click(await screen.findByRole("button", { name: /Synthetic Patient · Clinic One/ }));
    await screen.findByText("Newest reply");
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Take 500 mg" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    fireEvent.click(await screen.findByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByText(/Send could not be confirmed/);
    const first = vi.mocked(careConversations.send).mock.calls[0];
    expect(first.at(-1)).toEqual({ text: "Toma 500 mg", locale: "es-MX", model_id: "test-model" });
    fireEvent.click(screen.getByRole("button", { name: /Second Patient · Clinic One/ }));
    await screen.findByText("Newest reply");
    fireEvent.click(screen.getByRole("button", { name: /Synthetic Patient · Clinic One/ }));
    const retry = await screen.findByRole("button", { name: "Retry" });
    await waitFor(() => expect(retry).toBeEnabled());
    fireEvent.click(retry);
    await waitFor(() => expect(careConversations.send).toHaveBeenCalledTimes(2));
    expect(vi.mocked(careConversations.send).mock.calls[1]).toEqual(first);
  });
  it("shows a passed English translation of a Spanish patient message, wrapping long words", async () => {
    vi.mocked(careConversations.messages).mockResolvedValue({
      items: [{ ...message("newest", "Tomo 5 mg al dia"), sender_role: "patient", translation: "I take 5 mg daily", translation_locale: "en-US", translation_guard_passed: true }],
      next_cursor: null,
    });
    render(<CareConversations audience="clinician" />);
    fireEvent.click(await screen.findByRole("button", { name: /Synthetic Patient · Clinic One/ }));
    expect(await screen.findByText("I take 5 mg daily")).toHaveClass("break-words");
    expect(screen.getByText("Translated from Spanish")).toBeInTheDocument();
  });
  it("never shows a translation into Spanish to the clinician", async () => {
    vi.mocked(careConversations.messages).mockResolvedValue({
      items: [{ ...message("newest", "Hello there"), sender_role: "patient", translation: "Hola", translation_locale: "es-MX", translation_guard_passed: true }],
      next_cursor: null,
    });
    render(<CareConversations audience="clinician" />);
    fireEvent.click(await screen.findByRole("button", { name: /Synthetic Patient · Clinic One/ }));
    await screen.findByText("Hello there");
    expect(screen.queryByText("Hola")).not.toBeInTheDocument();
  });
  it("hides a patient-message translation whose safety check failed and says why", async () => {
    vi.mocked(careConversations.messages).mockResolvedValue({
      items: [{ ...message("newest", "Tomo 5 mg al dia"), sender_role: "patient", translation: "I take 50 mg daily", translation_locale: "en-US", translation_guard_passed: false }],
      next_cursor: null,
    });
    render(<CareConversations audience="clinician" />);
    fireEvent.click(await screen.findByRole("button", { name: /Synthetic Patient · Clinic One/ }));
    await screen.findByText("Tomo 5 mg al dia");
    expect(screen.queryByText("I take 50 mg daily")).not.toBeInTheDocument();
    expect(screen.getByText("Automatic translation unavailable for this message")).toBeInTheDocument();
  });
  it("selects only the exact linked conversation and reports unavailable targets", async () => {
    vi.mocked(careConversations.list).mockResolvedValue([thread, { ...thread, id: "second", clinician_name: "Dr. Two" }]);
    const view = render(<CareConversations conversationId="second" />);
    await waitFor(() => expect(careConversations.messages).toHaveBeenCalledWith("synthetic-token", "second", undefined));
    expect(screen.getByRole("button", { name: /Dr. Two · Clinic One/ })).toHaveAttribute("aria-pressed", "true");
    expect(careConversations.messages).not.toHaveBeenCalledWith("synthetic-token", thread.id, undefined);
    view.rerender(<CareConversations conversationId="missing" />);
    await screen.findByText(/The linked conversation is unavailable/);
    expect(careConversations.messages).not.toHaveBeenCalledWith("synthetic-token", "missing", undefined);
  });
  it("requires one explicit recipient and opens only that clinician's thread", async () => {
    render(<CareConversations />);
    await screen.findByRole("option", { name: /Dr. Two/ });
    expect(screen.getByRole("button", { name: "Open conversation" })).toBeDisabled();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "clinician-two" } });
    fireEvent.click(screen.getByRole("button", { name: "Open conversation" }));
    await waitFor(() => expect(careConversations.open).toHaveBeenCalledWith("synthetic-token", "clinician-two"));
    expect(careConversations.open).toHaveBeenCalledTimes(1);
  });

  it("renders actual sender, clinic and plain text; marks only the displayed last ID", async () => {
    vi.mocked(careConversations.messages).mockResolvedValue({ items: [message("one", "<img src=x onerror=alert(1)>"), message("two", "Newest reply")], next_cursor: "one" });
    render(<CareConversations />);
    expect(await screen.findByText("2 unread")).toBeInTheDocument();
    await select();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
    // Each message names its sender; the clinic appears once, in the thread header.
    expect(screen.getAllByText(/^Dr. One · Clinician ·/).length).toBeGreaterThan(1);
    expect(screen.queryAllByText(/Clinician · Clinic One/, { selector: "p" })).toHaveLength(0);
    expect(screen.getByRole("heading", { name: /Clinic One/ })).toBeInTheDocument();
    await waitFor(() => expect(careConversations.read).toHaveBeenCalledWith("synthetic-token", thread.id, "two"));
    expect(careConversations.read).not.toHaveBeenCalledWith("synthetic-token", thread.id, "unseen");
  });

  it("keeps body and UUID for an uncertain retry, without automatic resend", async () => {
    vi.mocked(careConversations.send).mockRejectedValueOnce(new TypeError("transport failed"));
    render(<CareConversations />);
    await select();
    fireEvent.change(screen.getByRole("textbox", { name: "Message" }), { target: { value: "  My question  " } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByText(/Send could not be confirmed/);
    expect(careConversations.send).toHaveBeenCalledTimes(1);
    const first = vi.mocked(careConversations.send).mock.calls[0]!;
    expect(first.slice(0, 3)).toEqual(["synthetic-token", thread.id, "My question"]);
    expect(first[3]).toMatch(/^[0-9a-f-]{36}$/);
    expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("  My question  ");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(careConversations.send).toHaveBeenCalledTimes(2));
    expect(vi.mocked(careConversations.send).mock.calls[1]).toEqual(first);
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue(""));
  });

  it("retains an uncertain draft and key across thread switches", async () => {
    vi.mocked(careConversations.list).mockResolvedValue([thread, { ...thread, id: "other", clinician_name: "Dr. Two" }]);
    vi.mocked(careConversations.send).mockRejectedValueOnce(new TypeError());
    render(<CareConversations />);
    await select();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Question" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByText(/Send could not be confirmed/);
    const first = vi.mocked(careConversations.send).mock.calls[0];
    fireEvent.click(screen.getByRole("button", { name: /Dr. Two · Clinic One/ }));
    await screen.findByRole("textbox");
    fireEvent.click(screen.getByRole("button", { name: /Dr. One · Clinic One/ }));
    await screen.findByRole("button", { name: "Retry" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Retry" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(careConversations.send).toHaveBeenCalledTimes(2));
    expect(vi.mocked(careConversations.send).mock.calls[1]).toEqual(first);
  });

  it("loads older pages with the returned cursor and deduplicates boundary messages", async () => {
    vi.mocked(careConversations.messages)
      .mockResolvedValueOnce({ items: [message("newest", "Newest reply")], next_cursor: "newest" })
      .mockResolvedValueOnce({ items: [message("older", "Earlier reply", "2026-10-08T10:00:00Z"), message("newest", "Newest reply")], next_cursor: null });
    render(<CareConversations />);
    await select();
    fireEvent.click(screen.getByRole("button", { name: "Load older messages" }));
    await screen.findByText("Earlier reply");
    expect(careConversations.messages).toHaveBeenLastCalledWith("synthetic-token", thread.id, "newest");
    expect(screen.getAllByText("Newest reply")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "Load older messages" })).not.toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Conversations" }).firstChild).toHaveTextContent("Earlier reply");
    expect(careConversations.read).toHaveBeenCalledWith("synthetic-token", thread.id, "newest");
  });

  it("clears messages and composer on revocation without showing backend details", async () => {
    vi.mocked(careConversations.send).mockRejectedValue({ status: 403, message: "private UUID details" });
    render(<CareConversations />);
    await select();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Question" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByText("This conversation is unavailable. Refresh conversations.");
    expect(screen.queryByText("Newest reply")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByText(/private UUID/)).not.toBeInTheDocument();
  });

  it("clears account state and ignores late responses from the previous account", async () => {
    let finish!: (value: { items: CareConversationMessage[]; next_cursor: null }) => void;
    vi.mocked(careConversations.messages).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const view = render(<CareConversations />);
    fireEvent.click(await screen.findByRole("button", { name: /Dr. One · Clinic One/ }));
    auth.user = { id: "other-account" }; auth.accessToken = "other-token";
    vi.mocked(careConversations.list).mockResolvedValue([]);
    view.rerender(<CareConversations />);
    await act(async () => { finish({ items: [message("late", "Private previous account")], next_cursor: null }); });
    expect(screen.queryByText("Private previous account")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("localizes the recipient, composer, safety notice and uncertain send in Mexican Spanish", async () => {
    vi.mocked(careConversations.send).mockRejectedValue(new TypeError());
    render(<CareConversations locale="es-MX" />);
    await select();
    expect(screen.getByRole("combobox", { name: "Elegir destinatario" })).toBeInTheDocument();
    expect(screen.getByText(/no se supervisan continuamente/)).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Mensaje" }), { target: { value: "Pregunta" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar mensaje" }));
    await screen.findByText(/No se pudo confirmar el envío/);
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeEnabled();
  });

  it("refreshes a visible selected thread and stops polling while hidden or unmounted", async () => {
    vi.useFakeTimers();
    let view!: ReturnType<typeof render>;
    await act(async () => { view = render(<CareConversations />); });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: /Dr. One · Clinic One/ })); });
    vi.mocked(careConversations.messages).mockResolvedValue({ items: [message("newest", "Newest reply"), message("arrived", "New arrival", "2026-10-09T11:00:00Z")], next_cursor: null });
    await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
    expect(screen.getByText("New arrival")).toBeInTheDocument();
    expect(careConversations.read).toHaveBeenLastCalledWith("synthetic-token", thread.id, "arrived");
    const count = vi.mocked(careConversations.messages).mock.calls.length;
    const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    expect(careConversations.messages).toHaveBeenCalledTimes(count);
    view.unmount();
    visibility.mockRestore();
    await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
    expect(careConversations.messages).toHaveBeenCalledTimes(count);
  });

  it("distinguishes saved sends from refresh failure and never offers to resend the saved message", async () => {
    render(<CareConversations />);
    await select();
    vi.mocked(careConversations.messages).mockRejectedValue(new TypeError());
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "My question" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByText(/Message saved. Could not refresh/);
    expect(screen.getByRole("textbox")).toHaveValue("");
    expect(careConversations.send).toHaveBeenCalledTimes(1);
  });

  it("pauses reads and polling while the conversation view is hidden and retains the pending UUID", async () => {
    vi.mocked(careConversations.send).mockRejectedValueOnce(new TypeError());
    const view = render(<CareConversations />);
    await select();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Question" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByText(/Send could not be confirmed/);
    const first = vi.mocked(careConversations.send).mock.calls[0];
    view.rerender(<CareConversations visible={false} />);
    const reads = vi.mocked(careConversations.read).mock.calls.length;
    const loads = vi.mocked(careConversations.messages).mock.calls.length;
    await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
    expect(careConversations.messages).toHaveBeenCalledTimes(loads);
    expect(careConversations.read).toHaveBeenCalledTimes(reads);
    view.rerender(<CareConversations visible />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Retry" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(careConversations.send).toHaveBeenCalledTimes(2));
    expect(vi.mocked(careConversations.send).mock.calls[1]).toEqual(first);
  });

  it("presents assigned patients in the clinician inbox and does not permit blank messages", async () => {
    render(<CareConversations audience="clinician" />);
    fireEvent.click(await screen.findByRole("button", { name: /Synthetic Patient · Clinic One/ }));
    await screen.findByText("Newest reply");
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "   " } });
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
    expect(screen.getByRole("textbox")).toHaveAttribute("maxlength", "4000");
  });

  it("polls the visible inbox without resetting selection, draft or loading the whole screen", async () => {
    vi.useFakeTimers();
    let view!: ReturnType<typeof render>;
    await act(async () => { view = render(<CareConversations />); });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: /Dr. One · Clinic One/ })); });
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Unsent draft" } });
    vi.mocked(careConversations.list).mockResolvedValue([thread, { ...thread, id: "second", clinician_name: "Dr. Two", last_message_preview: "Inactive thread arrival", unread_count: 3 }]);
    await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
    expect(screen.getByText("Inactive thread arrival")).toBeInTheDocument();
    expect(screen.getByText("3 unread")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Dr. One · Clinic One/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("textbox")).toHaveValue("Unsent draft");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    const calls = vi.mocked(careConversations.list).mock.calls.length;
    view.rerender(<CareConversations visible={false} />);
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    expect(careConversations.list).toHaveBeenCalledTimes(calls);
    view.rerender(<CareConversations visible />);
    await act(async () => { await Promise.resolve(); });
    const visibleCalls = vi.mocked(careConversations.list).mock.calls.length;
    const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
    expect(careConversations.list).toHaveBeenCalledTimes(visibleCalls);
    visibility.mockRestore();
  });

  it("refreshes server unread counts after read marking and preserves concurrent unseen arrivals", async () => {
    let finishRead!: (value: { read_at: string }) => void;
    vi.mocked(careConversations.read).mockReturnValue(new Promise((resolve) => { finishRead = resolve; }));
    render(<CareConversations />);
    await select();
    vi.mocked(careConversations.list).mockResolvedValue([{ ...thread, unread_count: 1, last_message_preview: "Concurrent unseen arrival" }]);
    await act(async () => { finishRead({ read_at: "2026-10-09T11:00:00Z" }); });
    expect(await screen.findByText("1 unread")).toBeInTheDocument();
    expect(screen.getByText("Concurrent unseen arrival")).toBeInTheDocument();
    expect(careConversations.read).toHaveBeenCalledWith("synthetic-token", thread.id, "newest");
    expect(careConversations.read).not.toHaveBeenCalledWith("synthetic-token", thread.id, "unseen-arrival");
    expect(screen.queryByText("0 unread")).not.toBeInTheDocument();
  });

  it("ignores an older inbox poll that resolves after a deferred read completes", async () => {
    let finishPoll!: (value: CareConversation[]) => void;
    let finishRead!: (value: { read_at: string }) => void;
    vi.mocked(careConversations.read).mockReturnValue(new Promise((resolve) => { finishRead = resolve; }));
    const view = render(<CareConversations />);
    await select();
    vi.mocked(careConversations.list).mockReturnValueOnce(new Promise((resolve) => { finishPoll = resolve; }));
    await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
    vi.mocked(careConversations.list).mockResolvedValue([{ ...thread, unread_count: 1 }]);
    await act(async () => { finishRead({ read_at: "2026-10-09T11:00:00Z" }); });
    expect(screen.getByText("1 unread")).toBeInTheDocument();
    await act(async () => { finishPoll([{ ...thread, unread_count: 9 }]); });
    expect(screen.queryByText("9 unread")).not.toBeInTheDocument();
    view.unmount();
  });

  it("aborts a deferred inbox poll on send and rejects its late preview/unread update", async () => {
    let finishPoll!: (value: CareConversation[]) => void;
    render(<CareConversations />);
    await select();
    vi.mocked(careConversations.list).mockReturnValueOnce(new Promise((resolve) => { finishPoll = resolve; }));
    await act(async () => { document.dispatchEvent(new Event("visibilitychange")); });
    const oldSignal = vi.mocked(careConversations.list).mock.calls.at(-1)![1]!;
    vi.mocked(careConversations.list).mockResolvedValue([{ ...thread, unread_count: 1, last_message_preview: "My question" }]);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "My question" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() => expect(screen.getByRole("textbox")).toHaveValue(""));
    expect(oldSignal.aborted).toBe(true);
    await screen.findByText("1 unread");
    await act(async () => { finishPoll([{ ...thread, unread_count: 9, last_message_preview: "Stale preview" }]); });
    expect(screen.queryByText("Stale preview")).not.toBeInTheDocument();
    expect(screen.queryByText("9 unread")).not.toBeInTheDocument();
    expect(screen.getByText("My question")).toBeInTheDocument();
  });

  it("polls current recipients, clears a revoked choice and offers new assignments without losing the selected draft", async () => {
    vi.useFakeTimers();
    await act(async () => { render(<CareConversations />); });
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: /Dr. One · Clinic One/ })); });
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Draft" } });
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "clinician-two" } });
    vi.mocked(careConversations.recipients).mockResolvedValue([
      { id: "clinician-one", name: "Dr. One", clinic_name: "Clinic One", role: "clinician" },
      { id: "clinician-three", name: "Dr. Three", clinic_name: "Clinic Three", role: "clinician" },
    ]);
    await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
    expect(screen.getByRole("combobox")).toHaveValue("");
    expect(screen.queryByRole("option", { name: /Dr. Two/ })).not.toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Dr. Three/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open conversation" })).toBeDisabled();
    expect(screen.getByRole("textbox")).toHaveValue("Draft");
    expect(screen.getByRole("button", { name: /Dr. One · Clinic One/ })).toHaveAttribute("aria-pressed", "true");
  });

  it.each(["en-US", "es-MX"])("requires explicit confirmation before preparing a new key after a definitive mismatch (%s)", async (locale) => {
    const spanish = locale === "es-MX";
    vi.mocked(careConversations.send).mockRejectedValueOnce({
      status: 422, details: { error: { code: "MESSAGE_IDEMPOTENCY_MISMATCH" } },
    });
    render(<CareConversations locale={locale} />);
    await select();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "My question" } });
    fireEvent.click(screen.getByRole("button", { name: spanish ? "Enviar mensaje" : "Send message" }));
    await screen.findByText(spanish ? /El reintento fue rechazado/ : /The retry was rejected/);
    const first = vi.mocked(careConversations.send).mock.calls[0]!;
    expect(screen.getByRole("textbox")).toHaveValue("My question");
    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(screen.getByRole("button", { name: spanish ? "Reintentar" : "Retry" })).toBeDisabled();
    const prepare = spanish ? "Preparar un nuevo envío" : "Prepare a new send";
    fireEvent.click(screen.getByRole("button", { name: prepare }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent(spanish ? /El mensaje anterior puede ya existir/ : /The previous message may already exist/);
    fireEvent.click(screen.getByRole("button", { name: spanish ? "Cancelar" : "Cancel" }));
    expect(screen.getByRole("textbox")).toBeDisabled();
    expect(careConversations.send).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: prepare }));
    fireEvent.click(screen.getByRole("button", { name: spanish ? "Confirmar: preparar un nuevo envío" : "Confirm: prepare a new send" }));
    expect(screen.getByRole("textbox")).toBeEnabled();
    expect(careConversations.send).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: spanish ? "Enviar mensaje" : "Send message" }));
    await waitFor(() => expect(careConversations.send).toHaveBeenCalledTimes(2));
    const second = vi.mocked(careConversations.send).mock.calls[1]!;
    expect(second.slice(0, 3)).toEqual(first.slice(0, 3));
    expect(second[3]).not.toBe(first[3]);
  });

  it("preserves text and permits editing after a definitive invalid request without silently resending", async () => {
    vi.mocked(careConversations.send).mockRejectedValueOnce({
      status: 422, details: { error: { code: "VALIDATION_ERROR" } },
    });
    render(<CareConversations />);
    await select();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Question" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await screen.findByText(/The message was rejected. Your text is preserved/);
    expect(screen.getByRole("textbox")).toHaveValue("Question");
    expect(screen.getByRole("textbox")).toBeEnabled();
    expect(careConversations.send).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Edited question" } });
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    await waitFor(() => expect(careConversations.send).toHaveBeenCalledTimes(2));
    expect(vi.mocked(careConversations.send).mock.calls[1]![2]).toBe("Edited question");
  });
});
