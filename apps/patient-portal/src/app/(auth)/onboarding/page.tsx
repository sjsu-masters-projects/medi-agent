"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useDispatch, useSelector } from "react-redux";
import { Button, Card, Input } from "@/components/ui";
import { api } from "@/services/api";
import { clearOnboardingProfile } from "@/store/slices/onboarding-slice";
import type { AppDispatch, RootState } from "@/store/store";

export default function OnboardingPage() {
    const router = useRouter();
    const token = useSelector((state: RootState) => state.auth.token);
    const profileDraft = useSelector((state: RootState) => state.onboarding.profileDraft);
    const dispatch = useDispatch<AppDispatch>();
    const [step, setStep] = useState(1);
    const [formData, setFormData] = useState({
        allergies: "",
        conditions: "",
        dateOfBirth: "",
        firstName: "",
        gender: "",
        inviteCode: "",
        language: "en",
        lastName: "",
    });

    useEffect(() => {
        if (!profileDraft) {
            return;
        }
        setFormData((current) => ({ ...current, ...profileDraft }));
    }, [profileDraft]);

    async function handleFinish() {
        if (!token) {
            router.replace("/login");
            return;
        }

        try {
            await api.put(
                "/api/v1/patients/me",
                {
                    first_name: formData.firstName,
                    gender: formData.gender || undefined,
                    last_name: formData.lastName,
                    preferred_language: formData.language,
                },
                { token },
            );

            if (formData.inviteCode.trim()) {
                await api.post(
                    `/api/v1/patients/me/care-team/join?invite_code=${encodeURIComponent(formData.inviteCode.trim())}`,
                    undefined,
                    { token },
                );
            }
        } catch {
            // Keep onboarding resilient even while backend support for all fields is still evolving.
        } finally {
            dispatch(clearOnboardingProfile());
            router.replace("/today");
        }
    }

    function updateField(field: keyof typeof formData, value: string) {
        setFormData((current) => ({ ...current, [field]: value }));
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
                                onChange={(event) => updateField("language", event.target.value)}
                                value={formData.language}
                            >
                                <option value="en">English</option>
                                <option value="es">Spanish</option>
                            </select>
                        </label>
                        <Input label="Gender (optional)" onChange={(event) => updateField("gender", event.target.value)} value={formData.gender} />
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
                        <p className="text-sm text-gray-500">You can skip this now and link your clinic later from the portal.</p>
                    </div>
                ) : null}

                <div className="flex items-center justify-between gap-3">
                    <Button disabled={step === 1} onClick={() => setStep((current) => Math.max(1, current - 1))} variant="secondary">
                        Back
                    </Button>
                    {step < 4 ? (
                        <Button onClick={() => setStep((current) => Math.min(4, current + 1))}>Next</Button>
                    ) : (
                        <Button onClick={handleFinish}>Finish setup</Button>
                    )}
                </div>
            </Card>
            </div>
        </div>
    );
}
