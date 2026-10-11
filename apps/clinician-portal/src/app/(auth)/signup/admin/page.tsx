"use client";

import Link from "next/link";
import { AuthShell } from "@/components/features/auth-shell";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useDispatch } from "react-redux";
import { Button, Input } from "@/components/ui";
import { api } from "@/services/api";
import { writeStoredSession } from "@/services/auth-session";
import { hydrateSession, type ClinicianAuthSession } from "@/store/slices/auth-slice";
import type { AppDispatch } from "@/store/store";
import { PortalUserRole } from "@/types";

interface SignupResponse {
    tokens: {
        access_token: string;
        expires_at: number;
        refresh_token: string;
    };
    user: {
        email: string;
        id: string;
        role: typeof PortalUserRole[keyof typeof PortalUserRole];
    };
}

function InfoIcon({ text }: { text: string }) {
    return (
        <span className="group relative inline-flex items-center">
            <span
                aria-label={text}
                className="inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-line-strong text-[10px] font-semibold text-muted"
                role="img"
                tabIndex={0}
            >
                i
            </span>
            <span
                className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 w-56 -translate-x-1/2 rounded-lg bg-rail px-2.5 py-1.5 text-xs font-normal text-rail-ink opacity-0 shadow-[var(--shadow-pop)] transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100"
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

            if (response.user.role !== PortalUserRole.CLINICIAN) {
                throw new Error("This signup produced a non-clinician account.");
            }

            const session: ClinicianAuthSession = {
                accessToken: response.tokens.access_token,
                expiresAt: response.tokens.expires_at,
                refreshToken: response.tokens.refresh_token,
                user: {
                    email: response.user.email,
                    id: response.user.id,
                    role: PortalUserRole.CLINICIAN,
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
        <AuthShell
            headline="Launch your clinic workspace in one secure step."
            subcopy="Create the clinic, register the first admin account, and start onboarding your care team from the dashboard."
            footer="Your account will manage clinic settings and team access."
            wide
        >
                <div className="space-y-6">
                    <div className="space-y-2">
                        <p className="font-mono text-[11px] uppercase tracking-[0.06em] text-primary">Clinic admin onboarding</p>
                        <h2 className="text-[26px] font-semibold leading-tight tracking-[-0.02em] text-ink">Create clinic and admin account</h2>
                        <p className="text-sm text-muted">
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
                            <div className="flex items-center gap-2 text-[13px] font-medium text-ink-2">
                                <span>Type 1 NPI (optional)</span>
                                <InfoIcon text="Type 1 NPI is for the admin clinician (individual provider NPI)." />
                            </div>
                            <Input aria-label="Type 1 NPI (optional)" onChange={(event) => updateField("type1Npi", event.target.value)} value={formData.type1Npi} />
                        </div>
                        <div className="space-y-1">
                            <div className="flex items-center gap-2 text-[13px] font-medium text-ink-2">
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
                        {error ? <p role="alert" className="rounded-lg bg-risk-soft px-3 py-2 text-sm text-risk-ink md:col-span-2">{error}</p> : null}
                        {isClinicAlreadyExistsError ? (
                            <div className="rounded-xl border border-warn-line bg-warn-soft px-4 py-3 text-sm text-warn-ink md:col-span-2">
                                <p className="font-semibold">This clinic is already provisioned.</p>
                                <p className="mt-1">
                                    Use an existing clinician login for this clinic, then ask a current clinic admin to grant admin access.
                                </p>
                                <Link className="mt-2 inline-block font-semibold text-warn-ink underline" href="/login">
                                    Go to clinician sign in
                                </Link>
                            </div>
                        ) : null}
                        <div className="md:col-span-2">
                            <Button disabled={submitting} fullWidth size="lg" type="submit">
                                {submitting ? "Creating clinic..." : "Create clinic admin account"}
                            </Button>
                        </div>
                    </form>

                    <div className="text-sm text-muted">
                        Already have clinic access?{" "}
                        <Link className="font-medium text-primary hover:underline" href="/login">
                            Sign in
                        </Link>
                    </div>
                </div>
        </AuthShell>
    );
}
