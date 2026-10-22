import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChatBubble } from "@/components/features/chat-bubble";
import {
    addPendingMessage, chatSlice, failPendingMessages, markMessageFailed, reconcileSavedMessage, removeMessage, setMessages,
} from "@/store/slices/chat-slice";
import { ChatRole, type ChatMessage } from "@/types";

const reducer = chatSlice.reducer;
const initial = reducer(undefined, { type: "init" });
const pending = (cid: string, content = "Do I have an appointment?"): ChatMessage => ({
    clientMessageId: cid, content, createdAt: "2026-10-19T18:27:00Z", id: `pending-${cid}`,
    language: "en-US" as ChatMessage["language"], patientId: "p", role: ChatRole.USER,
});
const saved = (id: string, content = "Do I have an appointment?"): ChatMessage => ({
    content, createdAt: "2026-10-19T18:27:01Z", id, language: "en-US" as ChatMessage["language"],
    patientId: "p", role: ChatRole.USER,
});
const assistant: ChatMessage = { ...saved("a1", "Earlier reply"), role: ChatRole.ASSISTANT };

describe("optimistic user message", () => {
    it("is shown immediately as pending", () => {
        const state = reducer(initial, addPendingMessage(pending("c1")));
        expect(state.messages).toHaveLength(1);
        expect(state.messages[0].delivery).toBe("pending");
    });

    it("is replaced in place by the saved message, with no duplicate and no reordering", () => {
        let state = reducer(initial, setMessages([assistant]));
        state = reducer(state, addPendingMessage(pending("c1")));
        state = reducer(state, addPendingMessage(pending("c2", "second")));
        state = reducer(state, reconcileSavedMessage({ clientMessageId: "c1", message: saved("srv-1") }));
        expect(state.messages.map((m) => m.id)).toEqual(["a1", "srv-1", "pending-c2"]);
        expect(state.messages[1].delivery).toBeUndefined();
        expect(state.messages[1].clientMessageId).toBe("c1");
        // A repeat of the same event (at-least-once delivery) changes nothing.
        const again = reducer(state, reconcileSavedMessage({ clientMessageId: "c1", message: saved("srv-1") }));
        expect(again.messages).toEqual(state.messages);
    });

    it("drops the pending copy when the saved message already arrived by id", () => {
        let state = reducer(initial, addPendingMessage(pending("c1")));
        state = { ...state, messages: [...state.messages, saved("srv-1")] };
        state = reducer(state, reconcileSavedMessage({ clientMessageId: "c1", message: saved("srv-1") }));
        expect(state.messages.map((m) => m.id)).toEqual(["srv-1"]);
    });

    it("matches an older event without a client id by identical pending text", () => {
        let state = reducer(initial, addPendingMessage(pending("c1")));
        state = reducer(state, reconcileSavedMessage({ message: saved("srv-1") }));
        expect(state.messages.map((m) => m.id)).toEqual(["srv-1"]);
    });

    it("keeps a pending message through a history reload that does not hold it yet", () => {
        let state = reducer(initial, addPendingMessage(pending("c1")));
        state = reducer(state, setMessages([assistant]));
        expect(state.messages.map((m) => m.id)).toEqual(["a1", "pending-c1"]);
    });

    it("marks every unconfirmed message failed when the connection drops, and a reconnect snapshot settles it", () => {
        let state = reducer(initial, addPendingMessage(pending("c1")));
        state = reducer(state, failPendingMessages());
        expect(state.messages[0].delivery).toBe("failed");
        state = reducer(state, reconcileSavedMessage({ clientMessageId: "c1", message: saved("srv-1") }));
        expect(state.messages).toHaveLength(1);
        expect(state.messages[0].delivery).toBeUndefined();
    });

    it("keeps the text in a failed state, and removing it is explicit", () => {
        let state = reducer(initial, addPendingMessage(pending("c1")));
        state = reducer(state, markMessageFailed("c1"));
        expect(state.messages[0]).toMatchObject({ delivery: "failed", content: "Do I have an appointment?" });
        state = reducer(state, removeMessage("c1"));
        expect(state.messages).toEqual([]);
    });
});

describe("pending user bubble", () => {
    it.each([["en-US", "Sending…"], ["es-MX", "Enviando…"]] as const)("announces sending in %s", (locale, text) => {
        render(<ChatBubble role="user" content="Hola" timestamp="2026-10-19T18:27:00Z" locale={locale} delivery="pending" />);
        expect(screen.getByRole("status")).toHaveTextContent(text);
        expect(screen.getByText("Hola")).toBeInTheDocument();
    });

    it("offers retry and remove on a failed send, with the text preserved", () => {
        const retry = vi.fn();
        const remove = vi.fn();
        render(<ChatBubble role="user" content="Keep this text" timestamp="2026-10-19T18:27:00Z" locale="en-US"
            delivery="failed" onRetrySend={retry} onRemoveUnsent={remove} />);
        expect(screen.getByText("Keep this text")).toBeInTheDocument();
        expect(screen.getByRole("alert")).toHaveTextContent("Not sent");
        fireEvent.click(screen.getByRole("button", { name: "Retry" }));
        fireEvent.click(screen.getByRole("button", { name: "Remove" }));
        expect(retry).toHaveBeenCalledOnce();
        expect(remove).toHaveBeenCalledOnce();
    });
});
