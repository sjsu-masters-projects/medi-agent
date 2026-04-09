/**
 * Patient detail Redux slice — manages the deep dive data for a single patient.
 */

import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { fetchPatientDeepDive, generateSoapNote } from "@/services/clinicians";
import type { PatientDeepDive, SoapNoteResponse } from "@/services/clinicians";

interface PatientDetailState {
    data: PatientDeepDive | null;
    loadingProfile: boolean;
    generatingSoap: boolean;
    error: string | null;
}

const initialState: PatientDetailState = {
    data: null,
    loadingProfile: false,
    generatingSoap: false,
    error: null,
};

// ── Async thunks ─────────────────────────────────────────────────────────────

export const loadPatientDeepDive = createAsyncThunk(
    "patientDetail/loadDeepDive",
    async (patientId: string, { rejectWithValue }) => {
        try {
            return await fetchPatientDeepDive(patientId);
        } catch (err) {
            return rejectWithValue(
                err instanceof Error ? err.message : "Failed to load patient data",
            );
        }
    },
);

export const triggerSoapNote = createAsyncThunk(
    "patientDetail/triggerSoapNote",
    async (
        { patientId, lookbackDays }: { patientId: string; lookbackDays?: number },
        { rejectWithValue },
    ) => {
        try {
            const result = await generateSoapNote(patientId, lookbackDays);
            return result.soap_note as SoapNoteResponse;
        } catch (err) {
            return rejectWithValue(
                err instanceof Error ? err.message : "Failed to generate SOAP note",
            );
        }
    },
);

// ── Slice ─────────────────────────────────────────────────────────────────────

export const patientDetailSlice = createSlice({
    name: "patientDetail",
    initialState,
    reducers: {
        clearPatientDetail: (state) => {
            state.data = null;
            state.error = null;
        },
    },
    extraReducers: (builder) => {
        builder
            .addCase(loadPatientDeepDive.pending, (state) => {
                state.loadingProfile = true;
                state.error = null;
            })
            .addCase(loadPatientDeepDive.fulfilled, (state, action) => {
                state.data = action.payload;
                state.loadingProfile = false;
            })
            .addCase(loadPatientDeepDive.rejected, (state, action) => {
                state.loadingProfile = false;
                state.error = action.payload as string;
            })
            .addCase(triggerSoapNote.pending, (state) => {
                state.generatingSoap = true;
            })
            .addCase(triggerSoapNote.fulfilled, (state, action) => {
                state.generatingSoap = false;
                if (state.data) {
                    state.data.latest_soap_note = action.payload;
                }
            })
            .addCase(triggerSoapNote.rejected, (state, action) => {
                state.generatingSoap = false;
                state.error = action.payload as string;
            });
    },
});

export const { clearPatientDetail } = patientDetailSlice.actions;
