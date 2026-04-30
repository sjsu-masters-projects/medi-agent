"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { FiEye, FiEyeOff } from "react-icons/fi";
import { useDispatch } from "react-redux";
import { Button, Card, Input } from "@/components/ui";
import { api } from "@/services/api";
import { writeStoredSession } from "@/services/auth-session";
import { hydrateSession, type PatientAuthSession } from "@/store/slices/auth-slice";
import { setOnboardingProfile } from "@/store/slices/onboarding-slice";
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

export default function SignupPage() {
    const router = useRouter();
    const dispatch = useDispatch<AppDispatch>();
    const [error, setError] = useState("");
    const [passwordVisible, setPasswordVisible] = useState(false);
    const [confirmPasswordVisible, setConfirmPasswordVisible] = useState(false);
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

            if (response.user.role !== PortalUserRole.PATIENT) {
                throw new Error("Signup did not create a patient account.");
            }

            const session: PatientAuthSession = {
                accessToken: response.tokens.access_token,
                expiresAt: response.tokens.expires_at,
                refreshToken: response.tokens.refresh_token,
                user: { ...response.user, role: PortalUserRole.PATIENT },
            };
            writeStoredSession(session);
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
        <div className="app-shell patient-page min-h-dvh pb-10">
            <div className="relative overflow-hidden rounded-b-[38px] bg-[#147465] px-6 pt-14 pb-10 text-white shadow-[0_24px_70px_rgba(20,116,101,0.25)]">
                <div className="absolute -top-16 -right-14 h-52 w-52 rounded-full bg-white/12" />
                <div className="absolute -bottom-20 left-5 h-56 w-56 rounded-full bg-[#d8aa57]/18" />
                <div className="relative">
                    <p className="text-xs font-black uppercase tracking-[0.24em] text-white/72">Patient signup</p>
                    <h1 className="mt-3 text-[2.35rem] font-black leading-none tracking-[-0.04em]">Join MediAgent</h1>
                    <p className="mt-4 max-w-sm text-base leading-7 text-white/82">
                        Set up your account to track medications, symptoms, and care updates in one place.
                    </p>
                </div>
            </div>

            <div className="patient-stack -mt-5 space-y-5 px-5">
                <Card className="shadow-[0_24px_70px_rgba(42,58,84,0.14)]" padding="lg">
                    <div className="mb-5 flex items-center gap-2">
                        <span className="h-2.5 w-12 rounded-full bg-[#147465]" />
                        <span className="h-2.5 w-12 rounded-full bg-[#dbe7df]" />
                        <span className="h-2.5 w-12 rounded-full bg-[#dbe7df]" />
                    </div>
                    <div className="mb-5 rounded-2xl border border-[#b6d9d2] bg-[#e6f4f1] px-4 py-3 text-sm font-medium text-[#147465]">
                        Clinic invite code is entered on onboarding step 4 (Connect your care team) after account creation.
                    </div>
                    <form className="space-y-5" onSubmit={handleSubmit}>
                        <Input label="First name" onChange={(event) => updateField("firstName", event.target.value)} value={formData.firstName} />
                        <Input label="Last name" onChange={(event) => updateField("lastName", event.target.value)} value={formData.lastName} />
                        <Input label="Date of birth" onChange={(event) => updateField("dateOfBirth", event.target.value)} type="date" value={formData.dateOfBirth} />
                        <Input label="Email" onChange={(event) => updateField("email", event.target.value)} type="email" value={formData.email} />
                        <Input
                            label="Password"
                            onChange={(event) => updateField("password", event.target.value)}
                            trailingAction={
                                <button
                                    aria-label={passwordVisible ? "Hide password" : "Show password"}
                                    className="inline-flex h-9 w-9 items-center justify-center rounded-xl text-[#64748b] hover:bg-[#f4f0ea] hover:text-[#17233a]"
                                    onClick={() => setPasswordVisible((current) => !current)}
                                    type="button"
                                >
                                    {passwordVisible ? <FiEyeOff className="h-5 w-5" /> : <FiEye className="h-5 w-5" />}
                                </button>
                            }
                            type={passwordVisible ? "text" : "password"}
                            value={formData.password}
                        />
                        <Input
                            label="Confirm password"
                            onChange={(event) => updateField("confirmPassword", event.target.value)}
                            trailingAction={
                                <button
                                    aria-label={confirmPasswordVisible ? "Hide confirm password" : "Show confirm password"}
                                    className="inline-flex h-9 w-9 items-center justify-center rounded-xl text-[#64748b] hover:bg-[#f4f0ea] hover:text-[#17233a]"
                                    onClick={() => setConfirmPasswordVisible((current) => !current)}
                                    type="button"
                                >
                                    {confirmPasswordVisible ? <FiEyeOff className="h-5 w-5" /> : <FiEye className="h-5 w-5" />}
                                </button>
                            }
                            type={confirmPasswordVisible ? "text" : "password"}
                            value={formData.confirmPassword}
                        />
                        {error ? <p className="rounded-2xl bg-[#fff2ef] px-4 py-3 text-sm font-semibold text-[#b94032]">{error}</p> : null}
                        <Button fullWidth size="lg" type="submit">Create account</Button>
                    </form>
                </Card>

                <Card className="space-y-2 bg-white/76" padding="md">
                    <p className="text-base text-[#5b6b83]">Already have an account?</p>
                    <Link className="inline-flex min-h-11 items-center text-base font-bold text-[#147465]" href="/login">
                        Sign in
                    </Link>
                </Card>
            </div>
        </div>
    );
}
