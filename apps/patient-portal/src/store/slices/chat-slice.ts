import type { PayloadAction } from "@reduxjs/toolkit";
import { createSlice } from "@reduxjs/toolkit";
import type { ChatMessage } from "@/types";

interface ChatState {
    messages: ChatMessage[];
    loading: boolean;
    isVoiceMode: boolean;
}

const initialState: ChatState = {
    messages: [],
    loading: false,
    isVoiceMode: false,
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
        toggleVoiceMode: (state) => {
            state.isVoiceMode = !state.isVoiceMode;
        },
    },
});

export const { addMessage, setMessages, setLoading, toggleVoiceMode } = chatSlice.actions;
