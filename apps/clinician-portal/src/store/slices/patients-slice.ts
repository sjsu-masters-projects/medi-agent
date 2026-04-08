import type { PayloadAction } from "@reduxjs/toolkit";
import { createSlice } from "@reduxjs/toolkit";
import type { PatientSummary } from "@/types";

interface PatientsState {
    list: PatientSummary[];
    selectedPatient: PatientSummary | null;
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
        setPatients: (state, action: PayloadAction<PatientSummary[]>) => {
            state.list = action.payload;
            state.loading = false;
        },
        setSelectedPatient: (state, action: PayloadAction<PatientSummary | null>) => {
            state.selectedPatient = action.payload;
        },
        setLoading: (state, action: PayloadAction<boolean>) => {
            state.loading = action.payload;
        },
    },
});

export const { setPatients, setSelectedPatient, setLoading } = patientsSlice.actions;
