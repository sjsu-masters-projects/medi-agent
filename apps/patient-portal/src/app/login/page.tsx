"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { FiEye, FiEyeOff } from "react-icons/fi";
import { useDispatch } from "react-redux";
import Image from "next/image";
import { AuthEntryButton as Button, AuthEntryInput as Input } from "@/components/features/auth-entry-presentation";
import { api } from "@/services/api";
import { writeStoredSession } from "@/services/auth-session";
import { hydrateSession, type PatientAuthSession } from "@/store/slices/auth-slice";
import type { AppDispatch } from "@/store/store";
import { PortalUserRole } from "@/types";
import { AuthEntryLanguage, useAuthEntryLocale } from "@/components/features/auth-entry-language";
import { getAuthEntryCopy } from "@/content/auth-entry-copy";
import { sanitizeReturnPath } from "../../../../../packages/shared/src/utils/return-path";

interface AuthResponse {
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
    requires_clinic_join?: boolean;
}

function LoginPageContent() {
    const router = useRouter();
    const { locale, setLocale } = useAuthEntryLocale();
    const copy = getAuthEntryCopy(locale);
    const searchParams = useSearchParams();
    const dispatch = useDispatch<AppDispatch>();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [passwordVisible, setPasswordVisible] = useState(false);
    const [errorKey, setErrorKey] = useState<"clinicianAccount" | "invalidLogin" | "failure" | null>(null);
    const [submitting, setSubmitting] = useState(false);

    const notice = (() => {
        const reason = searchParams?.get("reason") ?? "";
        if (reason === "session_expired") {
            return copy.expired;
        }
        if (reason === "unauthorized") {
            return copy.unauthorized;
        }
        if (reason === "logged_out") {
            return copy.loggedOut;
        }
        return "";
    })();

    async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setSubmitting(true);
        setErrorKey(null);

        try {
            const response = await api.post<AuthResponse>("/api/v1/auth/login", { email, password });
            if (response.user.role !== PortalUserRole.PATIENT) {
                setErrorKey("clinicianAccount");
                return;
            }
            const session: PatientAuthSession = {
                accessToken: response.tokens.access_token,
                expiresAt: response.tokens.expires_at,
                refreshToken: response.tokens.refresh_token,
                user: { ...response.user, role: PortalUserRole.PATIENT },
            };
            writeStoredSession(session);
            dispatch(hydrateSession(session));

            // The login response carries this single onboarding decision so we do not
            // make a second blocking request before the first authenticated route.
            if (response.requires_clinic_join) {
                router.replace("/profile?joinClinic=1");
            } else {
                const returnPath = sanitizeReturnPath(searchParams?.get("return_path"));
                if (returnPath && !returnPath.startsWith("/login")) {
                    router.replace(returnPath);
                } else {
                    router.replace("/today");
                }
            }
        } catch (submissionError) {
            setErrorKey(typeof submissionError === "object" && submissionError !== null && "status" in submissionError && submissionError.status === 401 ? "invalidLogin" : "failure");
        } finally {
            setSubmitting(false);
        }
    }

    return (
        <div className="patient-page patient-entry mx-auto flex min-h-dvh w-full max-w-[480px] flex-col bg-background pb-[calc(env(safe-area-inset-bottom)+24px)]" lang={locale}>
            <AuthEntryLanguage locale={locale} onChange={setLocale} />
            <header className="px-6 pt-6 pb-6">
                <Image alt="" className="mb-5 h-16 w-16 drop-shadow-[0_12px_18px_rgba(20,116,101,0.25)]" height={64} priority src="/brand/icon.svg" width={64} />
                <p className="font-mono text-xs uppercase tracking-[.06em] text-brand">MediAgent Care</p>
                <h1 className="mt-2 text-[32px] font-semibold leading-tight text-ink">{copy.welcome}</h1>
                <p className="mt-2 text-base leading-relaxed text-muted">
                    {copy.loginIntro}
                </p>
            </header>

            <div className="patient-stack flex flex-1 flex-col gap-6 px-6">
                    <form className="space-y-5" onSubmit={handleSubmit}>
                        <div className="sr-only">
                            <h2 className="text-[17px] font-semibold text-ink">{copy.signInHeading}</h2>
                            <p className="mt-1 text-sm text-muted">
                                {copy.signInIntro}
                            </p>
                        </div>
                        <Input
                            autoComplete="email"
                            label={copy.email} required
                            onChange={(event) => setEmail(event.target.value)}
                            type="email"
                            value={email}
                        />
                        <Input
                            autoComplete="current-password"
                            label={copy.password} required
                            onChange={(event) => setPassword(event.target.value)}
                            trailingAction={
                                <button
                                    aria-label={passwordVisible ? copy.hidePassword : copy.showPassword}
                                    className="inline-flex h-11 w-11 items-center justify-center rounded-xl text-muted hover:text-ink"
                                    onClick={() => setPasswordVisible((current) => !current)}
                                    type="button"
                                >
                                    {passwordVisible ? <FiEyeOff aria-hidden className="h-5 w-5" /> : <FiEye aria-hidden className="h-5 w-5" />}
                                </button>
                            }
                            type={passwordVisible ? "text" : "password"}
                            value={password}
                        />
                        {notice ? <p role="status" className="rounded-2xl bg-brand-tint px-4 py-3 text-sm font-medium text-brand-ink">{notice}</p> : null}
                        {errorKey ? <p role="alert" className="rounded-2xl bg-danger-tint px-4 py-3 text-sm font-semibold text-danger-ink">{copy[errorKey]}</p> : null}
                        <Button disabled={submitting} type="submit">
                            {submitting ? copy.signingIn : copy.signIn}
                        </Button>
                    </form>
                <section className="mt-auto flex flex-wrap items-center justify-between gap-3 rounded-group bg-surface p-4 shadow-[0_1px_0_rgba(16,32,43,.04)]">
                    <div className="min-w-0 flex-1 basis-40">
                        <p className="text-[15px] font-semibold text-ink">{copy.newHere}</p>
                        <p className="mt-1 text-sm text-muted">{copy.newIntro}</p>
                    </div>
                    <Link className="inline-flex min-h-11 min-w-11 items-center rounded-xl bg-brand-tint px-3 text-sm font-semibold text-brand" href={"/signup?lang=" + locale} prefetch={false}>
                        {copy.createOne}
                    </Link>
                </section>
            </div>
        </div>
    );
}

export default function LoginPage() {
    return (
        <Suspense fallback={null}>
            <LoginPageContent />
        </Suspense>
    );
}
