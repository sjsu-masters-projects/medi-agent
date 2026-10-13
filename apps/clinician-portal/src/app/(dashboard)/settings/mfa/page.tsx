"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useDispatch, useSelector } from "react-redux";
import { Button, Card, Input } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { api } from "@/services/api";
import { writeStoredSession } from "@/services/auth-session";
import { hydrateSession, type ClinicianAuthSession } from "@/store/slices/auth-slice";
import type { RootState } from "@/store/store";
import { formatClinicianDate } from "@/utils/dates";

type MFAStep = "loading" | "already_enrolled" | "enroll" | "verify" | "success";

interface EnrollData {
    factor_id: string;
    totp: {
        qr_code: string;
        secret: string;
        uri: string;
    };
    friendly_name: string;
}

interface Factor {
    id: string;
    friendly_name: string | null;
    factor_type: string;
    status: string;
    created_at: string | null;
}

interface MFAVerifyResponse {
    access_token: string;
    expires_at: number;
    refresh_token: string;
    token_type: string;
}

interface RefreshResponse {
    tokens: {
        access_token: string;
        expires_at: number;
        refresh_token: string;
    };
    user: {
        email: string;
        id: string;
        role: "clinician";
    };
}

const footerClass =
    "flex flex-wrap items-center justify-end gap-3 rounded-b-2xl border-t border-line bg-surface-2 px-5 py-3";

function StepHeader({ children, number }: { children: React.ReactNode; number: number }) {
    return (
        <div className="flex items-start gap-3 border-b border-line px-5 py-4">
            <span aria-hidden="true" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-primary-line bg-primary-tint font-mono text-[13px] font-medium text-primary">
                {number}
            </span>
            <div className="min-w-0">{children}</div>
        </div>
    );
}

