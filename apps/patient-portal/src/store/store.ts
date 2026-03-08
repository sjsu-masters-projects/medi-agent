import { configureStore } from "@reduxjs/toolkit";
import { authSlice } from "./slices/auth-slice";
import { feedSlice } from "./slices/feed-slice";
import { chatSlice } from "./slices/chat-slice";
import { recordsSlice } from "./slices/records-slice";

export const store = configureStore({
    reducer: {
        auth: authSlice.reducer,
        feed: feedSlice.reducer,
        chat: chatSlice.reducer,
        records: recordsSlice.reducer,
    },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
