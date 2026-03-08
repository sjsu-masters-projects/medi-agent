import { createSlice } from "@reduxjs/toolkit";

interface FeedState {
    tasks: unknown[];
    loading: boolean;
    error: string | null;
}

const initialState: FeedState = {
    tasks: [],
    loading: false,
    error: null,
};

export const feedSlice = createSlice({
    name: "feed",
    initialState,
    reducers: {
        setTasks: (state, action) => {
            state.tasks = action.payload;
            state.loading = false;
        },
        setLoading: (state, action) => {
            state.loading = action.payload;
        },
        setError: (state, action) => {
            state.error = action.payload;
            state.loading = false;
        },
    },
});

export const { setTasks, setLoading, setError } = feedSlice.actions;
