import { configureStore } from "@reduxjs/toolkit";
import { authSlice } from "./slices/auth-slice";
import { dashboardSlice } from "./slices/dashboard-slice";
import { medwatchSlice } from "./slices/medwatch-slice";
import { patientDetailSlice } from "./slices/patient-detail-slice";

export const store = configureStore({
    reducer: {
        auth: authSlice.reducer,
        dashboard: dashboardSlice.reducer,
        medwatch: medwatchSlice.reducer,
        patientDetail: patientDetailSlice.reducer,
    },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
