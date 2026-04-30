"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { FiEye, FiEyeOff } from "react-icons/fi";
import { useDispatch } from "react-redux";
import { Button, Card, Input } from "@/components/ui";
import { api } from "@/services/api";
import { writeStoredSession } from "@/services/auth-session";
import { hydrateSession, type PatientAuthSession } from "@/store/slices/auth-slice";
import type { AppDispatch } from "@/store/store";
import { PortalUserRole } from "@/types";
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
}

interface CareTeamMembership {
    id: string;
}

function LoginPageContent() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const dispatch = useDispatch<AppDispatch>();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [passwordVisible, setPasswordVisible] = useState(false);
    const [error, setError] = useState("");
    const [submitting, setSubmitting] = useState(false);

    const notice = (() => {
        const reason = searchParams?.get("reason") ?? "";
        if (reason === "session_expired") {
            return "Your session expired. Please sign in again.";
        }
        if (reason === "unauthorized") {
            return "You no longer have access to this portal. Please sign in again.";
        }
        if (reason === "logged_out") {
            return "You have been logged out.";
        }
        return "";
    })();

    async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setSubmitting(true);
        setError("");

        try {
            const response = await api.post<AuthResponse>("/api/v1/auth/login", { email, password });
            if (response.user.role !== PortalUserRole.PATIENT) {
                throw new Error("This login belongs to a clinician account.");
            }
            const session: PatientAuthSession = {
                accessToken: response.tokens.access_token,
                expiresAt: response.tokens.expires_at,
                refreshToken: response.tokens.refresh_token,
                user: { ...response.user, role: PortalUserRole.PATIENT },
            };
            writeStoredSession(session);
            dispatch(hydrateSession(session));

            const careTeams = await api.get<CareTeamMembership[]>("/api/v1/patients/me/care-team", {
                token: session.accessToken,
            });

            if (careTeams.length === 0) {
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
            setError((submissionError as Error).message);
        } finally {
            setSubmitting(false);
        }
    }

    return (
        <div className="app-shell patient-page min-h-dvh pb-10">
            <div className="relative overflow-hidden rounded-b-[38px] bg-[#147465] px-6 pt-14 pb-10 text-white shadow-[0_24px_70px_rgba(20,116,101,0.25)]">
                <div className="absolute -top-16 -right-14 h-52 w-52 rounded-full bg-white/12" />
                <div className="absolute -bottom-20 left-5 h-56 w-56 rounded-full bg-[#d8aa57]/18" />
                <div className="relative">
                    <div className="mb-8 flex h-14 w-14 items-center justify-center rounded-[24px] bg-white/16 text-lg font-black tracking-tight ring-1 ring-white/25">
                        M
                    </div>
                    <p className="text-xs font-black uppercase tracking-[0.24em] text-white/72">MediAgent</p>
                    <h1 className="mt-3 text-[2.45rem] font-black leading-[0.98] tracking-[-0.04em]">Welcome back</h1>
                    <p className="mt-4 max-w-sm text-base leading-7 text-white/82">
                        Your calm space for today&apos;s care plan, records, and messages from your care team.
                    </p>
                </div>
                <div className="relative mt-6 inline-flex rounded-full bg-white/15 px-4 py-2 text-sm font-bold text-white ring-1 ring-white/20">
                    Patient portal
                </div>
            </div>

            <div className="patient-stack -mt-5 space-y-5 px-5">
                <Card className="shadow-[0_24px_70px_rgba(42,58,84,0.14)]" padding="lg">
                    <form className="space-y-5" onSubmit={handleSubmit}>
                        <div>
                            <h2 className="text-xl font-black text-[#17233a]">Sign in securely</h2>
                            <p className="mt-1 text-base leading-7 text-[#64748b]">
                                We&apos;ll keep you in the right patient workspace.
                            </p>
                        </div>
                        <Input label="Email address" onChange={(event) => setEmail(event.target.value)} type="email" value={email} />
                        <Input
                            label="Password"
                            onChange={(event) => setPassword(event.target.value)}
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
                            value={password}
                        />
                        {notice ? <p className="rounded-2xl bg-[#e6f4f1] px-4 py-3 text-sm font-medium text-[#147465]">{notice}</p> : null}
                        {error ? <p className="rounded-2xl bg-[#fff2ef] px-4 py-3 text-sm font-semibold text-[#b94032]">{error}</p> : null}
                        <Button disabled={submitting} fullWidth size="lg" type="submit">
                            {submitting ? "Signing in..." : "Sign in"}
                        </Button>
                    </form>
                </Card>

                <Card className="space-y-3 border-[#b6d9d2] bg-[#e6f4f1]" padding="md">
                    <p className="text-base font-bold text-[#17233a]">New to MediAgent?</p>
                    <p className="text-base leading-7 text-[#5b6b83]">Create your account to get medication reminders and clinician updates.</p>
                    <Link className="inline-flex min-h-11 items-center text-base font-bold text-[#147465]" href="/signup">
                        Create one
                    </Link>
                </Card>
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
