"use client";

import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useDispatch } from "react-redux";
import { Button, Input } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { AuthShell, AuthSteps, VerifiedClinic } from "@/components/features/auth-shell";
import { api } from "@/services/api";
import { consumeSignOutReason, writeStoredSession } from "@/services/auth-session";
import {
    clearStoredClinicContext,
    writeStoredClinicContext,
    type ClinicContext,
} from "@/services/clinic-context";
import { clinicErrorMessage, fetchMyClinics, joinClinicByCode } from "@/services/clinics";
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
    /** True when the clinic code path is adding a clinic once sign-in completes. */
    joining: boolean;
    session: ClinicianAuthSession;
}

interface ClinicResolveResponse {
    clinic_code: string;
    clinic_id: string;
    clinic_name: string;
    status: "active" | "suspended";
}

// "login" is the default: email, password and MFA, with no clinic code. "verify", "choose" and
// "join-login" are the secondary path for adding a clinic to an existing account.
type LoginStage = "verify" | "choose" | "login" | "join-login" | "mfa";

type JoinRole = "provider" | "nurse";

function mapClinicContext(response: ClinicResolveResponse): ClinicContext {
    return {
        clinicCode: response.clinic_code,
        clinicId: response.clinic_id,
        clinicName: response.clinic_name,
        status: response.status,
    };
}

function getErrorMessage(error: unknown, fallbackMessage: string): string {
    return clinicErrorMessage(error, fallbackMessage);
}

