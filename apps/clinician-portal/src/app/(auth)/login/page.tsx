"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useState } from "react";
import { FiEye, FiEyeOff } from "react-icons/fi";
import { useDispatch } from "react-redux";
import { Button, Card, Input } from "@/components/ui";
import { ApiClientError, api, isRetryableApiError } from "@/services/api";
import { writeStoredSession } from "@/services/auth-session";
import {
    clearStoredClinicContext,
    readStoredClinicContext,
    writeStoredClinicContext,
    type ClinicContext,
} from "@/services/clinic-context";
import { hydrateSession, type ClinicianAuthSession } from "@/store/slices/auth-slice";
import type { AppDispatch } from "@/store/store";
import { PortalUserRole } from "@/types";

interface LoginResponse {
    mfa_factors?: MFAFactorSummary[];
    mfa_required?: boolean;
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

interface MFAFactorSummary {
    friendly_name?: string | null;
    id: string;
}

interface MFAVerifyResponse {
    access_token: string;
    expires_at: number;
    refresh_token: string;
}

interface PendingMFAChallenge {
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

type LoginStage = "verify" | "choose" | "login" | "mfa";

type ApiErrorWithEnvelope = {
    error?: {
        code?: string;
    };
};

function mapClinicContext(response: ClinicResolveResponse): ClinicContext {
    return {
        clinicCode: response.clinic_code,
        clinicId: response.clinic_id,
        clinicName: response.clinic_name,
        status: response.status,
    };
}

function getErrorMessage(error: unknown, fallbackMessage: string): string {
    if (error instanceof Error && error.message) {
        return error.message;
    }

    if (typeof error === "string" && error) {
        return error;
    }

    return fallbackMessage;
}

function isClinicContextInvalidError(error: unknown): boolean {
    if (!(error instanceof ApiClientError)) {
        return false;
    }

    const code = (error.details as ApiErrorWithEnvelope | null)?.error?.code;
    const message = error.message.toLowerCase();

    return code === "CLINIC_CONTEXT_INVALID" || code === "CLINIC_CODE_INVALID" || message === "clinic code is invalid" || message === "clinic code is inactive";
}

export default function ClinicianLoginPage() {
    const router = useRouter();
    const dispatch = useDispatch<AppDispatch>();
    const [stage, setStage] = useState<LoginStage>("verify");
    const [clinicCode, setClinicCode] = useState("");
    const [clinicContext, setClinicContext] = useState<ClinicContext | null>(null);
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [clinicCodeError, setClinicCodeError] = useState("");
    const [mfaFactors, setMfaFactors] = useState<MFAFactorSummary[]>([]);
    const [mfaCode, setMfaCode] = useState("");
    const [passwordVisible, setPasswordVisible] = useState(false);
    const [pendingMFAChallenge, setPendingMFAChallenge] =
        useState<PendingMFAChallenge | null>(null);
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        const stored = readStoredClinicContext();
        if (!stored) {
            return;
        }

        const revalidateStoredClinicContext = async () => {
            setClinicCode(stored.clinicCode);
            setSubmitting(true);

            try {
                const resolved = await api.post<ClinicResolveResponse>("/api/v1/clinics/resolve-code", {
                    clinic_code: stored.clinicCode,
                });
                const nextClinicContext = mapClinicContext(resolved);
                writeStoredClinicContext(nextClinicContext);
                setClinicContext(nextClinicContext);
                setStage("choose");
            } catch {
                clearStoredClinicContext();
                setClinicContext(null);
                setStage("verify");
                setError("Saved clinic access expired. Please verify your clinic code again.");
            } finally {
                setSubmitting(false);
            }
        };

        void revalidateStoredClinicContext();
    }, []);

