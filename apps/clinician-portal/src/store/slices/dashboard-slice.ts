/**
 * Dashboard Redux slice — Risk Radar state management.
 *
 * Includes async thunk for fetching real API data + handling loading/error states.
 */

import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import type { PayloadAction } from "@reduxjs/toolkit";
import { fetchDashboard } from "@/services/clinicians";
import type { DashboardResponse, PatientRiskData } from "@/services/clinicians";

export interface DashboardStat {
    change: string;
    label: string;
    trend: "up" | "down" | "neutral";
    value: string;
}

interface DashboardState {
    stats: DashboardStat[];
    patients: PatientRiskData[];
    summary: Omit<DashboardResponse, "patients"> | null;
    loading: boolean;
    error: string | null;
}

const initialState: DashboardState = {
    stats: [],
    patients: [],
    summary: null,
    loading: false,
    error: null,
};

// ── Async thunk ──────────────────────────────────────────────────────────────

export const loadDashboard = createAsyncThunk(
    "dashboard/loadDashboard",
    async (_, { rejectWithValue }) => {
        try {
            return await fetchDashboard();
        } catch (err) {
            return rejectWithValue(err instanceof Error ? err.message : "Failed to load dashboard");
        }
    },
);

// ── Slice ────────────────────────────────────────────────────────────────────

export const dashboardSlice = createSlice({
    name: "dashboard",
    initialState,
    reducers: {
        /** Manual override for mock data / SSR hydration. */
        setPatients: (state, action: PayloadAction<PatientRiskData[]>) => {
            state.patients = action.payload;
            state.loading = false;
        },
        setStats: (state, action: PayloadAction<DashboardStat[]>) => {
            state.stats = action.payload;
        },
        setLoading: (state, action: PayloadAction<boolean>) => {
            state.loading = action.payload;
        },
        /** Update a single patient's risk data (Supabase Realtime patch). */
        patchPatient: (state, action: PayloadAction<Partial<PatientRiskData> & { patient_id: string }>) => {
            const index = state.patients.findIndex(
                (p) => p.patient_id === action.payload.patient_id,
            );
            if (index !== -1) {
                state.patients[index] = { ...state.patients[index], ...action.payload };
            }
        },
    },
    extraReducers: (builder) => {
        builder
            .addCase(loadDashboard.pending, (state) => {
                state.loading = true;
                state.error = null;
            })
            .addCase(loadDashboard.fulfilled, (state, action) => {
                const { patients, ...summary } = action.payload;
                state.patients = patients;
                state.summary = summary;
                state.loading = false;
                state.error = null;
                // Build stats cards from summary
                state.stats = [
                    {
                        label: "Monitored Patients",
                        value: String(summary.total),
                        trend: "neutral",
                        change: "",
                    },
                    {
                        label: "Critical Risk (< 60% or ADR)",
                        value: String(summary.high_risk),
                        trend: summary.high_risk > 0 ? "up" : "neutral",
                        change: "",
                    },
                    {
                        label: "FDA MedWatch Drafts",
                        value: `${summary.medwatch_pending} Pending`,
                        trend: "neutral",
                        change: "",
                    },
                ];
            })
            .addCase(loadDashboard.rejected, (state, action) => {
                state.loading = false;
                state.error = action.payload as string;
            });
    },
});

export const { setPatients, setStats, setLoading, patchPatient } = dashboardSlice.actions;
export type { PatientRiskData };
