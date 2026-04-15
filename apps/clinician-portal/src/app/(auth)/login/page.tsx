"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useDispatch } from "react-redux";
import { Button, Card, Input } from "@/components/ui";
import { api } from "@/services/api";
import { writeStoredSession } from "@/services/auth-session";
import {
    clearStoredClinicContext,
    readStoredClinicContext,
    writeStoredClinicContext,
    type ClinicContext,
} from "@/services/clinic-context";
import { hydrateSession, type ClinicianAuthSession } from "@/store/slices/auth-slice";
import type { AppDispatch } from "@/store/store";

interface LoginResponse {
    tokens: {
        access_token: string;
        expires_at: number;
        refresh_token: string;
    };
    mfa_factors?: Array<{
        id: string;
        friendly_name: string | null;
    }>;
    mfa_required?: boolean;
    user: {
        email: string;
        id: string;
        role: "patient" | "clinician";
    };
}

interface MFAVerifyResponse {
    access_token: string;
    expires_at: number;
    refresh_token: string;
}

interface PendingMFALogin {
    factorId: string;
    friendlyName: string;
    session: ClinicianAuthSession;
}

interface ClinicResolveResponse {
    clinic_code: string;
    clinic_id: string;
    clinic_name: string;
    status: "active" | "suspended";
}

type LoginStage = "verify" | "choose" | "login";

