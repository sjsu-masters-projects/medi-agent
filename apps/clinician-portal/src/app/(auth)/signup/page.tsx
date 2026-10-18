"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Button, Input } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { AuthShell, AuthSteps, VerifiedClinic } from "@/components/features/auth-shell";
import { api } from "@/services/api";
import { apiErrorCode, clinicErrorMessage } from "@/services/clinics";
import { writeStoredSession } from "@/services/auth-session";
import {
    readStoredClinicContext,
    writeStoredClinicContext,
    type ClinicContext,
} from "@/services/clinic-context";
import { hydrateSession, type ClinicianAuthSession } from "@/store/slices/auth-slice";
import type { AppDispatch, RootState } from "@/store/store";
import { ClinicianRole, PortalUserRole } from "@/types";

interface SignupResponse {
    clinic?: ClinicResolveResponse | null;
    invitation_status?: "accepted" | "pending" | null;
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

interface ClinicResolveResponse {
    clinic_code: string;
    clinic_id: string;
    clinic_name: string;
    status: "active" | "suspended";
}

/** Unauthenticated preview: the clinic code is shared only after acceptance. */
interface InvitationPreview {
    clinic_name: string;
    email: string;
    role: ClinicianRole;
}

interface InvitationAcceptResponse {
    clinic: ClinicResolveResponse;
    status: "accepted";
}

const roleLabels: Record<string, string> = {
    [ClinicianRole.ADMIN]: "Clinic Admin",
    [ClinicianRole.NURSE]: "Nurse / MA",
    [ClinicianRole.PROVIDER]: "Provider",
};

function mapClinicContext(response: ClinicResolveResponse): ClinicContext {
    return {
        clinicCode: response.clinic_code,
        clinicId: response.clinic_id,
        clinicName: response.clinic_name,
        status: response.status,
    };
}

function ClinicianSignupPageContent() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const dispatch = useDispatch<AppDispatch>();
    const [error, setError] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [inviteLoading, setInviteLoading] = useState(false);
    const [clinicContext, setClinicContext] = useState<ClinicContext | null>(null);
    const [inviteRole, setInviteRole] = useState<ClinicianRole | null>(null);
    const inviteHydrated = useRef(false);
    const [invitationToken, setInvitationToken] = useState("");
    const [invitation, setInvitation] = useState<InvitationPreview | null>(null);
    const [signInOpen, setSignInOpen] = useState(false);
    const [signInPassword, setSignInPassword] = useState("");
    // Asked for only when the account has an authenticator but no active clinic to sign in to.
    const [needsMfaCode, setNeedsMfaCode] = useState(false);
    const [mfaCode, setMfaCode] = useState("");
    const [accepted, setAccepted] = useState(false);
    const accessToken = useSelector((state: RootState) => state.auth.accessToken);
    const existingAccountPanelRef = useRef<HTMLDivElement>(null);
    const existingAccountToggleRef = useRef<HTMLButtonElement>(null);
    const pendingFocus = useRef<"panel" | "toggle" | null>(null);
    // Creating an account is the primary invitation path; an existing account is opt-in.
    const canChooseExistingAccount = Boolean(invitationToken) && !accepted && Boolean(invitation || accessToken);
    const existingAccountOpen = canChooseExistingAccount && signInOpen;
    const [formData, setFormData] = useState({
        confirmPassword: "",
        email: "",
        firstName: "",
        lastName: "",
        npiNumber: "",
        password: "",
        role: ClinicianRole.PROVIDER,
        specialty: "",
    });

    const updateField = useCallback((field: keyof typeof formData, value: string) => {
        setFormData((current) => ({ ...current, [field]: value }));
    }, []);

    const chooseExistingAccount = useCallback((open: boolean) => {
        pendingFocus.current = open ? "panel" : "toggle";
        setError("");
        setSignInOpen(open);
    }, []);

    useEffect(() => {
        const target = pendingFocus.current;
        pendingFocus.current = null;
        if (target === "panel") {
            existingAccountPanelRef.current?.querySelector<HTMLElement>("input, button")?.focus();
        } else if (target === "toggle") {
            existingAccountToggleRef.current?.focus();
        }
    }, [signInOpen]);

    useEffect(() => {
        const stored = readStoredClinicContext();
        setClinicContext(stored);
    }, []);

