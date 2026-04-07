import type { PayloadAction } from "@reduxjs/toolkit";
import { createSlice } from "@reduxjs/toolkit";

export interface ClinicianAuthUser {
    id: string;
    email: string;
    role: "provider" | "admin" | "nurse" | "clinician";
}

interface AuthState {
    user: ClinicianAuthUser | null;
    token: string | null;
    isAuthenticated: boolean;
    loading: boolean;
}

const initialState: AuthState = {
    user: null,
    token: null,
    isAuthenticated: false,
    loading: true,
};

export const authSlice = createSlice({
    name: "auth",
    initialState,
    reducers: {
        hydrateSession: (
            state,
            action: PayloadAction<{ token: string | null; user: ClinicianAuthUser } | null>,
        ) => {
            state.user = action.payload?.user ?? null;
            state.token = action.payload?.token ?? null;
            state.isAuthenticated = !!action.payload?.user;
            state.loading = false;
        },
        setUser: (state, action: PayloadAction<ClinicianAuthUser | null>) => {
            state.user = action.payload;
            state.isAuthenticated = !!action.payload;
            state.loading = false;
        },
        setToken: (state, action: PayloadAction<string | null>) => {
            state.token = action.payload;
        },
        finishHydration: (state) => {
            state.loading = false;
        },
        logout: (state) => {
            state.user = null;
            state.token = null;
            state.isAuthenticated = false;
            state.loading = false;
        },
    },
});

export const { hydrateSession, setUser, setToken, finishHydration, logout } = authSlice.actions;
