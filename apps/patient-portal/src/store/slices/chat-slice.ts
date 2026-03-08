import { createSlice } from "@reduxjs/toolkit";

interface ChatState {
    messages: unknown[];
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
        addMessage: (state, action) => {
            state.messages.push(action.payload);
        },
        setMessages: (state, action) => {
            state.messages = action.payload;
        },
        setLoading: (state, action) => {
            state.loading = action.payload;
        },
        toggleVoiceMode: (state) => {
            state.isVoiceMode = !state.isVoiceMode;
        },
    },
});

export const { addMessage, setMessages, setLoading, toggleVoiceMode } = chatSlice.actions;