export default function ClinicianLoginPage() {
    const router = useRouter();
    const dispatch = useDispatch<AppDispatch>();
    const [stage, setStage] = useState<LoginStage>("verify");
    const [clinicCode, setClinicCode] = useState("");
    const [clinicContext, setClinicContext] = useState<ClinicContext | null>(null);
    const [code, setCode] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [clinicCodeError, setClinicCodeError] = useState("");
    const [pendingMFA, setPendingMFA] = useState<PendingMFALogin | null>(null);
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        const stored = readStoredClinicContext();
        if (!stored) {
            return;
        }

        setClinicCode(stored.clinicCode);
        setClinicContext(stored);
        setStage("choose");
    }, []);

    async function handleVerifyClinicCode(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setError("");
        setClinicCodeError("");

        const normalizedClinicCode = clinicCode.trim().toUpperCase();
        setClinicCode(normalizedClinicCode);

        if (!normalizedClinicCode) {
            setClinicCodeError("Clinic code is required.");
            return;
        }

        if (normalizedClinicCode.length < 6) {
            setClinicCodeError("Clinic code should have at least 6 characters.");
            return;
        }

        setSubmitting(true);

        try {
            const resolved = await api.post<ClinicResolveResponse>("/api/v1/clinics/resolve-code", {
                clinic_code: normalizedClinicCode,
            });

            const context: ClinicContext = {
                clinicCode: resolved.clinic_code,
                clinicId: resolved.clinic_id,
                clinicName: resolved.clinic_name,
                status: resolved.status,
            };

            writeStoredClinicContext(context);
            setClinicCode(resolved.clinic_code);
            setClinicContext(context);
            setStage("choose");
        } catch (submissionError) {
            setClinicCodeError((submissionError as Error).message);
        } finally {
            setSubmitting(false);
        }
    }

    async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setSubmitting(true);
        setError("");

        if (!clinicContext) {
            setError("Enter and verify your clinic code first.");
            setSubmitting(false);
            return;
        }

        try {
            const response = await api.post<LoginResponse>("/api/v1/auth/login", {
                clinic_code: clinicContext.clinicCode,
                email,
                password,
            });
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

            if (response.mfa_required) {
                const factor = response.mfa_factors?.[0];
                if (!factor) {
                    throw new Error("MFA is required but no verified factor is available.");
                }
                setPendingMFA({
                    factorId: factor.id,
                    friendlyName: factor.friendly_name ?? "Authenticator",
                    session,
                });
                setCode("");
                return;
            }

            writeStoredSession(session);
            dispatch(hydrateSession(session));
            router.replace("/dashboard");
        } catch (submissionError) {
            setError((submissionError as Error).message);
        } finally {
            setSubmitting(false);
        }
    }

    async function handleMFAVerify(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!pendingMFA) {
            return;
        }

        setSubmitting(true);
        setError("");

        try {
            const response = await api.post<MFAVerifyResponse>(
                "/api/v1/auth/mfa/verify",
                { factor_id: pendingMFA.factorId, code },
                {
                    headers: { "X-Refresh-Token": pendingMFA.session.refreshToken },
                    token: pendingMFA.session.accessToken,
                },
            );

            const session: ClinicianAuthSession = {
                accessToken: response.access_token,
                expiresAt: response.expires_at,
                refreshToken: response.refresh_token,
                user: pendingMFA.session.user,
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

    function useDifferentClinicCode() {
        clearStoredClinicContext();
        setClinicContext(null);
        setClinicCode("");
        setEmail("");
        setPassword("");
        setPendingMFA(null);
        setCode("");
        setError("");
        setStage("verify");
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
                        <p className="text-sm font-medium text-blue-600">
                            {pendingMFA ? "Clinical Intelligence Platform" : "Clinic access"}
                        </p>
                        <h2 className="text-3xl font-bold text-gray-900">
                            {pendingMFA
                                ? "Verify MFA"
                                : stage === "verify"
                                  ? "Enter clinic code"
                                  : stage === "choose"
                                    ? "Choose sign-in path"
                                    : "Sign in"}
                        </h2>
                        <p className="text-sm text-gray-500">
                            {pendingMFA
                                ? `Enter the 6-digit code from ${pendingMFA.friendlyName}.`
                                : stage === "verify"
                                  ? "Verify your clinic workspace before continuing to login or registration."
                                  : stage === "choose"
                                    ? "Clinic verified. Continue to sign in with your account or join this clinic."
                                    : "Access your dashboard, roster, and active alerts."}
                        </p>
                    </div>

                    {pendingMFA ? (
                        <form className="space-y-4" onSubmit={handleMFAVerify}>
                            <Input
                                autoComplete="one-time-code"
                                inputMode="numeric"
                                label="6-digit code"
                                maxLength={6}
                                onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
                                placeholder="000000"
                                value={code}
                            />
                            {error ? <p className="text-sm text-red-600">{error}</p> : null}
                            <Button disabled={submitting || code.length !== 6} fullWidth type="submit">
                                {submitting ? "Verifying..." : "Verify and continue"}
                            </Button>
                            <button
                                className="w-full text-sm text-gray-500 underline"
                                onClick={() => {
                                    setPendingMFA(null);
                                    setCode("");
                                    setError("");
                                    setStage("login");
                                }}
                                type="button"
                            >
                                Use a different account
                            </button>
                        </form>
                    ) : null}

                    {!pendingMFA && stage === "verify" ? (
                        <form className="space-y-4" onSubmit={handleVerifyClinicCode}>
                            <Input
                                error={clinicCodeError}
                                label="Clinic code"
                                onChange={(event) => {
                                    setClinicCode(event.target.value.toUpperCase());
                                    if (clinicCodeError) {
                                        setClinicCodeError("");
                                    }
                                }}
                                value={clinicCode}
                            />
                            <Button disabled={submitting} fullWidth type="submit">
                                {submitting ? "Verifying..." : "Verify clinic code"}
                            </Button>
                            <Link className="block text-center text-sm font-medium text-blue-600" href="/signup/admin">
                                Start a new clinic workspace (creates Clinic Admin)
                            </Link>
                        </form>
                    ) : null}

                    {!pendingMFA && stage === "choose" && clinicContext ? (
                        <div className="space-y-4">
                            <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                                <p className="font-semibold">Clinic verified: {clinicContext.clinicName}</p>
                                <p className="mt-1">Code: {clinicContext.clinicCode}</p>
                            </div>
                            {error ? <p className="text-sm text-red-600">{error}</p> : null}
                            <Button fullWidth onClick={() => setStage("login")} type="button">
                                I already have an account
                            </Button>
                            <Link className="block" href="/signup">
                                <Button fullWidth type="button" variant="secondary">
                                    Join this clinic (Provider / Nurse)
                                </Button>
                            </Link>
                            <button
                                className="w-full text-sm text-slate-500 underline"
                                onClick={useDifferentClinicCode}
                                type="button"
                            >
                                Use a different clinic code
                            </button>
                        </div>
                    ) : null}

                    {!pendingMFA && stage === "login" && clinicContext ? (
                        <>
                            <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                                Signing into clinic: <span className="font-semibold">{clinicContext.clinicName}</span>
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
                                <button className="text-blue-600" onClick={() => setStage("choose")} type="button">
                                    Back
                                </button>
                                <span className="text-gray-400">Forgot password?</span>
                            </div>
                        </>
                    ) : null}
                </Card>
            </div>
        </div>
    );
}
