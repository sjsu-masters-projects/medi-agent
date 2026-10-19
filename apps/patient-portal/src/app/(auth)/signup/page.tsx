"use client";

import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { FiEye, FiEyeOff } from "react-icons/fi";
import { useDispatch } from "react-redux";
import { AuthEntryButton as Button, AuthEntryInput as Input } from "@/components/features/auth-entry-presentation";
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
            writeStoredSession(session, { signIn: true });
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
        <div className="patient-page patient-entry mx-auto flex min-h-dvh w-full max-w-[480px] flex-col bg-background pb-[calc(env(safe-area-inset-bottom)+24px)]" lang={locale}>
            <AuthEntryLanguage locale={locale} onChange={setLocale} />
            <header className="px-6 pt-6 pb-6">
                <Image alt="" className="mb-5 h-16 w-16 drop-shadow-[0_12px_18px_rgba(20,116,101,0.25)]" height={64} priority src="/brand/icon.svg" width={64} />
                <p className="font-mono text-xs uppercase tracking-[.06em] text-brand">{copy.signup}</p>
                <h1 className="mt-2 text-[32px] font-semibold leading-tight text-ink">{copy.join}</h1>
                <p className="mt-2 text-base leading-relaxed text-muted">
                    {copy.signupIntro}
                </p>
            </header>

            <div className="patient-stack flex flex-1 flex-col gap-6 px-6">
                <div>
                    <div className="mb-5 rounded-2xl border border-line-strong bg-surface-2 px-4 py-3 text-sm font-medium text-ink-2">
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
                                    className="inline-flex h-11 w-11 items-center justify-center rounded-xl text-muted hover:bg-surface-2 hover:text-ink"
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
                                    className="inline-flex h-11 w-11 items-center justify-center rounded-xl text-muted hover:bg-surface-2 hover:text-ink"
                                    onClick={() => setConfirmPasswordVisible((current) => !current)}
                                    type="button"
                                >
                                    {confirmPasswordVisible ? <FiEyeOff aria-hidden className="h-5 w-5" /> : <FiEye aria-hidden className="h-5 w-5" />}
                                </button>
                            }
                            type={confirmPasswordVisible ? "text" : "password"}
                            value={formData.confirmPassword}
                        />
                        {errorKey ? <p role="alert" className="rounded-2xl bg-danger-tint px-4 py-3 text-sm font-semibold text-danger-ink">{copy[errorKey]}</p> : null}
                        <Button disabled={submitting} type="submit">{submitting ? copy.creating : copy.createAccount}</Button>
                    </form>
                </div>

                <section className="mt-auto flex flex-wrap items-center justify-between gap-3 rounded-group border border-line bg-surface p-4">
                    <p className="text-sm text-muted">{copy.already}</p>
                    <Link className="inline-flex min-h-11 min-w-11 items-center rounded-xl bg-brand-tint px-3 text-sm font-semibold text-brand" href={"/login?lang=" + locale} prefetch={false}>
                        {copy.signIn}
                    </Link>
                </section>
            </div>
        </div>
    );
}
