"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useDispatch } from "react-redux";
import { Button, Card, Input } from "@/components/ui";
import { api } from "@/services/api";
import { hydrateSession } from "@/store/slices/auth-slice";
import type { AppDispatch } from "@/store/store";

const authStorageKey = "mediagent-patient-auth";
const onboardingStorageKey = "mediagent-onboarding-profile";

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
            window.sessionStorage.setItem(
                onboardingStorageKey,
                JSON.stringify({
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
        <div className="app-shell min-h-dvh bg-gray-50 px-5 py-10">
            <div className="space-y-6">
                <div className="space-y-2 text-center">
                    <p className="text-sm font-medium text-blue-600">Create your account</p>
                    <h1 className="text-3xl font-bold text-gray-900">Join MediAgent</h1>
                </div>
                <Card padding="lg">
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
                <p className="text-center text-sm text-gray-500">
                    Already have an account?{" "}
                    <Link className="font-medium text-blue-600" href="/login">
                        Sign in
                    </Link>
                </p>
            </div>
        </div>
    );
}
