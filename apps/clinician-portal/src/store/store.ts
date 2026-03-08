import { configureStore } from "@reduxjs/toolkit";
import { authSlice } from "./slices/auth-slice";
import { dashboardSlice } from "./slices/dashboard-slice";
import { patientsSlice } from "./slices/patients-slice";
import { medwatchSlice } from "./slices/medwatch-slice";

export const store = configureStore({
    reducer: {
        auth: authSlice.reducer,
        dashboard: dashboardSlice.reducer,
        patients: patientsSlice.reducer,
        medwatch: medwatchSlice.reducer,
    },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
