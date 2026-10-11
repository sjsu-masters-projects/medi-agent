"use client";

import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useDispatch } from "react-redux";
import { Button, Input } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { AuthShell, AuthSteps, VerifiedClinic } from "@/components/features/auth-shell";
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
import { sanitizeReturnPath } from "../../../../../../packages/shared/src/utils/return-path";

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

const CLINIC_CONTEXT_ERROR_CODES = new Set([
    "CLINIC_CONTEXT_INVALID",
    "CLINIC_CODE_INVALID",
    "CLINIC_CODE_INACTIVE",
]);

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
    return typeof code === "string" && CLINIC_CONTEXT_ERROR_CODES.has(code);
}

function ClinicianLoginPageContent() {
    const router = useRouter();
    const searchParams = useSearchParams();
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

    const returnPath = sanitizeReturnPath(searchParams?.get("return_path")) ?? "/dashboard";
    const reason = searchParams?.get("reason") ?? "";

    useEffect(() => {
        if (reason === "session_expired") {
            setError("Your session expired. Please sign in again.");
        }

        if (reason === "unauthorized") {
            setError("You no longer have access to this portal. Please sign in again.");
        }
    }, [reason]);

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
            router.replace(returnPath.startsWith("/login") ? "/dashboard" : returnPath);
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
            router.replace(returnPath.startsWith("/login") ? "/dashboard" : returnPath);
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
        <AuthShell
            headline="Clinical intelligence for the entire patient panel."
            subcopy="Review AI-drafted care plans against their source documents, catch adherence risk early, and publish only what you approve."
            footer="Supervised clinical decision support for outpatient chronic care."
        >
                <div className="space-y-6">
                    <div className="space-y-2">
                        <AuthSteps label="Clinic access" step={stage === "verify" ? 1 : stage === "choose" ? 2 : 3} />
                        <p className="sr-only">Clinic access</p>
                        <h2 className="pt-3 text-[26px] font-semibold leading-tight tracking-[-0.02em] text-ink">
                            {stage === "verify"
                                ? "Enter clinic code"
                                : stage === "choose"
                                    ? "Choose sign-in path"
                                    : stage === "login"
                                        ? "Sign in"
                                        : "Verify MFA"}
                        </h2>
                        <p className="text-sm leading-relaxed text-muted">
                            {stage === "verify"
                                ? "Your clinic code opens your workspace. Next, you'll sign in or join the clinic."
                                : stage === "choose"
                                    ? "Clinic verified. Sign in, or create an account to join this clinic."
                                    : stage === "login"
                                        ? "Access your dashboard, roster, and active alerts."
                                        : "Use your authenticator app to complete sign-in."}
                        </p>
                    </div>

                    {stage === "verify" ? (
                        <form className="space-y-4" onSubmit={handleVerifyClinicCode}>
                            <Input
                                className="font-mono tracking-[0.04em]"
                                error={clinicCodeError}
                                label="Clinic code"
                                placeholder="CA-CLINIC-"
                                onChange={(event) => {
                                    setClinicCode(event.target.value.toUpperCase());
                                    if (clinicCodeError) {
                                        setClinicCodeError("");
                                    }
                                }}
                                value={clinicCode}
                            />
                            {error ? <p role="alert" className="rounded-lg bg-risk-soft px-3 py-2 text-sm text-risk-ink">{error}</p> : null}
                            <Button disabled={submitting} fullWidth size="lg" type="submit">
                                {submitting ? "Verifying..." : <>Verify clinic code<Icon name="arrow" className="h-4 w-4" /></>}
                            </Button>
                            <div className="space-y-0.5 border-t border-line pt-4 text-sm">
                                <p className="text-muted">
                                    New clinic?{" "}
                                    <Link className="font-medium text-primary hover:underline" href="/signup/admin">
                                        Create a clinic workspace
                                    </Link>
                                </p>
                                <p className="text-xs text-muted">You&apos;ll set it up as its first Clinic Admin.</p>
                            </div>
                        </form>
                    ) : null}

                    {stage === "choose" && clinicContext ? (
                        <div className="space-y-4">
                            <VerifiedClinic code={`${clinicContext.clinicCode} · verified`} name={clinicContext.clinicName}>
                                <p className="sr-only">Clinic verified: {clinicContext.clinicName}</p>
                                <p className="sr-only">Code: {clinicContext.clinicCode}</p>
                            </VerifiedClinic>
                            {error ? <p role="alert" className="rounded-lg bg-risk-soft px-3 py-2 text-sm text-risk-ink">{error}</p> : null}
                            <Button fullWidth onClick={() => setStage("login")} size="lg" type="button">
                                I already have an account
                            </Button>
                            <Link className="block" href="/signup">
                                <Button fullWidth size="lg" type="button" variant="secondary">
                                    Join this clinic (Provider / Nurse)
                                </Button>
                            </Link>
                            <button className="w-full text-sm text-muted hover:text-ink" onClick={useDifferentClinicCode} type="button">
                                Use a different clinic code
                            </button>
                        </div>
                    ) : null}

                    {stage === "mfa" && clinicContext ? (
                        <div className="space-y-4">
                            <div className="flex items-start gap-3 rounded-xl border border-warn-line bg-warn-soft px-4 py-3 text-sm text-warn-ink">
                                <Icon name="shield" className="mt-0.5 h-4 w-4 shrink-0" />
                                <div>
                                <p className="font-semibold">Multi-factor authentication required</p>
                                <p className="mt-1">
                                    Enter the 6-digit code from your authenticator app to continue signing in to{" "}
                                    <span className="font-medium">{clinicContext.clinicName}</span>.
                                </p>
                                </div>
                            </div>
                            <div className="space-y-1 rounded-xl border border-line bg-surface-2 px-4 py-3 text-sm text-ink-2">
                                <p className="font-semibold text-ink">Available factors</p>
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
                                    className="text-center font-mono text-lg tracking-[0.4em]"
                                    placeholder="000000"
                                    value={mfaCode}
                                />
                                {error ? <p role="alert" className="rounded-lg bg-risk-soft px-3 py-2 text-sm text-risk-ink">{error}</p> : null}
                                <Button disabled={submitting || mfaCode.trim().length !== 6} fullWidth size="lg" type="submit">
                                    {submitting ? "Verifying..." : "Verify and continue"}
                                </Button>
                            </form>
                            <div className="flex items-center justify-start text-sm">
                                <button
                                    className="inline-flex items-center gap-1 font-medium text-muted hover:text-ink"
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
                            <div className="flex items-center gap-2.5 rounded-xl border border-line bg-surface-2 px-3.5 py-2.5 text-sm text-ink-2">
                                <Icon name="building" className="h-4 w-4 shrink-0 text-muted" />
                                <span>Signing into clinic: <span className="font-semibold text-ink">{clinicContext.clinicName}</span></span>
                            </div>
                            <form className="space-y-4" onSubmit={handleSubmit}>
                                <Input
                                    autoComplete="email"
                                    label="Email"
                                    onChange={(event) => setEmail(event.target.value)}
                                    type="email"
                                    value={email}
                                />
                                <Input
                                    autoComplete="current-password"
                                    label="Password"
                                    onChange={(event) => setPassword(event.target.value)}
                                    trailingAction={
                                        <button
                                            aria-label={passwordVisible ? "Hide password" : "Show password"}
                                            className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted hover:bg-sunken hover:text-ink-2"
                                            onClick={() => setPasswordVisible((current) => !current)}
                                            type="button"
                                        >
                                            <Icon name={passwordVisible ? "eyeOff" : "eye"} className="h-4 w-4" />
                                        </button>
                                    }
                                    type={passwordVisible ? "text" : "password"}
                                    value={password}
                                />
                                {error ? <p role="alert" className="rounded-lg bg-risk-soft px-3 py-2 text-sm text-risk-ink">{error}</p> : null}
                                <Button disabled={submitting} fullWidth size="lg" type="submit">
                                    {submitting ? "Signing in..." : "Sign in"}
                                </Button>
                            </form>
                            <div className="flex items-center justify-start text-sm">
                                <button className="inline-flex items-center gap-1 font-medium text-muted hover:text-ink" onClick={() => setStage("choose")} type="button">
                                    <Icon name="back" className="h-3.5 w-3.5" />
                                    Back
                                </button>
                            </div>
                        </>
                    ) : null}
                </div>
        </AuthShell>
    );
}

export default function ClinicianLoginPage() {
    return (
        <Suspense fallback={null}>
            <ClinicianLoginPageContent />
        </Suspense>
    );
}
