"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useDispatch } from "react-redux";
import { Button, Card, Input } from "@/components/ui";
import { api } from "@/services/api";
import { hydrateSession } from "@/store/slices/auth-slice";
import { setOnboardingProfile } from "@/store/slices/onboarding-slice";
import type { AppDispatch } from "@/store/store";

const authStorageKey = "mediagent-patient-auth";

interface SignupResponse {
    tokens: {
        access_token: string;
    };
    user: {
        email: string;
        id: string;
        role: "patient" | "clinician";
    };
}

export default function SignupPage() {
    const router = useRouter();
    const dispatch = useDispatch<AppDispatch>();
    const [error, setError] = useState("");
    const [formData, setFormData] = useState({
        confirmPassword: "",
        dateOfBirth: "1985-03-15",
        email: "",
        firstName: "",
        lastName: "",
        password: "",
    });

    async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setError("");

        if (formData.password !== formData.confirmPassword) {
            setError("Passwords do not match.");
            return;
        }

        try {
            const response = await api.post<SignupResponse>("/api/v1/auth/signup/patient", {
                date_of_birth: formData.dateOfBirth,
                email: formData.email,
                first_name: formData.firstName,
                last_name: formData.lastName,
                password: formData.password,
            });

            const session = { token: response.tokens.access_token, user: response.user };
            window.localStorage.setItem(authStorageKey, JSON.stringify(session));
            dispatch(
                setOnboardingProfile({
                    dateOfBirth: formData.dateOfBirth,
                    firstName: formData.firstName,
                    lastName: formData.lastName,
                }),
            );
            dispatch(hydrateSession(session));
            router.replace("/onboarding");
        } catch (submissionError) {
            setError((submissionError as Error).message);
        }
    }

    function updateField(field: keyof typeof formData, value: string) {
        setFormData((current) => ({ ...current, [field]: value }));
    }

    return (
        <div className="app-shell min-h-dvh bg-gray-50 pb-10">
            <div className="rounded-b-[28px] bg-sky-700 px-5 pt-12 pb-8 text-white shadow-sm">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-100">Patient signup</p>
                <h1 className="mt-3 text-3xl font-bold">Join MediAgent</h1>
                <p className="mt-2 max-w-sm text-sm text-sky-100">
                    Set up your account to track medications, symptoms, and care updates in one place.
                </p>
            </div>

            <div className="-mt-4 space-y-5 px-5">
                <Card className="shadow-lg shadow-slate-100" padding="lg">
                    <div className="mb-5 flex items-center gap-2">
                        <span className="h-2.5 w-10 rounded-full bg-sky-700" />
                        <span className="h-2.5 w-10 rounded-full bg-sky-200" />
                        <span className="h-2.5 w-10 rounded-full bg-sky-200" />
                    </div>
                    <form className="space-y-4" onSubmit={handleSubmit}>
                        <Input label="First name" onChange={(event) => updateField("firstName", event.target.value)} value={formData.firstName} />
                        <Input label="Last name" onChange={(event) => updateField("lastName", event.target.value)} value={formData.lastName} />
                        <Input label="Date of birth" onChange={(event) => updateField("dateOfBirth", event.target.value)} type="date" value={formData.dateOfBirth} />
                        <Input label="Email" onChange={(event) => updateField("email", event.target.value)} type="email" value={formData.email} />
                        <Input label="Password" onChange={(event) => updateField("password", event.target.value)} type="password" value={formData.password} />
                        <Input
                            label="Confirm password"
                            onChange={(event) => updateField("confirmPassword", event.target.value)}
                            type="password"
                            value={formData.confirmPassword}
                        />
                        {error ? <p className="text-sm text-red-600">{error}</p> : null}
                        <Button fullWidth type="submit">Create account</Button>
                    </form>
                </Card>

                <Card className="space-y-2 border-slate-100 bg-white" padding="md">
                    <p className="text-sm text-slate-500">Already have an account?</p>
                    <Link className="text-sm font-medium text-sky-700" href="/login">
                        Sign in
                    </Link>
                </Card>
            </div>
        </div>
    );
}