export default function MFASetupPage() {
    const router = useRouter();
    const dispatch = useDispatch();
    const { accessToken, refreshToken, user } = useSelector((state: RootState) => state.auth);
    const [step, setStep] = useState<MFAStep>("loading");
    const [enrollData, setEnrollData] = useState<EnrollData | null>(null);
    const [factors, setFactors] = useState<Factor[]>([]);
    const [code, setCode] = useState("");
    const [error, setError] = useState("");
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        if (!accessToken || !refreshToken) {
            return;
        }
        const currentAccessToken = accessToken;
        const currentRefreshToken = refreshToken;

        async function checkFactors() {
            try {
                const result = await api.get<{ factors: Factor[] }>("/api/v1/auth/mfa/factors", {
                    headers: { "X-Refresh-Token": currentRefreshToken },
                    token: currentAccessToken,
                });
                const verified = result.factors.filter((f) => f.status === "verified");
                if (verified.length > 0) {
                    setFactors(verified);
                    setStep("already_enrolled");
                } else {
                    setStep("enroll");
                }
            } catch {
                setStep("enroll");
            }
        }

        void checkFactors();
    }, [accessToken, refreshToken]);

    async function handleEnroll() {
        if (!accessToken || !refreshToken) {
            return;
        }
        const currentAccessToken = accessToken;
        const currentRefreshToken = refreshToken;

        setError("");
        setSubmitting(true);
        try {
            const result = await api.post<EnrollData>(
                "/api/v1/auth/mfa/enroll",
                { friendly_name: "Authenticator" },
                {
                    headers: { "X-Refresh-Token": currentRefreshToken },
                    token: currentAccessToken,
                },
            );
            setEnrollData(result);
            setStep("verify");
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setSubmitting(false);
        }
    }

    async function handleVerify(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (!accessToken || !refreshToken || !enrollData || !user) {
            return;
        }
        const currentAccessToken = accessToken;
        const currentRefreshToken = refreshToken;

        setError("");
        setSubmitting(true);
        try {
            const response = await api.post<MFAVerifyResponse>(
                "/api/v1/auth/mfa/verify",
                { factor_id: enrollData.factor_id, code },
                {
                    headers: { "X-Refresh-Token": currentRefreshToken },
                    token: currentAccessToken,
                },
            );
            const session: ClinicianAuthSession = {
                accessToken: response.access_token,
                expiresAt: response.expires_at,
                refreshToken: response.refresh_token,
                user,
            };
            writeStoredSession(session);
            dispatch(hydrateSession(session));
            setStep("success");
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setSubmitting(false);
        }
    }

    async function handleUnenroll(factorId: string) {
        if (!accessToken || !refreshToken) {
            return;
        }
        const currentAccessToken = accessToken;
        const currentRefreshToken = refreshToken;

        setError("");
        try {
            await api.post("/api/v1/auth/mfa/unenroll", { factor_id: factorId }, {
                headers: { "X-Refresh-Token": currentRefreshToken },
                token: currentAccessToken,
            });
            const refreshed = await api.post<RefreshResponse>("/api/v1/auth/refresh", {
                expected_role: "clinician",
                refresh_token: currentRefreshToken,
            });
            const session: ClinicianAuthSession = {
                accessToken: refreshed.tokens.access_token,
                expiresAt: refreshed.tokens.expires_at,
                refreshToken: refreshed.tokens.refresh_token,
                user: refreshed.user,
            };
            writeStoredSession(session);
            dispatch(hydrateSession(session));
            setFactors((current) => current.filter((f) => f.id !== factorId));
            setStep("enroll");
        } catch (e) {
            setError((e as Error).message);
        }
    }

    if (step === "loading") {
        return (
            <div className="ma-page">
                <div className="flex max-w-[720px] items-center justify-center rounded-2xl border border-line bg-surface px-6 py-16 text-center shadow-[var(--shadow-card)]">
                    <p className="text-sm text-muted">Checking MFA status...</p>
                </div>
            </div>
        );
    }

    return (
        <div className="ma-page space-y-5">
            <div>
                <button
                    className="ma-press mb-3 inline-flex h-8 items-center rounded-lg px-2 -ml-2 text-[13px] font-medium text-primary hover:bg-primary-tint"
                    onClick={() => router.push("/settings")}
                    type="button"
                >
                    &larr; Back to Settings
                </button>
                <h1 className="text-2xl font-semibold tracking-[-0.02em] text-ink">Multi-Factor Authentication</h1>
                <p className="mt-1 max-w-[72ch] text-sm text-muted">
                    Add an extra layer of security using an authenticator app that generates one-time codes.
                </p>
            </div>

            <div className="max-w-[720px] space-y-5">
                {error ? (
                    <p role="alert" className="flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink">
                        <Icon aria-hidden="true" name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
                        <span>{error}</span>
                    </p>
                ) : null}

                {step === "already_enrolled" ? (
                    <Card className="ma-enter" padding="none">
                        <div className="flex items-center gap-3 border-b border-line px-5 py-4">
                            <span aria-hidden="true" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-ok-tint text-ok-ink">
                                <Icon name="shield" className="h-4 w-4" />
                            </span>
                            <div>
                                <p className="text-[15px] font-semibold text-ink">MFA is enabled</p>
                                <p className="mt-0.5 text-[13px] text-muted">
                                    Your account is protected with {factors.length} authenticator{factors.length > 1 ? "s" : ""}.
                                </p>
                            </div>
                        </div>
                        <ul className="divide-y divide-line">
                            {factors.map((factor) => (
                                <li className="flex flex-wrap items-center justify-between gap-3 px-5 py-4" key={factor.id}>
                                    <div className="flex min-w-0 items-center gap-3">
                                        <span aria-hidden="true" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-sunken text-ink-2">
                                            <Icon name="clock" className="h-4 w-4" />
                                        </span>
                                        <div className="min-w-0">
                                            <p className="text-sm font-medium text-ink">{factor.friendly_name ?? "Authenticator"}</p>
                                            <p className="text-[13px] text-muted">
                                                Added {factor.created_at ? formatClinicianDate(factor.created_at) : "—"}
                                            </p>
                                        </div>
                                    </div>
                                    <Button
                                        onClick={() => handleUnenroll(factor.id)}
                                        size="sm"
                                        variant="danger"
                                    >
                                        Remove
                                    </Button>
                                </li>
                            ))}
                        </ul>
                    </Card>
                ) : null}

                {step === "enroll" ? (
                    <Card className="ma-enter" padding="none">
                        <StepHeader number={1}>
                            <h2 className="text-[15px] font-semibold text-ink">Set up authenticator</h2>
                            <p className="mt-0.5 text-[13px] text-muted">
                                You will need an authenticator app like Google Authenticator, Authy, or 1Password.
                            </p>
                        </StepHeader>
                        <div className={footerClass}>
                            <Button disabled={submitting} onClick={handleEnroll}>
                                {submitting ? "Setting up..." : "Begin setup"}
                            </Button>
                        </div>
                    </Card>
                ) : null}

                {step === "verify" && enrollData ? (
                    <Card className="ma-enter" padding="none">
                        <StepHeader number={2}>
                            <h2 className="text-[15px] font-semibold text-ink">Scan QR code</h2>
                            <p className="mt-0.5 text-[13px] text-muted">
                                Open your authenticator app and scan the QR code below, then enter the 6-digit code.
                            </p>
                        </StepHeader>
                        <div className="px-5 pt-5">
                            <div className="grid gap-4 rounded-xl bg-sunken p-4 sm:grid-cols-[auto_minmax(0,1fr)] sm:items-center">
                                <div className="flex justify-center rounded-xl border border-line bg-surface p-3">
                                    {/* eslint-disable-next-line @next/next/no-img-element -- QR code is a data URI, not optimizable */}
                                    <img alt="TOTP QR Code" className="h-48 w-48" src={enrollData.totp.qr_code} />
                                </div>
                                <div className="min-w-0">
                                    <p className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">Manual entry key</p>
                                    <p className="mt-1.5 select-all break-all rounded-[10px] border border-line-strong bg-surface px-3 py-2 font-mono text-sm text-ink">{enrollData.totp.secret}</p>
                                </div>
                            </div>
                        </div>
                        <form onSubmit={handleVerify}>
                            <div className="px-5 py-5">
                                <Input
                                    autoComplete="one-time-code"
                                    className="font-mono text-base tracking-[0.4em]"
                                    inputMode="numeric"
                                    label="6-digit code"
                                    maxLength={6}
                                    onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
                                    placeholder="000000"
                                    value={code}
                                />
                            </div>
                            <div className={footerClass}>
                                <Button disabled={submitting || code.length !== 6} type="submit">
                                    {submitting ? "Verifying..." : "Verify and enable"}
                                </Button>
                            </div>
                        </form>
                    </Card>
                ) : null}

                {step === "success" ? (
                    <Card className="ma-enter space-y-3 py-10 text-center" padding="lg">
                        <div aria-hidden="true" className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-ok-tint text-ok-ink">
                            <Icon name="shield" className="h-6 w-6" />
                        </div>
                        <h2 className="text-[15px] font-semibold text-ink">MFA enabled successfully</h2>
                        <p className="text-sm text-muted">
                            Your account is now protected with two-factor authentication.
                        </p>
                        <div className="pt-2">
                            <Button onClick={() => router.push("/settings")}>Back to Settings</Button>
                        </div>
                    </Card>
                ) : null}
            </div>
        </div>
    );
}
