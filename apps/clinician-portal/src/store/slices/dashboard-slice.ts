import { createSlice } from "@reduxjs/toolkit";

interface DashboardState {
    riskData: unknown[];
    loading: boolean;
}

const initialState: DashboardState = {
    riskData: [],
    loading: false,
};

export const dashboardSlice = createSlice({
    name: "dashboard",
    initialState,
    reducers: {
        setRiskData: (state, action) => {
            state.riskData = action.payload;
            state.loading = false;
        },
        setLoading: (state, action) => {
            state.loading = action.payload;
        },
    },
});

export const { setRiskData, setLoading } = dashboardSlice.actions;
