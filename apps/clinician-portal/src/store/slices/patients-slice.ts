import { createSlice } from "@reduxjs/toolkit";

interface PatientsState {
    list: unknown[];
    selectedPatient: unknown;
    loading: boolean;
}

const initialState: PatientsState = {
    list: [],
    selectedPatient: null,
    loading: false,
};

export const patientsSlice = createSlice({
    name: "patients",
    initialState,
    reducers: {
        setPatients: (state, action) => {
            state.list = action.payload;
            state.loading = false;
        },
        setSelectedPatient: (state, action) => {
            state.selectedPatient = action.payload;
        },
        setLoading: (state, action) => {
            state.loading = action.payload;
        },
    },
});

export const { setPatients, setSelectedPatient, setLoading } = patientsSlice.actions;
