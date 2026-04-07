"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useSelector } from "react-redux";
import { Button, Card, Input } from "@/components/ui";
import { api } from "@/services/api";
import type { RootState } from "@/store/store";

const onboardingStorageKey = "mediagent-onboarding-profile";

export default function OnboardingPage() {
    const router = useRouter();
    const token = useSelector((state: RootState) => state.auth.token);
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
        const storedValue = window.sessionStorage.getItem(onboardingStorageKey);
        if (!storedValue) {
            return;
        }

        try {
            const parsed = JSON.parse(storedValue) as {
                dateOfBirth: string;
                firstName: string;
                lastName: string;
            };
            setFormData((current) => ({ ...current, ...parsed }));
        } catch {
            window.sessionStorage.removeItem(onboardingStorageKey);
        }
    }, []);

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
            window.sessionStorage.removeItem(onboardingStorageKey);
            router.replace("/today");
        }
    }

    function updateField(field: keyof typeof formData, value: string) {
        setFormData((current) => ({ ...current, [field]: value }));
    }

    return (
        <div className="app-shell min-h-dvh bg-gray-50 px-5 py-10">
            <Card className="space-y-6" padding="lg">
                <div>
                    <p className="text-sm font-medium text-blue-600">Step {step} of 4</p>
                    <h1 className="mt-1 text-2xl font-bold text-gray-900">Complete your profile</h1>
                </div>

                {step === 1 ? (
                    <div className="space-y-4">
                        <Input label="First name" onChange={(event) => updateField("firstName", event.target.value)} value={formData.firstName} />
                        <Input label="Last name" onChange={(event) => updateField("lastName", event.target.value)} value={formData.lastName} />
                        <Input label="Date of birth" onChange={(event) => updateField("dateOfBirth", event.target.value)} type="date" value={formData.dateOfBirth} />
                    </div>
                ) : null}

                {step === 2 ? (
                    <div className="space-y-4">
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
                        <Input label="Known allergies" onChange={(event) => updateField("allergies", event.target.value)} placeholder="Penicillin, peanuts..." value={formData.allergies} />
                        <Input label="Known conditions" onChange={(event) => updateField("conditions", event.target.value)} placeholder="Diabetes, hypertension..." value={formData.conditions} />
                    </div>
                ) : null}

                {step === 4 ? (
                    <div className="space-y-4">
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
    );
}
