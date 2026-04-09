import type { PayloadAction } from "@reduxjs/toolkit";
import { createSlice } from "@reduxjs/toolkit";

export interface PatientAuthUser {
    id: string;
    email: string;
    role: "patient";
}

export interface PatientAuthSession {
    accessToken: string;
    refreshToken: string;
    expiresAt: number;
    user: PatientAuthUser;
}

interface AuthState {
    user: PatientAuthUser | null;
    accessToken: string | null;
    refreshToken: string | null;
    expiresAt: number | null;
    isAuthenticated: boolean;
    loading: boolean;
}

const initialState: AuthState = {
    user: null,
    accessToken: null,
    refreshToken: null,
    expiresAt: null,
    isAuthenticated: false,
    loading: true,
};

export const authSlice = createSlice({
    name: "auth",
    initialState,
    reducers: {
        hydrateSession: (
            state,
            action: PayloadAction<PatientAuthSession | null>,
        ) => {
            state.user = action.payload?.user ?? null;
            state.accessToken = action.payload?.accessToken ?? null;
            state.refreshToken = action.payload?.refreshToken ?? null;
            state.expiresAt = action.payload?.expiresAt ?? null;
            state.isAuthenticated = !!action.payload?.user;
            state.loading = false;
        },
        setUser: (state, action: PayloadAction<PatientAuthUser | null>) => {
            state.user = action.payload;
            state.isAuthenticated = !!action.payload;
            state.loading = false;
        },
        setAccessToken: (state, action: PayloadAction<string | null>) => {
            state.accessToken = action.payload;
        },
        setRefreshToken: (state, action: PayloadAction<string | null>) => {
            state.refreshToken = action.payload;
        },
        setExpiresAt: (state, action: PayloadAction<number | null>) => {
            state.expiresAt = action.payload;
        },
        finishHydration: (state) => {
            state.loading = false;
        },
        logout: (state) => {
            state.user = null;
            state.accessToken = null;
            state.refreshToken = null;
            state.expiresAt = null;
            state.isAuthenticated = false;
            state.loading = false;
        },
    },
});

export const { hydrateSession, setUser, setAccessToken, setRefreshToken, setExpiresAt, finishHydration, logout } =
    authSlice.actions;
