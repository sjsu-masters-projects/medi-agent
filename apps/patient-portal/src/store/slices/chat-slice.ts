import type { PayloadAction } from "@reduxjs/toolkit";
import { createSlice } from "@reduxjs/toolkit";
import type { ChatMessage } from "@/types";

interface ChatState {
    messages: ChatMessage[];
    loading: boolean;
    isVoiceMode: boolean;
    isTyping: boolean;
    connectionStatus: "idle" | "connecting" | "connected" | "disconnected" | "error";
    error: string | null;
}

const initialState: ChatState = {
    messages: [],
    loading: false,
    isVoiceMode: false,
    isTyping: false,
    connectionStatus: "idle",
    error: null,
};

const isUnsettled = (message: ChatMessage) => message.delivery !== undefined;

export const chatSlice = createSlice({
    name: "chat",
    initialState,
    reducers: {
        addMessage: (state, action: PayloadAction<ChatMessage>) => {
            const index = state.messages.findIndex((message) => message.id === action.payload.id);
            if (index < 0) state.messages.push(action.payload);
            else state.messages[index] = action.payload;
        },
        setMessages: (state, action: PayloadAction<ChatMessage[]>) => {
            // A history reload must not erase a message the patient has just sent and the
            // server has not yet echoed back (unless the history already holds it).
            const kept = state.messages.filter((message) => isUnsettled(message)
                && !action.payload.some((saved) => saved.role === message.role
                    && saved.content === message.content && saved.id !== message.id
                    && saved.createdAt >= message.createdAt));
            state.messages = [...action.payload, ...kept];
        },
        /** The patient's message, drawn the instant they press send. Keyed by client_message_id. */
        addPendingMessage: (state, action: PayloadAction<ChatMessage>) => {
            const { clientMessageId } = action.payload;
            if (clientMessageId && state.messages.some((m) => m.clientMessageId === clientMessageId)) return;
            state.messages.push({ ...action.payload, delivery: "pending" });
        },
        /** Swap the pending copy for the saved message in place (same position, no duplicate). */
        reconcileSavedMessage: (state, action: PayloadAction<{ clientMessageId?: string | null; message: ChatMessage }>) => {
            const { clientMessageId, message } = action.payload;
            let pendingIndex = clientMessageId
                ? state.messages.findIndex((m) => m.clientMessageId === clientMessageId && isUnsettled(m))
                : -1;
            if (pendingIndex < 0 && !clientMessageId) {
                pendingIndex = state.messages.findIndex((m) => m.delivery === "pending"
                    && m.role === message.role && m.content === message.content);
            }
            const savedIndex = state.messages.findIndex((m) => m.id === message.id && !isUnsettled(m));
            if (pendingIndex < 0) {
                if (clientMessageId) return;
                if (savedIndex < 0) state.messages.push(message);
                else state.messages[savedIndex] = message;
                return;
            }
            // The saved copy keeps the client id, so its React key (and entrance animation) is stable.
            const settled = { ...message, clientMessageId: state.messages[pendingIndex].clientMessageId };
            if (savedIndex >= 0 && savedIndex !== pendingIndex) {
                state.messages[savedIndex] = settled;
                state.messages.splice(pendingIndex, 1);
            } else {
                state.messages[pendingIndex] = settled;
            }
        },
        markMessageFailed: (state, action: PayloadAction<string>) => {
            const target = state.messages.find((m) => m.clientMessageId === action.payload && isUnsettled(m));
            if (target) target.delivery = "failed";
        },
        /** The connection dropped before the server confirmed these: keep the text, offer a retry. */
        failPendingMessages: (state) => {
            for (const message of state.messages) if (message.delivery === "pending") message.delivery = "failed";
        },
        markMessagePending: (state, action: PayloadAction<string>) => {
            const target = state.messages.find((m) => m.clientMessageId === action.payload && isUnsettled(m));
            if (target) target.delivery = "pending";
        },
        removeMessage: (state, action: PayloadAction<string>) => {
            state.messages = state.messages.filter((m) => m.clientMessageId !== action.payload || !isUnsettled(m));
        },
        setLoading: (state, action: PayloadAction<boolean>) => {
            state.loading = action.payload;
        },
        setTyping: (state, action: PayloadAction<boolean>) => {
            state.isTyping = action.payload;
        },
        setConnectionStatus: (
            state,
            action: PayloadAction<ChatState["connectionStatus"]>,
        ) => {
            state.connectionStatus = action.payload;
        },
        setChatError: (state, action: PayloadAction<string | null>) => {
            state.error = action.payload;
        },
        clearChatState: (state) => {
            state.messages = [];
            state.isTyping = false;
            state.error = null;
            state.connectionStatus = "idle";
        },
        toggleVoiceMode: (state) => {
            state.isVoiceMode = !state.isVoiceMode;
        },
    },
});

export const {
    addMessage,
    addPendingMessage,
    failPendingMessages,
    markMessageFailed,
    markMessagePending,
    reconcileSavedMessage,
    removeMessage,
    clearChatState,
    setChatError,
    setConnectionStatus,
    setLoading,
    setMessages,
    setTyping,
    toggleVoiceMode,
} = chatSlice.actions;
