"use client";

import Link from "next/link";
import Image from "next/image";
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
import { AuthEntryLanguage, useAuthEntryLocale } from "@/components/features/auth-entry-language";
import { getAuthEntryCopy, getSignupErrorKey } from "@/content/auth-entry-copy";

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
    const { locale, setLocale } = useAuthEntryLocale();
    const copy = getAuthEntryCopy(locale);
    const [submitting, setSubmitting] = useState(false);
    const dispatch = useDispatch<AppDispatch>();
    const [errorKey, setErrorKey] = useState<"mismatch" | "wrongSignup" | "accountExists" | "failure" | null>(null);
    const [passwordVisible, setPasswordVisible] = useState(false);
    const [confirmPasswordVisible, setConfirmPasswordVisible] = useState(false);
    const [formData, setFormData] = useState({
        confirmPassword: "",
        dateOfBirth: "",
        email: "",
        firstName: "",
        lastName: "",
        password: "",
    });

    async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (submitting) return;
        setErrorKey(null);

        if (formData.password !== formData.confirmPassword) {
            setErrorKey("mismatch");
            return;
        }

        setSubmitting(true);
        try {
            const response = await api.post<SignupResponse>("/api/v1/auth/signup/patient", {
                date_of_birth: formData.dateOfBirth,
                email: formData.email,
                first_name: formData.firstName,
                last_name: formData.lastName,
                password: formData.password,
            });

            if (response.user.role !== PortalUserRole.PATIENT) {
                setErrorKey("wrongSignup");
                return;
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
            router.replace("/onboarding?lang=" + locale);
        } catch (submissionError) {
            setErrorKey(getSignupErrorKey(submissionError));
        } finally {
            setSubmitting(false);
        }
    }

    function updateField(field: keyof typeof formData, value: string) {
        setFormData((current) => ({ ...current, [field]: value }));
    }

    return (
        <div className="app-shell patient-page min-h-dvh pb-10" lang={locale}>
            <AuthEntryLanguage locale={locale} onChange={setLocale} />
            <div className="relative overflow-hidden rounded-b-[38px] bg-[#147465] px-6 pt-14 pb-10 text-white shadow-sm">
                <div className="absolute -top-16 -right-14 h-52 w-52 rounded-full bg-white/12" />
                <div className="absolute -bottom-20 left-5 h-56 w-56 rounded-full bg-[#d8aa57]/18" />
                <div className="relative">
                    <div className="mb-8 flex h-16 w-16 items-center justify-center rounded-[26px] bg-white/20 p-2 ring-1 ring-white/25">
                        <Image alt="" height={52} priority src="/brand/icon.svg" width={52} />
                    </div>
                    <p className="text-xs font-black uppercase tracking-[0.24em] text-white">{copy.signup}</p>
                    <h1 className="mt-3 text-[2.35rem] font-black leading-none tracking-[-0.04em]">{copy.join}</h1>
                    <p className="mt-4 max-w-sm text-base leading-7 text-white">
                        {copy.signupIntro}
                    </p>
                </div>
            </div>

            <div className="patient-stack -mt-5 space-y-5 px-5">
                <Card className="shadow-sm" padding="lg">
                    <div className="mb-5 rounded-2xl border border-[#b6d9d2] bg-[#e6f4f1] px-4 py-3 text-sm font-medium text-[#147465]">
                        {copy.inviteLater}
                    </div>
                    <form className="space-y-5" onSubmit={handleSubmit}>
                        <Input label={copy.firstName} required autoComplete="given-name" onChange={(event) => updateField("firstName", event.target.value)} value={formData.firstName} />
                        <Input label={copy.lastName} required autoComplete="family-name" onChange={(event) => updateField("lastName", event.target.value)} value={formData.lastName} />
                        <Input label={copy.dateOfBirth} required autoComplete="bday" onChange={(event) => updateField("dateOfBirth", event.target.value)} type="date" value={formData.dateOfBirth} />
                        <Input label={copy.email} required autoComplete="email" onChange={(event) => updateField("email", event.target.value)} type="email" value={formData.email} />
                        <Input
                            label={copy.password} required autoComplete="new-password"
                            onChange={(event) => updateField("password", event.target.value)}
                            trailingAction={
                                <button
                                    aria-label={passwordVisible ? copy.hidePassword : copy.showPassword}
                                    className="inline-flex h-11 w-11 items-center justify-center rounded-lg focus-visible:outline-2 focus-visible:outline-[#147465] text-[#5b6b83] hover:bg-[#fffaf4] hover:text-[#17233a]"
                                    onClick={() => setPasswordVisible((current) => !current)}
                                    type="button"
                                >
                                    {passwordVisible ? <FiEyeOff aria-hidden className="h-5 w-5" /> : <FiEye aria-hidden className="h-5 w-5" />}
                                </button>
                            }
                            type={passwordVisible ? "text" : "password"}
                            value={formData.password}
                        />
                        <Input
                            label={copy.confirmPassword} required autoComplete="new-password"
                            onChange={(event) => updateField("confirmPassword", event.target.value)}
                            trailingAction={
                                <button
                                    aria-label={confirmPasswordVisible ? copy.hideConfirm : copy.showConfirm}
                                    className="inline-flex h-11 w-11 items-center justify-center rounded-lg focus-visible:outline-2 focus-visible:outline-[#147465] text-[#5b6b83] hover:bg-[#fffaf4] hover:text-[#17233a]"
                                    onClick={() => setConfirmPasswordVisible((current) => !current)}
                                    type="button"
                                >
                                    {confirmPasswordVisible ? <FiEyeOff aria-hidden className="h-5 w-5" /> : <FiEye aria-hidden className="h-5 w-5" />}
                                </button>
                            }
                            type={confirmPasswordVisible ? "text" : "password"}
                            value={formData.confirmPassword}
                        />
                        {errorKey ? <p role="alert" className="rounded-2xl bg-red-100 px-4 py-3 text-sm font-semibold text-red-800">{copy[errorKey]}</p> : null}
                        <Button disabled={submitting} fullWidth size="lg" type="submit">{submitting ? copy.creating : copy.createAccount}</Button>
                    </form>
                </Card>

                <Card className="space-y-2 bg-white" padding="md">
                    <p className="text-base text-[#5b6b83]">{copy.already}</p>
                    <Link className="inline-flex min-h-11 items-center text-base font-bold text-[#147465]" href={"/login?lang=" + locale} prefetch={false}>
                        {copy.signIn}
                    </Link>
                </Card>
            </div>
        </div>
    );
}
