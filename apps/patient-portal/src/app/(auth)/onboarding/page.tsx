"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useDispatch, useSelector } from "react-redux";
import { Button, Card, Input } from "@/components/ui";
import { api } from "@/services/api";
import { getBrowserTimezone, getSupportedTimezones } from "@/services/timezones";
import { clearOnboardingProfile } from "@/store/slices/onboarding-slice";
import type { AppDispatch, RootState } from "@/store/store";
import { DEFAULT_LOCALE, SUPPORTED_LOCALES, getLocaleLabel, normalizeLocale } from "@/types";

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
        timezone: getBrowserTimezone(),
    }));
    const [timezones] = useState<string[]>(() => getSupportedTimezones());

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
                    timezone: formData.timezone,
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
        <div className="app-shell patient-page min-h-dvh pb-10">
            <div className="relative overflow-hidden rounded-b-[38px] bg-[#147465] px-6 pt-14 pb-10 text-white shadow-[0_24px_70px_rgba(20,116,101,0.25)]">
                <div className="absolute -top-16 -right-14 h-52 w-52 rounded-full bg-white/12" />
                <div className="absolute -bottom-20 left-5 h-56 w-56 rounded-full bg-[#d8aa57]/18" />
                <div className="relative">
                <p className="text-xs font-black uppercase tracking-[0.24em] text-white/72">Step {step} of 4</p>
                <h1 className="mt-3 text-[2.35rem] font-black leading-none tracking-[-0.04em]">Complete your profile</h1>
                <p className="mt-4 text-base leading-7 text-white/82">A few details help us personalize reminders and connect you to your clinic.</p>
                <div className="mt-5 flex items-center gap-2">
                    {[1, 2, 3, 4].map((value) => (
                        <span
                            className={`h-2.5 flex-1 rounded-full ${value <= step ? "bg-white" : "bg-white/25"}`}
                            key={value}
                        />
                    ))}
                </div>
                </div>
            </div>

            <div className="patient-stack -mt-5 px-5">
                <Card className="space-y-6 shadow-[0_24px_70px_rgba(42,58,84,0.14)]" padding="lg">
                {step === 1 ? (
                    <div className="space-y-5">
                        <div>
                            <p className="text-xs font-black uppercase tracking-[0.2em] text-[#8090a5]">Personal info</p>
                            <h2 className="mt-1 text-xl font-black text-[#17233a]">Tell us about yourself</h2>
                        </div>
                        <Input label="First name" onChange={(event) => updateField("firstName", event.target.value)} value={formData.firstName} />
                        <Input label="Last name" onChange={(event) => updateField("lastName", event.target.value)} value={formData.lastName} />
                        <Input label="Date of birth" onChange={(event) => updateField("dateOfBirth", event.target.value)} type="date" value={formData.dateOfBirth} />
                    </div>
                ) : null}

                {step === 2 ? (
                    <div className="space-y-5">
                        <div>
                            <p className="text-xs font-black uppercase tracking-[0.2em] text-[#8090a5]">Preferences</p>
                            <h2 className="mt-1 text-xl font-black text-[#17233a]">Set your communication basics</h2>
                        </div>
                        <label className="block text-[0.95rem] font-semibold text-[#30415f]">
                            Preferred language
                            <select
                                className="mt-2 min-h-[3.25rem] w-full rounded-2xl border border-[#d9cbc0] bg-white/90 px-4 py-3 text-base text-[#17233a] shadow-sm outline-none focus:border-[#147465] focus:ring-4 focus:ring-[#147465]/15"
                                onChange={(event) => updateField("language", normalizeLocale(event.target.value))}
                                value={formData.language}
                            >
                                {SUPPORTED_LOCALES.map((locale) => (
                                    <option key={locale} value={locale}>
                                        {getLocaleLabel(locale)}
                                    </option>
                                ))}
                            </select>
                        </label>
                        <label className="block text-[0.95rem] font-semibold text-[#30415f]">
                            Timezone
                            <select
                                className="mt-2 min-h-[3.25rem] w-full rounded-2xl border border-[#d9cbc0] bg-white/90 px-4 py-3 text-base text-[#17233a] shadow-sm outline-none focus:border-[#147465] focus:ring-4 focus:ring-[#147465]/15"
                                onChange={(event) => updateField("timezone", event.target.value)}
                                value={formData.timezone}
                            >
                                {timezones.map((timezone) => (
                                    <option key={timezone} value={timezone}>
                                        {timezone}
                                    </option>
                                ))}
                            </select>
                        </label>
                        <label className="block text-[0.95rem] font-semibold text-[#30415f]">
                            Gender (optional)
                            <select
                                className="mt-2 min-h-[3.25rem] w-full rounded-2xl border border-[#d9cbc0] bg-white/90 px-4 py-3 text-base text-[#17233a] shadow-sm outline-none focus:border-[#147465] focus:ring-4 focus:ring-[#147465]/15"
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
                    <div className="space-y-5">
                        <div>
                            <p className="text-xs font-black uppercase tracking-[0.2em] text-[#8090a5]">Medical info</p>
                            <h2 className="mt-1 text-xl font-black text-[#17233a]">Add context for your care team</h2>
                        </div>
                        <Input label="Known allergies" onChange={(event) => updateField("allergies", event.target.value)} placeholder="Penicillin, peanuts..." value={formData.allergies} />
                        <Input label="Known conditions" onChange={(event) => updateField("conditions", event.target.value)} placeholder="Diabetes, hypertension..." value={formData.conditions} />
                    </div>
                ) : null}

                {step === 4 ? (
                    <div className="space-y-5">
                        <div>
                            <p className="text-xs font-black uppercase tracking-[0.2em] text-[#8090a5]">Join clinic</p>
                            <h2 className="mt-1 text-xl font-black text-[#17233a]">Connect your care team</h2>
                        </div>
                        <Input label="Clinic invite code" onChange={(event) => updateField("inviteCode", event.target.value)} placeholder="CITY-8832" value={formData.inviteCode} />
                        <p className="rounded-2xl bg-[#e6f4f1] px-4 py-3 text-sm font-medium text-[#147465]">This code is required to finish setup and connect your clinic care team.</p>
                    </div>
                ) : null}

                {error ? (
                    <div className="rounded-2xl border border-[#efbeb5] bg-[#fff2ef] px-4 py-3 text-sm font-semibold text-[#b94032]">
                        {error}
                    </div>
                ) : null}

                <div className="flex items-center justify-between gap-3">
                    <Button disabled={step === 1 || submitting} onClick={() => setStep((current) => Math.max(1, current - 1))} variant="secondary">
                        Back
                    </Button>
                    {step < 4 ? (
                        <Button disabled={submitting} onClick={() => setStep((current) => Math.min(4, current + 1))} size="lg">Next</Button>
                    ) : (
                        <Button disabled={submitting} onClick={handleFinish} size="lg">
                            {submitting ? "Saving..." : "Finish setup"}
                        </Button>
                    )}
                </div>
                </Card>
            </div>
        </div>
    );
}
