import type { PayloadAction } from "@reduxjs/toolkit";
import { createSlice } from "@reduxjs/toolkit";
import type { PatientSummary } from "@/types";

export interface DashboardStat {
    change: string;
    label: string;
    trend: "up" | "down" | "neutral";
    value: string;
}

interface DashboardState {
    stats: DashboardStat[];
    patients: PatientSummary[];
    loading: boolean;
}

const initialState: DashboardState = {
    stats: [],
    patients: [],
    loading: false,
};

export const dashboardSlice = createSlice({
    name: "dashboard",
    initialState,
    reducers: {
        setPatients: (state, action: PayloadAction<PatientSummary[]>) => {
            state.patients = action.payload;
            state.loading = false;
        },
        setStats: (state, action: PayloadAction<DashboardStat[]>) => {
            state.stats = action.payload;
        },
        setLoading: (state, action: PayloadAction<boolean>) => {
            state.loading = action.payload;
        },
    },
});

export const { setPatients, setStats, setLoading } = dashboardSlice.actions;