    useEffect(() => {
        if (inviteHydrated.current) {
            return;
        }

        const token = new URLSearchParams(window.location.hash.slice(1)).get("invitation");
        if (token) {
            inviteHydrated.current = true;
            window.history.replaceState(null, "", window.location.pathname + window.location.search);
            setInvitationToken(token); setInviteLoading(true);
            void api.post<InvitationPreview>(
                "/api/v1/email/invitations/preview", { token },
            ).then(value => {
                setInvitation(value);
                updateField("email", value.email); updateField("role", value.role); setInviteRole(value.role);
            }).catch((previewError) => setError(
                (previewError as Error).message || "This invitation is invalid, expired or no longer available.",
            ))
              .finally(() => setInviteLoading(false));
            return;
        }

        const emailParam = searchParams?.get("email")?.trim() ?? "";
        const roleParam = searchParams?.get("role")?.trim().toLowerCase() ?? "";
        const codeParam = searchParams?.get("code")?.trim() ?? "";

        if (emailParam) {
            updateField("email", emailParam);
        }

        // Admin access is granted only by an addressed invitation, never a query string.
        const resolvedRole =
            roleParam === ClinicianRole.NURSE
                  ? ClinicianRole.NURSE
                  : roleParam === ClinicianRole.PROVIDER
                    ? ClinicianRole.PROVIDER
                    : null;

        if (resolvedRole) {
            updateField("role", resolvedRole);
            setInviteRole(resolvedRole);
        }

        if (!codeParam) {
            inviteHydrated.current = true;
            return;
        }

        inviteHydrated.current = true;
        setInviteLoading(true);
        setError("");

        const resolveInviteClinic = async () => {
            try {
                const resolved = await api.post<ClinicResolveResponse>(
                    "/api/v1/clinics/resolve-code",
                    { clinic_code: codeParam.toUpperCase() },
                );
                const context = mapClinicContext(resolved);
                writeStoredClinicContext(context);
                setClinicContext(context);
            } catch (submissionError) {
                setError(
                    (submissionError as Error).message ||
                        "Unable to verify the clinic invite. Please verify your clinic code first.",
                );
            } finally {
                setInviteLoading(false);
            }
        };

        void resolveInviteClinic();
    }, [searchParams, updateField]);

    async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setError("");

        if (!invitationToken && !clinicContext) {
            setError("Verify your clinic code first to continue.");
            return;
        }

        if (formData.password !== formData.confirmPassword) {
            setError("Passwords do not match.");
            return;
        }

        setSubmitting(true);

        try {
            const response = await api.post<SignupResponse>("/api/v1/auth/signup/clinician", {
                // An invitation names its clinic; the code is not shared before acceptance.
                clinic_code: invitationToken ? undefined : clinicContext?.clinicCode,
                email: formData.email,
                first_name: formData.firstName,
                last_name: formData.lastName,
                type1_npi: formData.npiNumber || undefined,
                password: formData.password,
                role: formData.role,
                specialty: formData.specialty,
                invitation_token: invitationToken || undefined,
            });

            if (response.user.role !== PortalUserRole.CLINICIAN) {
                throw new Error("This signup produced a non-clinician account.");
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
            if (response.clinic) {
                const context = mapClinicContext(response.clinic);
                writeStoredClinicContext(context); setClinicContext(context);
            }
            // The server claims membership in the same request. If that did not finish,
            // the account is kept and this signed-in session can retry the claim.
            if (invitationToken && response.invitation_status !== "accepted") {
                // The new account is signed in now, so the retry lives on the existing-account path.
                pendingFocus.current = "panel"; setSignInOpen(true);
                setError("Your account was created, but joining the clinic could not be confirmed yet. Use Accept invitation to try again.");
                setSubmitting(false);
                return;
            }
            router.replace("/dashboard");
        } catch (submissionError) {
            setError(clinicErrorMessage(submissionError, "Unable to create your account. Please try again."));
            setSubmitting(false);
        }
    }