    async function handleVerifyClinicCode(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setError("");
        setClinicCodeError("");
        setMfaFactors([]);

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
            const context = mapClinicContext(resolved);

            writeStoredClinicContext(context);
            setClinicCode(context.clinicCode);
            setClinicContext(context);
            setStage("choose");
        } catch (submissionError) {
            setClinicCodeError(
                getErrorMessage(
                    submissionError,
                    "Unable to verify clinic code. Please try again.",
                ),
            );
        } finally {
            setSubmitting(false);
        }
    }

    function expireClinicContext(message: string) {
        const retainedClinicCode = clinicContext?.clinicCode ?? clinicCode;
        clearStoredClinicContext();
        setClinicContext(null);
        setMfaFactors([]);
        setStage("verify");
        setClinicCode(retainedClinicCode);
        setError(message);
    }

    async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setSubmitting(true);
        setError("");
        setMfaFactors([]);
        setMfaCode("");
        setPendingMFAChallenge(null);

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
            if (response.user.role !== PortalUserRole.CLINICIAN) {
                throw new Error(
                    "This account is registered as a patient. Please use the patient portal to sign in.",
                );
            }

            if (response.mfa_required) {
                const factors = response.mfa_factors ?? [];
                const primaryFactor = factors[0];
                if (!primaryFactor) {
                    throw new Error(
                        "Multi-factor authentication is required, but no verification method is set up for your account. Please contact your clinic administrator to set up MFA, then try signing in again.",
                    );
                }

                const pendingSession: ClinicianAuthSession = {
                    accessToken: response.tokens.access_token,
                    expiresAt: response.tokens.expires_at,
                    refreshToken: response.tokens.refresh_token,
                    user: {
                        email: response.user.email,
                        id: response.user.id,
                        role: PortalUserRole.CLINICIAN,
                    },
                };

                setMfaFactors(factors);
                setPendingMFAChallenge({
                    factorId: primaryFactor.id,
                    friendlyName: primaryFactor.friendly_name ?? "Authenticator",
                    session: pendingSession,
                });
                setStage("mfa");
                return;
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
            if (
                !isRetryableApiError(submissionError)
                && isClinicContextInvalidError(submissionError)
            ) {
                expireClinicContext("Saved clinic access expired. Please verify your clinic code again.");
                return;
            }
            setError(
                getErrorMessage(
                    submissionError,
                    "Unable to sign in right now. Please try again.",
                ),
            );
        } finally {
            setSubmitting(false);
        }
    }

    async function handleMFAVerify(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!pendingMFAChallenge) {
            return;
        }

        const code = mfaCode.trim();
        if (!/^\d{6}$/.test(code)) {
            setError("Enter the 6-digit code from your authenticator app.");
            return;
        }

        setSubmitting(true);
        setError("");

        try {
            const response = await api.post<MFAVerifyResponse>(
                "/api/v1/auth/mfa/verify",
                { factor_id: pendingMFAChallenge.factorId, code },
                {
                    headers: {
                        "X-Refresh-Token": pendingMFAChallenge.session.refreshToken,
                    },
                    token: pendingMFAChallenge.session.accessToken,
                },
            );

            const session: ClinicianAuthSession = {
                accessToken: response.access_token,
                expiresAt: response.expires_at,
                refreshToken: response.refresh_token,
                user: pendingMFAChallenge.session.user,
            };
            writeStoredSession(session);
            dispatch(hydrateSession(session));
            router.replace("/dashboard");
        } catch (submissionError) {
            setError(
                getErrorMessage(
                    submissionError,
                    "Unable to verify your MFA code. Please try again.",
                ),
            );
        } finally {
            setSubmitting(false);
        }
    }

    function useDifferentClinicCode() {
        clearStoredClinicContext();
        setClinicContext(null);
        setClinicCode("");
        setEmail("");
        setError("");
        setClinicCodeError("");
        setMfaFactors([]);
        setPassword("");
        setPasswordVisible(false);
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
                        <p className="text-sm font-medium text-blue-600">Clinic access</p>
                        <h2 className="text-3xl font-bold text-gray-900">
                            {stage === "verify"
                                ? "Enter clinic code"
                                : stage === "choose"
                                    ? "Choose sign-in path"
                                    : stage === "login"
                                        ? "Sign in"
                                        : "Verify MFA"}
                        </h2>
                        <p className="text-sm text-gray-500">
                            {stage === "verify"
                                ? "Verify your clinic workspace before continuing to login or registration."
                                : stage === "choose"
                                    ? "Clinic verified. Continue to sign in with your account or join this clinic."
                                    : stage === "login"
                                        ? "Access your dashboard, roster, and active alerts."
                                        : "Use your authenticator app to complete sign-in."}
                        </p>
                    </div>

                    {stage === "verify" ? (
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
                            {error ? <p className="text-sm text-red-600">{error}</p> : null}
                            <Button disabled={submitting} fullWidth type="submit">
                                {submitting ? "Verifying..." : "Verify clinic code"}
                            </Button>
                            <Link className="block text-center text-sm font-medium text-blue-600" href="/signup/admin">
                                Start a new clinic workspace (creates Clinic Admin)
                            </Link>
                        </form>
                    ) : null}

                    {stage === "choose" && clinicContext ? (
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
                            <button className="w-full text-sm text-slate-500 underline" onClick={useDifferentClinicCode} type="button">
                                Use a different clinic code
                            </button>
                        </div>
                    ) : null}

                    {stage === "mfa" && clinicContext ? (
                        <div className="space-y-4">
                            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                                <p className="font-semibold">Multi-factor authentication required</p>
                                <p className="mt-1">
                                    Enter the 6-digit code from your authenticator app to continue signing in to{" "}
                                    <span className="font-medium">{clinicContext.clinicName}</span>.
                                </p>
                            </div>
                            <div className="space-y-2 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                                <p className="font-semibold text-slate-900">Available factors</p>
                                {mfaFactors.length > 0 ? (
                                    mfaFactors.map((factor) => (
                                        <p key={factor.id}>{factor.friendly_name ?? "Authenticator"}</p>
                                    ))
                                ) : (
                                    <p>Authenticator</p>
                                )}
                            </div>
                            <form className="space-y-4" onSubmit={handleMFAVerify}>
                                <Input
                                    autoComplete="one-time-code"
                                    inputMode="numeric"
                                    label={`6-digit code (${pendingMFAChallenge?.friendlyName ?? "Authenticator"})`}
                                    maxLength={6}
                                    onChange={(event) => setMfaCode(event.target.value.replace(/\D/g, ""))}
                                    placeholder="000000"
                                    value={mfaCode}
                                />
                                {error ? <p className="text-sm text-red-600">{error}</p> : null}
                                <Button disabled={submitting || mfaCode.trim().length !== 6} fullWidth type="submit">
                                    {submitting ? "Verifying..." : "Verify and continue"}
                                </Button>
                            </form>
                            <div className="flex items-center justify-start text-sm">
                                <button
                                    className="text-blue-600"
                                    onClick={() => {
                                        setStage("login");
                                        setMfaCode("");
                                        setPendingMFAChallenge(null);
                                        setError("");
                                    }}
                                    type="button"
                                >
                                    Back
                                </button>
                            </div>
                        </div>
                    ) : null}

                    {stage === "login" && clinicContext ? (
                        <>
                            <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                                Signing into clinic: <span className="font-semibold">{clinicContext.clinicName}</span>
                            </div>
                            <form className="space-y-4" onSubmit={handleSubmit}>
                                <Input label="Email" onChange={(event) => setEmail(event.target.value)} type="email" value={email} />
                                <Input
                                    label="Password"
                                    onChange={(event) => setPassword(event.target.value)}
                                    trailingAction={
                                        <button
                                            aria-label={passwordVisible ? "Hide password" : "Show password"}
                                            className="inline-flex h-6 w-6 items-center justify-center rounded text-gray-500 hover:text-gray-700"
                                            onClick={() => setPasswordVisible((current) => !current)}
                                            type="button"
                                        >
                                            {passwordVisible ? <FiEyeOff className="h-4 w-4" /> : <FiEye className="h-4 w-4" />}
                                        </button>
                                    }
                                    type={passwordVisible ? "text" : "password"}
                                    value={password}
                                />
                                {error ? <p className="text-sm text-red-600">{error}</p> : null}
                                <Button disabled={submitting} fullWidth type="submit">
                                    {submitting ? "Signing in..." : "Sign in"}
                                </Button>
                            </form>
                            <div className="flex items-center justify-start text-sm">
                                <button className="text-blue-600" onClick={() => setStage("choose")} type="button">
                                    Back
                                </button>
                            </div>
                        </>
                    ) : null}
                </Card>
            </div>
        </div>
    );
}
