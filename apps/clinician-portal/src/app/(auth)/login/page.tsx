"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { useDispatch } from "react-redux";
import { Button, Card, Input } from "@/components/ui";
import { api } from "@/services/api";
import { writeStoredSession } from "@/services/auth-session";
import { hydrateSession, type ClinicianAuthSession } from "@/store/slices/auth-slice";
import type { AppDispatch } from "@/store/store";

interface LoginResponse {
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

export default function ClinicianLoginPage() {
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
            const response = await api.post<LoginResponse>("/api/v1/auth/login", { email, password });
            if (response.user.role !== "clinician") {
                throw new Error("This login belongs to a patient account.");
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
        } finally {
            setSubmitting(false);
        }
    }

    return (
        <div className="flex min-h-screen bg-gray-50">
            <div className="hidden w-1/2 bg-gray-900 px-12 py-16 text-white lg:flex lg:flex-col lg:justify-between">
                <div className="space-y-4">
                    <p className="text-sm font-medium uppercase tracking-[0.3em] text-blue-300">MediAgent Pro</p>
                    <h1 className="max-w-md text-5xl font-bold leading-tight">Clinical intelligence for the entire patient panel.</h1>
                    <p className="max-w-lg text-lg text-gray-300">
                        Surface high-risk adherence issues, coordinate shared care, and act on MedWatch drafts from one dashboard.
                    </p>
                </div>
                <p className="text-sm text-gray-400">Built for care teams managing proactive, AI-assisted follow-up.</p>
            </div>

            <div className="flex flex-1 items-center justify-center px-6 py-12">
                <Card className="w-full max-w-md space-y-6" padding="lg">
                    <div className="space-y-2">
                        <p className="text-sm font-medium text-blue-600">Clinical Intelligence Platform</p>
                        <h2 className="text-3xl font-bold text-gray-900">Sign in</h2>
                        <p className="text-sm text-gray-500">Access your dashboard, roster, and active alerts.</p>
                    </div>
                    <form className="space-y-4" onSubmit={handleSubmit}>
                        <Input label="Email" onChange={(event) => setEmail(event.target.value)} type="email" value={email} />
                        <Input label="Password" onChange={(event) => setPassword(event.target.value)} type="password" value={password} />
                        {error ? <p className="text-sm text-red-600">{error}</p> : null}
                        <Button disabled={submitting} fullWidth type="submit">
                            {submitting ? "Signing in..." : "Sign in"}
                        </Button>
                    </form>
                    <div className="flex items-center justify-between text-sm">
                        <Link className="text-blue-600" href="/signup">
                            Create clinician account
                        </Link>
                        <span className="text-gray-400">Forgot password?</span>
                    </div>
                </Card>
            </div>
        </div>
    );
}
