"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useDispatch } from "react-redux";
import { Button, Card, Input } from "@/components/ui";
import { api } from "@/services/api";
import { writeStoredSession } from "@/services/auth-session";
import { hydrateSession, type ClinicianAuthSession } from "@/store/slices/auth-slice";
import type { AppDispatch } from "@/store/store";

interface SignupResponse {
    tokens: {
        access_token: string;
        expires_at: number;
        refresh_token: string;
    };
    user: {
        email: string;
        id: string;
        role: "patient" | "clinician";
    };
}

export default function ClinicianSignupPage() {
    const router = useRouter();
    const dispatch = useDispatch<AppDispatch>();
    const [error, setError] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [formData, setFormData] = useState({
        clinicName: "",
        confirmPassword: "",
        email: "",
        firstName: "",
        lastName: "",
        npiNumber: "",
        password: "",
        specialty: "",
    });

    function updateField(field: keyof typeof formData, value: string) {
        setFormData((current) => ({ ...current, [field]: value }));
    }

    async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setError("");

        if (formData.password !== formData.confirmPassword) {
            setError("Passwords do not match.");
            return;
        }

        setSubmitting(true);

        try {
            const response = await api.post<SignupResponse>("/api/v1/auth/signup/clinician", {
                clinic_name: formData.clinicName,
                email: formData.email,
                first_name: formData.firstName,
                last_name: formData.lastName,
                npi_number: formData.npiNumber || undefined,
                password: formData.password,
                specialty: formData.specialty,
            });

            if (response.user.role !== "clinician") {
                throw new Error("This signup produced a non-clinician account.");
            }

            const session: ClinicianAuthSession = {
                accessToken: response.tokens.access_token,
                expiresAt: response.tokens.expires_at,
                refreshToken: response.tokens.refresh_token,
                user: {
                    email: response.user.email,
                    id: response.user.id,
                    role: "clinician",
                },
            };
            writeStoredSession(session);
            dispatch(hydrateSession(session));
            router.replace("/dashboard");
        } catch (submissionError) {
            setError((submissionError as Error).message);
            setSubmitting(false);
        }
    }

    return (
        <div className="flex min-h-screen bg-gray-50">
            <div className="hidden w-1/2 bg-gray-900 px-12 py-16 text-white lg:flex lg:flex-col lg:justify-between">
                <div className="space-y-4">
                    <p className="text-sm font-medium uppercase tracking-[0.3em] text-blue-300">MediAgent Pro</p>
                    <h1 className="max-w-md text-5xl font-bold leading-tight">Stand up your clinic workspace with one secure account.</h1>
                    <p className="max-w-lg text-lg text-gray-300">
                        Create your clinician account, connect your clinic identity, and begin managing patient follow-up from a shared dashboard.
                    </p>
                </div>
                <p className="text-sm text-gray-400">Supabase-backed auth with role-aware access through the backend API.</p>
            </div>

            <div className="flex flex-1 items-center justify-center px-6 py-12">
                <Card className="w-full max-w-xl space-y-6" padding="lg">
                    <div className="space-y-2">
                        <p className="text-sm font-medium text-blue-600">Clinician signup</p>
                        <h2 className="text-3xl font-bold text-gray-900">Create your account</h2>
                        <p className="text-sm text-gray-500">Set up a clinician login for dashboard access and invite-code workflows.</p>
                    </div>
                    <form className="grid gap-4 md:grid-cols-2" onSubmit={handleSubmit}>
                        <Input label="First name" onChange={(event) => updateField("firstName", event.target.value)} value={formData.firstName} />
                        <Input label="Last name" onChange={(event) => updateField("lastName", event.target.value)} value={formData.lastName} />
                        <Input label="Email" onChange={(event) => updateField("email", event.target.value)} type="email" value={formData.email} />
                        <Input label="Specialty" onChange={(event) => updateField("specialty", event.target.value)} value={formData.specialty} />
                        <Input label="Clinic name" onChange={(event) => updateField("clinicName", event.target.value)} value={formData.clinicName} />
                        <Input label="NPI number (optional)" onChange={(event) => updateField("npiNumber", event.target.value)} value={formData.npiNumber} />
                        <Input label="Password" onChange={(event) => updateField("password", event.target.value)} type="password" value={formData.password} />
                        <Input
                            label="Confirm password"
                            onChange={(event) => updateField("confirmPassword", event.target.value)}
                            type="password"
                            value={formData.confirmPassword}
                        />
                        {error ? <p className="text-sm text-red-600 md:col-span-2">{error}</p> : null}
                        <div className="md:col-span-2">
                            <Button disabled={submitting} fullWidth type="submit">
                                {submitting ? "Creating account..." : "Create clinician account"}
                            </Button>
                        </div>
                    </form>
                    <div className="text-sm text-gray-500">
                        Already have a clinician account?{" "}
                        <Link className="font-medium text-blue-600" href="/login">
                            Sign in
                        </Link>
                    </div>
                </Card>
            </div>
        </div>
    );
}
