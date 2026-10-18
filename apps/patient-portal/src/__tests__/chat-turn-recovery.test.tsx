import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useChatTurnRecovery } from "@/hooks/use-chat-turn-recovery";
import { ChatTurnRecovery } from "@/components/features/chat-turn-recovery";
import type { ChatTurnApi } from "@/services/chat-api";
import { ChatRole } from "@/types";
import { chatSlice, addMessage } from "@/store/slices/chat-slice";
import { getChatRecoveryCopy } from "@/content/chat-copy";

const row: ChatTurnApi = { client_message_id: "test-key", status: "interrupted", retryable: true,
    attempt: 1, document_id: "doc-1", user_message: { id: "user-1", patient_id: "patient-1",
        content: "Synthetic question", role: ChatRole.USER, language: "es-MX", created_at: "2026-10-17T10:00:00Z" } };
function setup(scope = "patient-1:chat-1") {
    const send = vi.fn();
    const socket = { current: { readyState: WebSocket.OPEN, send } as unknown as WebSocket };
    const hook = renderHook(({ scope }) => useChatTurnRecovery(scope, socket), { initialProps: { scope } });
    return { ...hook, send, socket };
}

describe("saved Nora turn recovery", () => {
    it("blocks rapid double sends and retries the exact identity and document", () => {
        const { result, send } = setup();
        act(() => {
            expect(result.current.send("Synthetic question", "en-US", "doc-1")).toBe(true);
            expect(result.current.send("Duplicate", "en-US", null)).toBe(false);
        });
        const first = JSON.parse(send.mock.calls[0][0]);
        act(() => { result.current.retry(first.client_message_id); });
        expect(JSON.parse(send.mock.calls[1][0])).toEqual(first);
    });

    it("keeps an unacknowledged send while a recovery snapshot is empty", () => {
        const { result } = setup();
        act(() => { result.current.send("Synthetic", "en-US", null); });
        act(() => { result.current.accept([], true); });
        expect(result.current.turnBusy).toBe(true);
        expect(result.current.turns[0].status).toBe("unknown");
    });

    it("recovers a saved Spanish request after reload and clears it on completed replay", () => {
        const { result, send } = setup();
        act(() => { result.current.accept([row], true); });
        act(() => { result.current.retry(row.client_message_id); });
        expect(JSON.parse(send.mock.calls[0][0])).toMatchObject({ client_message_id: row.client_message_id,
            content: row.user_message!.content, language: "es-MX", document_id: "doc-1" });
        act(() => { result.current.accept([{ ...row, status: "completed" }], true); });
        expect(result.current.turns).toEqual([]);
        expect(result.current.turnBusy).toBe(false);
    });

    it("never retries uncertain actions and dismisses only through the server", () => {
        const { result, send } = setup();
        act(() => { result.current.accept([{ ...row, retryable: false, failure_code: "action_uncertain" }]); });
        act(() => { expect(result.current.retry(row.client_message_id)).toBe(false); result.current.dismiss(row.client_message_id); });
        expect(send).toHaveBeenCalledExactlyOnceWith(JSON.stringify({ type: "dismiss_turn", client_message_id: row.client_message_id }));
        expect(result.current.turns).toHaveLength(1);
        act(() => { result.current.accept([], true); });
        expect(result.current.turns).toEqual([]);
    });

    it("isolates conversation and patient recovery state", () => {
        const { result, rerender } = setup();
        act(() => { result.current.accept([row]); });
        rerender({ scope: "patient-2:chat-1" });
        expect(result.current.turns).toEqual([]);
        rerender({ scope: "patient-1:chat-1" });
        expect(result.current.turns).toHaveLength(1);
    });

    it("returns a rejected unsaved request to the composer", () => {
        const { result, send } = setup();
        act(() => { result.current.send("Synthetic", "en-US", null); });
        const id = JSON.parse(send.mock.calls[0][0]).client_message_id;
        act(() => { expect(result.current.reject(id)).toBe("Synthetic"); });
        expect(result.current.turnBusy).toBe(false);
    });

    it.each(["en-US", "es-MX"] as const)("shows safe retry and uncertainty with accessible controls (%s)", (locale) => {
        const retry = vi.fn(); const dismiss = vi.fn();
        const rendered = render(<ChatTurnRecovery turns={[row]} locale={locale} connected onRetry={retry} onDismiss={dismiss} />);
        fireEvent.click(screen.getByRole("button", { name: locale === "es-MX" ? "Reintentar mensaje" : "Retry message" }));
        expect(retry).toHaveBeenCalledWith(row.client_message_id);
        rendered.rerender(<ChatTurnRecovery turns={[{ ...row, retryable: false, failure_code: "action_uncertain" }]} locale={locale} connected onRetry={retry} onDismiss={dismiss} />);
        expect(screen.queryByRole("button", { name: /retry|reintentar/i })).not.toBeInTheDocument();
        expect(screen.getByText(locale === "es-MX" ? /Es posible que se haya registrado/ : /An action may already/)).toBeInTheDocument();
    });

    it("deduplicates saved user and assistant replays in the transcript", () => {
        const message = { id: "saved", patientId: "patient-1", role: ChatRole.ASSISTANT, language: "en-US" as const,
            content: "Synthetic", createdAt: "2026-10-17T10:00:00Z" };
        const state = chatSlice.reducer(chatSlice.reducer(undefined, addMessage(message)), addMessage(message));
        expect(state.messages).toHaveLength(1);
    });

    it("keeps server-reviewed safety guidance visible on an interrupted reply", () => {
        render(<ChatTurnRecovery turns={[{ ...row, safety_guidance: "Reviewed synthetic safety guidance" }]} locale="en-US" connected onRetry={vi.fn()} onDismiss={vi.fn()} />);
        expect(screen.getByRole("alert")).toHaveTextContent("Reviewed synthetic safety guidance");
    });

    it.each(["en-US", "es-MX"] as const)("explains a disabled retry (%s)", (locale) => {
        const copy = getChatRecoveryCopy(locale);
        const view = render(<ChatTurnRecovery turns={[row]} locale={locale} connected={false} onRetry={vi.fn()} onDismiss={vi.fn()} />);
        expect(screen.getByRole("button", { name: copy.retry })).toHaveAccessibleDescription(copy.reconnectBeforeRetry);
        view.rerender(<ChatTurnRecovery turns={[row, { ...row, client_message_id: "another", status: "processing", retryable: false }]} locale={locale} connected onRetry={vi.fn()} onDismiss={vi.fn()} />);
        expect(screen.getByRole("button", { name: copy.retry })).toBeDisabled();
        expect(screen.getByRole("button", { name: copy.retry })).toHaveAccessibleDescription(copy.waitBeforeRetry);
    });
});
