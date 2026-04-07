import type { PayloadAction } from "@reduxjs/toolkit";
import { createSlice } from "@reduxjs/toolkit";
import type { Document } from "@/types";

interface RecordsState {
    documents: Document[];
    loading: boolean;
}

const initialState: RecordsState = {
    documents: [],
    loading: false,
};

export const recordsSlice = createSlice({
    name: "records",
    initialState,
    reducers: {
        setDocuments: (state, action: PayloadAction<Document[]>) => {
            state.documents = action.payload;
        },
        setLoading: (state, action: PayloadAction<boolean>) => {
            state.loading = action.payload;
        },
    },
});

export const { setDocuments, setLoading } = recordsSlice.actions;
