import { createSlice } from "@reduxjs/toolkit";

interface RecordsState {
    documents: unknown[];
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
        setDocuments: (state, action) => {
            state.documents = action.payload;
        },
        setLoading: (state, action) => {
            state.loading = action.payload;
        },
    },
});

export const { setDocuments, setLoading } = recordsSlice.actions;
