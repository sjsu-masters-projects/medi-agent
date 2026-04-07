import type { PayloadAction } from "@reduxjs/toolkit";
import { createSlice } from "@reduxjs/toolkit";
import type { MedWatchDraft } from "@/types";

interface MedwatchState {
    drafts: MedWatchDraft[];
    selectedDraft: MedWatchDraft | null;
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
        setDrafts: (state, action: PayloadAction<MedWatchDraft[]>) => {
            state.drafts = action.payload;
            state.loading = false;
        },
        setSelectedDraft: (state, action: PayloadAction<MedWatchDraft | null>) => {
            state.selectedDraft = action.payload;
        },
        setLoading: (state, action: PayloadAction<boolean>) => {
            state.loading = action.payload;
        },
    },
});

export const { setDrafts, setSelectedDraft, setLoading } = medwatchSlice.actions;
