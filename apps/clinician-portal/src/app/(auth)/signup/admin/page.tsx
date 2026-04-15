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

function InfoIcon({ text }: { text: string }) {
    return (
        <span className="group relative inline-flex items-center">
            <span
                aria-label={text}
                className="inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-slate-400 text-[10px] font-semibold text-slate-600"
                role="img"
                tabIndex={0}
            >
                i
            </span>
            <span
                className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 w-56 -translate-x-1/2 rounded-md bg-slate-900 px-2 py-1 text-xs font-normal text-white opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100"
                role="tooltip"
            >
                {text}
            </span>
        </span>
    );
}

export default function ClinicAdminSignupPage() {
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
        password: "",
        specialty: "",
        type1Npi: "",
        type2Npi: "",
    });
    const isClinicAlreadyExistsError = error.toLowerCase().includes("clinic already exists");

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
            const response = await api.post<SignupResponse>("/api/v1/auth/signup/clinic-admin", {
                clinic_name: formData.clinicName,
                email: formData.email,
                first_name: formData.firstName,
                last_name: formData.lastName,
                password: formData.password,
                specialty: formData.specialty,
                type1_npi: formData.type1Npi || undefined,
                type2_npi: formData.type2Npi || undefined,
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
                    <h1 className="max-w-md text-5xl font-bold leading-tight">Launch your clinic workspace in one secure step.</h1>
                    <p className="max-w-lg text-lg text-gray-300">
                        Create the clinic, register the first admin account, and start onboarding your care team from the dashboard.
                    </p>
                </div>
                <p className="text-sm text-gray-400">No manual SQL promotion required for the first clinic admin.</p>
            </div>

            <div className="flex flex-1 items-center justify-center px-6 py-12">
                <Card className="w-full max-w-xl space-y-6" padding="lg">
                    <div className="space-y-2">
                        <p className="text-sm font-medium text-blue-600">Clinic admin onboarding</p>
                        <h2 className="text-3xl font-bold text-gray-900">Create clinic and admin account</h2>
                        <p className="text-sm text-gray-500">
                            This account becomes the first clinic admin and can invite additional clinicians.
                        </p>
                    </div>

                    <form className="grid gap-4 md:grid-cols-2" onSubmit={handleSubmit}>
                        <div className="md:col-span-2">
                            <Input label="Clinic name" onChange={(event) => updateField("clinicName", event.target.value)} value={formData.clinicName} />
                        </div>
                        <Input label="First name" onChange={(event) => updateField("firstName", event.target.value)} value={formData.firstName} />
                        <Input label="Last name" onChange={(event) => updateField("lastName", event.target.value)} value={formData.lastName} />
                        <Input label="Email" onChange={(event) => updateField("email", event.target.value)} type="email" value={formData.email} />
                        <Input label="Specialty" onChange={(event) => updateField("specialty", event.target.value)} value={formData.specialty} />
                        <div className="space-y-1">
                            <div className="flex items-center gap-2 text-sm font-medium text-gray-700">
                                <span>Type 1 NPI (optional)</span>
                                <InfoIcon text="Type 1 NPI is for the admin clinician (individual provider NPI)." />
                            </div>
                            <Input aria-label="Type 1 NPI (optional)" onChange={(event) => updateField("type1Npi", event.target.value)} value={formData.type1Npi} />
                        </div>
                        <div className="space-y-1">
                            <div className="flex items-center gap-2 text-sm font-medium text-gray-700">
                                <span>Type 2 NPI (optional)</span>
                                <InfoIcon text="Type 2 NPI is for the clinic/organization (facility NPI)." />
                            </div>
                            <Input aria-label="Type 2 NPI (optional)" onChange={(event) => updateField("type2Npi", event.target.value)} value={formData.type2Npi} />
                        </div>
                        <Input label="Password" onChange={(event) => updateField("password", event.target.value)} type="password" value={formData.password} />
                        <Input
                            label="Confirm password"
                            onChange={(event) => updateField("confirmPassword", event.target.value)}
                            type="password"
                            value={formData.confirmPassword}
                        />
                        {error ? <p className="text-sm text-red-600 md:col-span-2">{error}</p> : null}
                        {isClinicAlreadyExistsError ? (
                            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 md:col-span-2">
                                <p className="font-semibold">This clinic is already provisioned.</p>
                                <p className="mt-1">
                                    Use an existing clinician login for this clinic, then ask a current clinic admin to grant admin access.
                                </p>
                                <Link className="mt-2 inline-block font-semibold text-amber-900 underline" href="/login">
                                    Go to clinician sign in
                                </Link>
                            </div>
                        ) : null}
                        <div className="md:col-span-2">
                            <Button disabled={submitting} fullWidth type="submit">
                                {submitting ? "Creating clinic..." : "Create clinic admin account"}
                            </Button>
                        </div>
                    </form>

                    <div className="text-sm text-gray-500">
                        Already have clinic access?{" "}
                        <Link className="font-medium text-blue-600" href="/login">
                            Sign in
                        </Link>
                    </div>
                </Card>
            </div>
        </div>
    );
}