    return (
        <AuthShell
            headline="Join your clinic's care team."
            subcopy="Create your clinician account to review AI drafts, approve care plans, and follow up with the patients assigned to you."
            footer="Access is limited to your clinic role and assigned care team."
            wide
        >
                <div className="space-y-6">
                    <div className="space-y-2">
                        <AuthSteps label="Clinic access" step={3} />
                        <p className="font-mono text-[11px] uppercase tracking-[0.06em] text-primary">Clinician signup</p>
                        <h2 className="text-[26px] font-semibold leading-tight tracking-[-0.02em] text-ink">Create your account</h2>
                        <p className="text-sm text-muted">Set up a clinician login for dashboard access and invite-code workflows.</p>
                        <p className="text-xs font-medium text-ink-2">Role access options: Provider or Nurse / MA</p>
                    </div>

                    {invitation ? (
                        <div className="rounded-[14px] border border-ok-line bg-ok-soft p-3.5 text-sm">
                            <p className="font-semibold text-ink">Invitation to join {invitation.clinic_name}</p>
                            <p className="text-ok-ink">{roleLabels[invitation.role] ?? invitation.role} · {invitation.email}</p>
                        </div>
                    ) : invitationToken ? null : clinicContext ? (
                        <VerifiedClinic code={clinicContext.clinicCode} name={clinicContext.clinicName}>
                            <p className="sr-only">Clinic: {clinicContext.clinicName}</p>
                            <p className="sr-only">Code: {clinicContext.clinicCode}</p>
                        </VerifiedClinic>
                    ) : (
                        <div className="flex items-start gap-2.5 rounded-xl border border-warn-line bg-warn-soft px-4 py-3 text-sm text-warn-ink">
                            <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
                            Verify your clinic code on the sign-in screen before creating an account.
                        </div>
                    )}

                    {invitation && accepted ? (
                        <div role="status" className="space-y-2 rounded-xl bg-surface-2 p-4 text-sm text-ink-2">
                            <p>Invitation accepted. Sign in to continue to {invitation.clinic_name}.</p>
                            <Link className="font-medium text-primary hover:underline" href="/login">Continue to sign in</Link>
                        </div>
                    ) : null}
                    {existingAccountOpen ? (
                        <div ref={existingAccountPanelRef} className="space-y-3 rounded-xl border border-line p-4">
                            {accessToken ? (
                                <>
                                    <p className="text-sm text-muted">You are signed in. Accept this invitation with your current clinician account.</p>
                                    <Button disabled={submitting || inviteLoading} onClick={() => {
                                        setSubmitting(true); setError("");
                                        void api.post<InvitationAcceptResponse>("/api/v1/email/invitations/accept", { token: invitationToken }, { token: accessToken })
                                            .then((result) => {
                                                writeStoredClinicContext(mapClinicContext(result.clinic));
                                                router.replace("/dashboard");
                                            })
                                            .catch((acceptError) => setError(clinicErrorMessage(acceptError, "This invitation cannot be accepted by the signed-in account.")))
                                            .finally(() => setSubmitting(false));
                                    }}>Accept invitation</Button>
                                </>
                            ) : invitation ? (
                                <form aria-label="Sign in to accept" className="space-y-3" onSubmit={(event) => {
                                    event.preventDefault();
                                    setSubmitting(true); setError("");
                                    void api.post<InvitationAcceptResponse>("/api/v1/auth/invitations/accept", {
                                        email: invitation.email, password: signInPassword, invitation_token: invitationToken,
                                        ...(needsMfaCode && mfaCode ? { mfa_code: mfaCode } : {}),
                                    }).then((result) => {
                                        const context = mapClinicContext(result.clinic);
                                        writeStoredClinicContext(context); setClinicContext(context);
                                        setSignInPassword(""); setAccepted(true);
                                    }).catch((acceptError) => {
                                        if (apiErrorCode(acceptError) === "MFA_CODE_REQUIRED") setNeedsMfaCode(true);
                                        setError(clinicErrorMessage(acceptError, "This invitation could not be accepted."));
                                    })
                                      .finally(() => setSubmitting(false));
                                }}>
                                    <p className="text-sm text-muted">Use your existing clinician account for {invitation.email}. You will sign in normally afterwards, including MFA.</p>
                                    <Input label="Existing account password" autoComplete="current-password" type="password" value={signInPassword} onChange={(event) => setSignInPassword(event.target.value)} />
                                    {needsMfaCode ? <Input label="Authenticator code" autoComplete="one-time-code" inputMode="numeric" maxLength={6} value={mfaCode} onChange={(event) => setMfaCode(event.target.value.replace(/\D/g, ""))} /> : null}
                                    <Button disabled={submitting || !signInPassword || (needsMfaCode && mfaCode.length !== 6)} type="submit">{submitting ? "Accepting..." : "Sign in to accept"}</Button>
                                </form>
                            ) : null}
                            {error ? <p role="alert" className="rounded-lg bg-risk-soft px-3 py-2 text-sm text-risk-ink">{error}</p> : null}
                            <button className="text-sm font-medium text-primary hover:underline" type="button" onClick={() => chooseExistingAccount(false)}>
                                Create a new account instead
                            </button>
                        </div>
                    ) : null}
                    {accepted || existingAccountOpen ? null : <form className="grid gap-4 md:grid-cols-2" onSubmit={handleSubmit}>
                        <Input label="First name" onChange={(event) => updateField("firstName", event.target.value)} value={formData.firstName} />
                        <Input label="Last name" onChange={(event) => updateField("lastName", event.target.value)} value={formData.lastName} />
                        <Input label="Email" readOnly={Boolean(invitationToken)} onChange={(event) => updateField("email", event.target.value)} type="email" value={formData.email} />
                        <Input label="Specialty" onChange={(event) => updateField("specialty", event.target.value)} value={formData.specialty} />
                        <label className="block">
                            <span className="mb-1.5 block text-[13px] font-medium text-ink-2">Role access</span>
                            <select
                                className="h-[42px] w-full rounded-[10px] border border-line-strong bg-surface px-3.5 text-sm text-ink outline-none transition focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)] disabled:bg-surface-2 disabled:text-muted"
                                disabled={Boolean(inviteRole)}
                                onChange={(event) => updateField("role", event.target.value)}
                                value={formData.role}
                            >
                                <option value={ClinicianRole.PROVIDER}>Provider</option>
                                <option value={ClinicianRole.NURSE}>Nurse / MA</option>
                                {inviteRole === ClinicianRole.ADMIN ? (
                                    <option value={ClinicianRole.ADMIN}>Clinic Admin (invite)</option>
                                ) : null}
                            </select>
                            {inviteRole ? (
                                <p className="mt-1 text-xs text-muted">Role access is set by your invite.</p>
                            ) : null}
                        </label>
                        <Input label="NPI number (optional)" onChange={(event) => updateField("npiNumber", event.target.value)} value={formData.npiNumber} />
                        <Input label="Password" onChange={(event) => updateField("password", event.target.value)} type="password" value={formData.password} />
                        <Input
                            label="Confirm password"
                            onChange={(event) => updateField("confirmPassword", event.target.value)}
                            type="password"
                            value={formData.confirmPassword}
                        />
                        {error ? <p role="alert" className="rounded-lg bg-risk-soft px-3 py-2 text-sm text-risk-ink md:col-span-2">{error}</p> : null}
                        <div className="md:col-span-2">
                            <Button
                                disabled={submitting || inviteLoading || (invitationToken ? !invitation : !clinicContext)}
                                fullWidth
                                size="lg"
                                type="submit"
                            >
                                {submitting ? "Creating account..." : "Create clinician account"}
                            </Button>
                        </div>
                    </form>}
                    {canChooseExistingAccount && !existingAccountOpen ? (
                        <button ref={existingAccountToggleRef} className="text-left text-sm font-medium text-primary hover:underline" type="button" onClick={() => chooseExistingAccount(true)}>
                            Already have a MediAgent clinician account? Sign in to accept
                        </button>
                    ) : null}
                    {invitationToken ? null : (
                        <div className="text-sm text-muted">
                            Already have a clinician account?{" "}
                            <Link className="font-medium text-primary hover:underline" href="/login">
                                Sign in
                            </Link>
                        </div>
                    )}
                    <div className="text-sm text-muted">
                        Need to onboard a brand-new clinic?{" "}
                        <Link className="font-medium text-primary hover:underline" href="/signup/admin">
                            Create clinic admin account
                        </Link>
                    </div>
                </div>
        </AuthShell>
    );
}

export default function ClinicianSignupPage() {
    return (
        <Suspense fallback={null}>
            <ClinicianSignupPageContent />
        </Suspense>
    );
}
