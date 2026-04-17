"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useDispatch } from "react-redux";
import { Button, Card, Input } from "@/components/ui";
import { api } from "@/services/api";
import { writeStoredSession } from "@/services/auth-session";
import { hydrateSession, type PatientAuthSession } from "@/store/slices/auth-slice";
import type { AppDispatch } from "@/store/store";
import { PortalUserRole } from "@/types";

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

export default function LoginPage() {
    const router = useRouter();
    const dispatch = useDispatch<AppDispatch>();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [submitting, setSubmitting] = useState(false);

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
                router.replace("/today");
            }
        } catch (submissionError) {
            setError((submissionError as Error).message);
        } finally {
            setSubmitting(false);
        }
    }

    return (
        <div className="app-shell min-h-dvh bg-gray-50 pb-10">
            <div className="rounded-b-[28px] bg-sky-700 px-5 pt-12 pb-8 text-white shadow-sm">
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-100">MediAgent</p>
                <h1 className="mt-3 text-3xl font-bold">Welcome back</h1>
                <p className="mt-2 max-w-sm text-sm text-sky-100">
                    Sign in to review today&apos;s schedule, records, and messages from your care team.
                </p>
                <div className="mt-5 inline-flex rounded-full bg-white/15 px-3 py-1 text-xs font-medium text-white">
                    Patient portal
                </div>
            </div>

            <div className="-mt-4 space-y-5 px-5">
                <Card className="shadow-lg shadow-slate-100" padding="lg">
                    <form className="space-y-4" onSubmit={handleSubmit}>
                        <Input label="Email address" onChange={(event) => setEmail(event.target.value)} type="email" value={email} />
                        <Input label="Password" onChange={(event) => setPassword(event.target.value)} type="password" value={password} />
                        {error ? <p className="text-sm text-red-600">{error}</p> : null}
                        <Button disabled={submitting} fullWidth type="submit">
                            {submitting ? "Signing in..." : "Sign in"}
                        </Button>
                    </form>
                </Card>

                <Card className="space-y-3 border-sky-100 bg-sky-50" padding="md">
                    <p className="text-sm font-semibold text-slate-900">New to MediAgent?</p>
                    <p className="text-sm text-slate-600">Create your account to get medication reminders and clinician updates.</p>
                    <Link className="inline-flex text-sm font-medium text-sky-700" href="/signup">
                        Create one
                    </Link>
                </Card>
            </div>
        </div>
    );
}