function ClinicianLoginPageContent() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const dispatch = useDispatch<AppDispatch>();
    const [stage, setStage] = useState<LoginStage>("login");
    const [clinicCode, setClinicCode] = useState("");
    // The clinic being added to an existing account (secondary path only).
    const [clinicContext, setClinicContext] = useState<ClinicContext | null>(null);
    const [joinRole, setJoinRole] = useState<JoinRole>("provider");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [clinicCodeError, setClinicCodeError] = useState("");
    const [mfaFactors, setMfaFactors] = useState<MFAFactorSummary[]>([]);
    const [mfaCode, setMfaCode] = useState("");
    const [passwordVisible, setPasswordVisible] = useState(false);
    const [pendingMFAChallenge, setPendingMFAChallenge] =
        useState<PendingMFAChallenge | null>(null);
    // Signed in, but adding the clinic failed: keep the session so the clinician can retry or go on.
    const [joinFailedSession, setJoinFailedSession] = useState<ClinicianAuthSession | null>(null);
    const [submitting, setSubmitting] = useState(false);

    const returnPath = sanitizeReturnPath(searchParams?.get("return_path")) ?? "/dashboard";
    const queryReason = searchParams?.get("reason") ?? "";
    // A sign-out recorded by the session limits or another tab can arrive without the query reason.
    const [storedReason, setStoredReason] = useState<string | null>(null);
    useEffect(() => {
        setStoredReason(consumeSignOutReason());
    }, []);
    const reason = queryReason || storedReason || "";
    const joining = clinicContext !== null && (stage === "join-login" || (stage === "mfa" && pendingMFAChallenge?.joining));

    useEffect(() => {
        if (reason === "session_expired") {
            setError("Your session expired. Please sign in again.");
        }

        if (reason === "inactivity") {
            setError("You were signed out after 2 hours of inactivity.");
        }

        if (reason === "session_limit") {
            setError("Your session reached its 12-hour limit.");
        }

        if (reason === "unauthorized") {
            setError("You no longer have access to this portal. Please sign in again.");
        }
    }, [reason]);

    function resetSignInFields() {
        setError("");
        setMfaFactors([]);
        setMfaCode("");
        setPendingMFAChallenge(null);
        setJoinFailedSession(null);
    }

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

            // The signup page reads this to continue joining the verified clinic.
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

    // Show the clinician's clinic name in the sidebar only when there is exactly one: with
    // several there is no single clinic to show, and no clinic is "active".
    async function rememberDisplayClinic(accessToken: string) {
        try {
            const { clinics } = await fetchMyClinics(accessToken);
            if (clinics.length === 1) {
                writeStoredClinicContext({
                    clinicCode: clinics[0].clinic_code ?? "",
                    clinicId: clinics[0].clinic_id,
                    clinicName: clinics[0].clinic_name,
                    status: clinics[0].status,
                });
            } else {
                clearStoredClinicContext();
            }
        } catch {
            // Display only; the portal works without it.
        }
    }

    async function finishSignIn(session: ClinicianAuthSession, joinTarget: ClinicContext | null) {
        if (joinTarget) {
            try {
                const joined = await joinClinicByCode(session.accessToken, joinTarget.clinicCode, joinRole);
                writeStoredClinicContext({
                    clinicCode: joined.clinic_code,
                    clinicId: joined.clinic_id,
                    clinicName: joined.clinic_name,
                    status: joined.clinic_status,
                });
            } catch (joinError) {
                setJoinFailedSession(session);
                setPendingMFAChallenge(null);
                setStage("join-login");
                setError(
                    getErrorMessage(joinError, "Signed in, but this clinic could not be added. Please try again."),
                );
                return;
            }
        } else {
            await rememberDisplayClinic(session.accessToken);
        }
        writeStoredSession(session, { signIn: true });
        dispatch(hydrateSession(session));
        router.replace(returnPath.startsWith("/login") ? "/dashboard" : returnPath);
    }

    async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setSubmitting(true);
        setError("");
        setMfaFactors([]);
        setMfaCode("");
        setPendingMFAChallenge(null);
        setJoinFailedSession(null);

        const joinTarget = stage === "join-login" ? clinicContext : null;

        try {
            // A deployed portal may still send a clinic code; this one does not need to.
            const response = await api.post<LoginResponse>("/api/v1/auth/login", {
                email,
                password,
            });
            if (response.user.role !== PortalUserRole.CLINICIAN) {
                throw new Error(
                    "This account is registered as a patient. Please use the patient portal to sign in.",
                );
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

            if (response.mfa_required) {
                const factors = response.mfa_factors ?? [];
                const primaryFactor = factors[0];
                if (!primaryFactor) {
                    throw new Error(
                        "Multi-factor authentication is required, but no verification method is set up for your account. Please contact your clinic administrator to set up MFA, then try signing in again.",
                    );
                }

                setMfaFactors(factors);
                setPendingMFAChallenge({
                    factorId: primaryFactor.id,
                    friendlyName: primaryFactor.friendly_name ?? "Authenticator",
                    joining: joinTarget !== null,
                    session,
                });
                setStage("mfa");
                return;
            }

            await finishSignIn(session, joinTarget);
        } catch (submissionError) {
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
            await finishSignIn(session, pendingMFAChallenge.joining ? clinicContext : null);
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

    async function continueWithoutJoining() {
        if (!joinFailedSession) {
            return;
        }
        await rememberDisplayClinic(joinFailedSession.accessToken);
        writeStoredSession(joinFailedSession, { signIn: true });
        dispatch(hydrateSession(joinFailedSession));
        router.replace(returnPath.startsWith("/login") ? "/dashboard" : returnPath);
    }

    function backToSignIn() {
        clearStoredClinicContext();
        setClinicContext(null);
        setClinicCode("");
        setClinicCodeError("");
        setPassword("");
        setPasswordVisible(false);
        resetSignInFields();
        setStage("login");
    }

    function useDifferentClinicCode() {
        clearStoredClinicContext();
        setClinicContext(null);
        setClinicCode("");
        setEmail("");
        setClinicCodeError("");
        setPassword("");
        setPasswordVisible(false);
        resetSignInFields();
        setStage("verify");
    }

    const secondaryPath = stage !== "login" && !(stage === "mfa" && !joining);
    const heading =
        stage === "verify"
            ? "Join a clinic"
            : stage === "choose"
                ? "Choose sign-in path"
                : stage === "mfa"
                    ? "Verify MFA"
                    : "Sign in";
    const subcopy =
        stage === "verify"
            ? "Enter the clinic code to join that clinic or create a workspace. You can belong to more than one clinic with a single account."
            : stage === "choose"
                ? "Clinic verified. Sign in to add it to your account, or create an account to join this clinic."
                : stage === "join-login"
                    ? "Sign in to add this clinic to your account. Your other clinics and patients stay as they are."
                    : stage === "login"
                        ? "Access your dashboard, roster, and active alerts."
                        : "Use your authenticator app to complete sign-in.";

    return (
        <AuthShell
            headline="Clinical intelligence for the entire patient panel."
            subcopy="Review AI-drafted care plans against their source documents, catch adherence risk early, and publish only what you approve."
            footer="Supervised clinical decision support for outpatient chronic care."
        >
                <div className="space-y-6">
                    <div className="space-y-2">
                        {secondaryPath ? (
                            <AuthSteps
                                label="Join a clinic"
                                step={stage === "verify" ? 1 : stage === "choose" ? 2 : 3}
                            />
                        ) : null}
                        <p className="sr-only">Clinician sign in</p>
                        <h2 className="pt-3 text-[26px] font-semibold leading-tight tracking-[-0.02em] text-ink">
                            {heading}
                        </h2>
                        <p className="text-sm leading-relaxed text-muted">{subcopy}</p>
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
                            <button className="w-full text-sm text-muted hover:text-ink" onClick={backToSignIn} type="button">
                                Back to sign in
                            </button>
                        </form>
                    ) : null}

                    {stage === "choose" && clinicContext ? (
                        <div className="space-y-4">
                            <VerifiedClinic code={`${clinicContext.clinicCode} · verified`} name={clinicContext.clinicName}>
                                <p className="sr-only">Clinic verified: {clinicContext.clinicName}</p>
                                <p className="sr-only">Code: {clinicContext.clinicCode}</p>
                            </VerifiedClinic>
                            {error ? <p role="alert" className="rounded-lg bg-risk-soft px-3 py-2 text-sm text-risk-ink">{error}</p> : null}
                            <Button
                                fullWidth
                                onClick={() => {
                                    resetSignInFields();
                                    setStage("join-login");
                                }}
                                size="lg"
                                type="button"
                            >
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

                    {stage === "mfa" ? (
                        <div className="space-y-4">
                            <div className="flex items-start gap-3 rounded-xl border border-warn-line bg-warn-soft px-4 py-3 text-sm text-warn-ink">
                                <Icon name="shield" className="mt-0.5 h-4 w-4 shrink-0" />
                                <div>
                                <p className="font-semibold">Multi-factor authentication required</p>
                                <p className="mt-1">
                                    Enter the 6-digit code from your authenticator app to continue signing in
                                    {joining && clinicContext ? (
                                        <>
                                            {" "}and add <span className="font-medium">{clinicContext.clinicName}</span>
                                        </>
                                    ) : null}
                                    .
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
                                        setStage(joining ? "join-login" : "login");
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

                    {stage === "login" || stage === "join-login" ? (
                        <>
                            {stage === "join-login" && clinicContext ? (
                                <div className="space-y-3">
                                    <div className="flex items-center gap-2.5 rounded-xl border border-line bg-surface-2 px-3.5 py-2.5 text-sm text-ink-2">
                                        <Icon name="building" className="h-4 w-4 shrink-0 text-muted" />
                                        <span>Adding clinic: <span className="font-semibold text-ink">{clinicContext.clinicName}</span></span>
                                    </div>
                                    <label className="block">
                                        <span className="mb-1.5 block text-[13px] font-medium text-ink-2">Your role at this clinic</span>
                                        <select
                                            className="h-[42px] w-full rounded-[10px] border border-line-strong bg-surface px-3.5 text-sm text-ink"
                                            onChange={(event) => setJoinRole(event.target.value as JoinRole)}
                                            value={joinRole}
                                        >
                                            <option value="provider">Provider</option>
                                            <option value="nurse">Nurse / MA</option>
                                        </select>
                                    </label>
                                </div>
                            ) : null}
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
                                <Link className="inline-flex min-h-11 items-center text-sm font-semibold text-primary" href="/forgot-password">
                                    Forgot your password?
                                </Link>
                                <Button disabled={submitting} fullWidth size="lg" type="submit">
                                    {submitting ? "Signing in..." : stage === "join-login" ? "Sign in and add clinic" : "Sign in"}
                                </Button>
                                {joinFailedSession ? (
                                    <Button fullWidth onClick={() => void continueWithoutJoining()} size="lg" type="button" variant="secondary">
                                        Continue to my dashboard
                                    </Button>
                                ) : null}
                            </form>
                            {stage === "login" ? (
                                <div className="space-y-0.5 border-t border-line pt-4 text-sm">
                                    <p className="text-muted">
                                        Joining a clinic or setting one up?{" "}
                                        <button
                                            className="font-medium text-primary hover:underline"
                                            onClick={() => {
                                                resetSignInFields();
                                                setStage("verify");
                                            }}
                                            type="button"
                                        >
                                            Join a clinic
                                        </button>
                                    </p>
                                    <p className="text-xs text-muted">Add a clinic to this account with its clinic code, or create a new workspace.</p>
                                </div>
                            ) : (
                                <div className="flex items-center justify-start text-sm">
                                    <button
                                        className="inline-flex items-center gap-1 font-medium text-muted hover:text-ink"
                                        onClick={() => {
                                            resetSignInFields();
                                            setStage("choose");
                                        }}
                                        type="button"
                                    >
                                        <Icon name="back" className="h-3.5 w-3.5" />
                                        Back
                                    </button>
                                </div>
                            )}
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
