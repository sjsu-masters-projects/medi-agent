"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useDispatch, useSelector } from "react-redux";
import { Button, Card, Input } from "@/components/ui";
import { api } from "@/services/api";
import { clearOnboardingProfile } from "@/store/slices/onboarding-slice";
import type { AppDispatch, RootState } from "@/store/store";
import { DEFAULT_LOCALE, Locale, normalizeLocale } from "@/types";

const allowedGenders = ["male", "female", "other", "prefer_not_to_say"] as const;

export default function OnboardingPage() {
    const router = useRouter();
    const accessToken = useSelector((state: RootState) => state.auth.accessToken);
    const profileDraft = useSelector((state: RootState) => state.onboarding.profileDraft);
    const dispatch = useDispatch<AppDispatch>();
    const [error, setError] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [step, setStep] = useState(1);
    const [formData, setFormData] = useState(() => ({
        allergies: "",
        conditions: "",
        dateOfBirth: profileDraft?.dateOfBirth ?? "",
        firstName: profileDraft?.firstName ?? "",
        gender: "",
        inviteCode: "",
        language: DEFAULT_LOCALE,
        lastName: profileDraft?.lastName ?? "",
    }));

    async function handleFinish() {
        if (!accessToken) {
            router.replace("/login");
            return;
        }

        setSubmitting(true);
        setError("");

        if (!formData.firstName.trim() || !formData.lastName.trim()) {
            setError("First name and last name are required.");
            setStep(1);
            setSubmitting(false);
            return;
        }

        const normalizedGender = formData.gender.trim().toLowerCase();
        if (normalizedGender && !allowedGenders.includes(normalizedGender as (typeof allowedGenders)[number])) {
            setError("Please choose a valid gender option.");
            setStep(2);
            setSubmitting(false);
            return;
        }

        if (!formData.inviteCode.trim()) {
            setError("Clinic invite code is required to complete onboarding.");
            setSubmitting(false);
            return;
        }

        try {
            await api.put(
                "/api/v1/patients/me",
                {
                    first_name: formData.firstName.trim(),
                    gender: normalizedGender || undefined,
                    last_name: formData.lastName.trim(),
                    preferred_language: normalizeLocale(formData.language),
                },
                { token: accessToken },
            );

            await api.post<{ clinician_first_name: string }>(
                `/api/v1/patients/me/care-team/join?invite_code=${encodeURIComponent(formData.inviteCode.trim())}`,
                undefined,
                { token: accessToken },
            );
        } catch (submissionError) {
            setError((submissionError as Error).message);
            setSubmitting(false);
            return;
        }

        dispatch(clearOnboardingProfile());
        router.replace("/today");
    }
    function updateField(field: keyof typeof formData, value: string) {
        setFormData((current) => ({ ...current, [field]: value }));
        if (error) {
            setError("");
        }
    }

    return (
        <div className="app-shell min-h-dvh bg-gray-50 pb-10">
            <div className="rounded-b-[28px] bg-sky-700 px-5 pt-12 pb-8 text-white shadow-sm">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-100">Step {step} of 4</p>
                <h1 className="mt-3 text-3xl font-bold">Complete your profile</h1>
                <p className="mt-2 text-sm text-sky-100">A few details help us personalize reminders and connect you to your clinic.</p>
                <div className="mt-5 flex items-center gap-2">
                    {[1, 2, 3, 4].map((value) => (
                        <span
                            className={`h-2.5 flex-1 rounded-full ${value <= step ? "bg-white" : "bg-white/25"}`}
                            key={value}
                        />
                    ))}
                </div>
            </div>

            <div className="-mt-4 px-5">
                <Card className="space-y-6 shadow-lg shadow-slate-100" padding="lg">
                {step === 1 ? (
                    <div className="space-y-4">
                        <div>
                            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Personal info</p>
                            <h2 className="mt-1 text-lg font-semibold text-slate-900">Tell us about yourself</h2>
                        </div>
                        <Input label="First name" onChange={(event) => updateField("firstName", event.target.value)} value={formData.firstName} />
                        <Input label="Last name" onChange={(event) => updateField("lastName", event.target.value)} value={formData.lastName} />
                        <Input label="Date of birth" onChange={(event) => updateField("dateOfBirth", event.target.value)} type="date" value={formData.dateOfBirth} />
                    </div>
                ) : null}

                {step === 2 ? (
                    <div className="space-y-4">
                        <div>
                            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Preferences</p>
                            <h2 className="mt-1 text-lg font-semibold text-slate-900">Set your communication basics</h2>
                        </div>
                        <label className="block text-sm font-medium text-gray-700">
                            Preferred language
                            <select
                                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500"
                                onChange={(event) => updateField("language", normalizeLocale(event.target.value))}
                                value={formData.language}
                            >
                                <option value={Locale.EN_US}>English (US)</option>
                                <option value={Locale.ES_MX}>Español (México)</option>
                            </select>
                        </label>
                        <label className="block text-sm font-medium text-gray-700">
                            Gender (optional)
                            <select
                                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500"
                                onChange={(event) => updateField("gender", event.target.value)}
                                value={formData.gender}
                            >
                                <option value="">Prefer not to say</option>
                                <option value="male">Male</option>
                                <option value="female">Female</option>
                                <option value="other">Other</option>
                                <option value="prefer_not_to_say">Prefer not to say</option>
                            </select>
                        </label>
                    </div>
                ) : null}

                {step === 3 ? (
                    <div className="space-y-4">
                        <div>
                            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Medical info</p>
                            <h2 className="mt-1 text-lg font-semibold text-slate-900">Add context for your care team</h2>
                        </div>
                        <Input label="Known allergies" onChange={(event) => updateField("allergies", event.target.value)} placeholder="Penicillin, peanuts..." value={formData.allergies} />
                        <Input label="Known conditions" onChange={(event) => updateField("conditions", event.target.value)} placeholder="Diabetes, hypertension..." value={formData.conditions} />
                    </div>
                ) : null}

                {step === 4 ? (
                    <div className="space-y-4">
                        <div>
                            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Join clinic</p>
                            <h2 className="mt-1 text-lg font-semibold text-slate-900">Connect your care team</h2>
                        </div>
                        <Input label="Clinic invite code" onChange={(event) => updateField("inviteCode", event.target.value)} placeholder="CITY-8832" value={formData.inviteCode} />
                        <p className="text-sm text-gray-500">This code is required to finish setup and connect your clinic care team.</p>
                    </div>
                ) : null}

                {error ? (
                    <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                        {error}
                    </div>
                ) : null}

                <div className="flex items-center justify-between gap-3">
                    <Button disabled={step === 1 || submitting} onClick={() => setStep((current) => Math.max(1, current - 1))} variant="secondary">
                        Back
                    </Button>
                    {step < 4 ? (
                        <Button disabled={submitting} onClick={() => setStep((current) => Math.min(4, current + 1))}>Next</Button>
                    ) : (
                        <Button disabled={submitting} onClick={handleFinish}>
                            {submitting ? "Saving..." : "Finish setup"}
                        </Button>
                    )}
                </div>
                </Card>
            </div>
        </div>
    );
}
