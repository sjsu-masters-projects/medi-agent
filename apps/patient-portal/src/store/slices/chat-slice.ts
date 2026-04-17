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

export const chatSlice = createSlice({
    name: "chat",
    initialState,
    reducers: {
        addMessage: (state, action: PayloadAction<ChatMessage>) => {
            state.messages.push(action.payload);
        },
        setMessages: (state, action: PayloadAction<ChatMessage[]>) => {
            state.messages = action.payload;
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
    clearChatState,
    setChatError,
    setConnectionStatus,
    setLoading,
    setMessages,
    setTyping,
    toggleVoiceMode,
} = chatSlice.actions;
