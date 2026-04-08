import type { PayloadAction } from "@reduxjs/toolkit";
import { createSlice } from "@reduxjs/toolkit";

interface OnboardingProfileDraft {
    dateOfBirth: string;
    firstName: string;
    lastName: string;
}

interface OnboardingState {
    profileDraft: OnboardingProfileDraft | null;
}

const initialState: OnboardingState = {
    profileDraft: null,
};

export const onboardingSlice = createSlice({
    name: "onboarding",
    initialState,
    reducers: {
        clearOnboardingProfile: (state) => {
            state.profileDraft = null;
        },
        setOnboardingProfile: (state, action: PayloadAction<OnboardingProfileDraft>) => {
            state.profileDraft = action.payload;
        },
    },
});

export const { clearOnboardingProfile, setOnboardingProfile } = onboardingSlice.actions;
