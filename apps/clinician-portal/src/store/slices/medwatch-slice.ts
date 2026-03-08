import { createSlice } from "@reduxjs/toolkit";

interface MedwatchState {
    drafts: unknown[];
    selectedDraft: unknown;
    loading: boolean;
}

const initialState: MedwatchState = {
    drafts: [],
    selectedDraft: null,
    loading: false,
};

export const medwatchSlice = createSlice({
    name: "medwatch",
    initialState,
    reducers: {
        setDrafts: (state, action) => {
            state.drafts = action.payload;
            state.loading = false;
        },
        setSelectedDraft: (state, action) => {
            state.selectedDraft = action.payload;
        },
        setLoading: (state, action) => {
            state.loading = action.payload;
        },
    },
});

export const { setDrafts, setSelectedDraft, setLoading } = medwatchSlice.actions;
