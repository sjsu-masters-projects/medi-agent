"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSelector } from "react-redux";
import { Button, Card, Input } from "@/components/ui";
import { api } from "@/services/api";
import type { RootState } from "@/store/store";

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

export default function MFASetupPage() {
    const router = useRouter();
    const token = useSelector((state: RootState) => state.auth.token);
    const [step, setStep] = useState<MFAStep>("loading");
    const [enrollData, setEnrollData] = useState<EnrollData | null>(null);
    const [factors, setFactors] = useState<Factor[]>([]);
    const [code, setCode] = useState("");
    const [error, setError] = useState("");
    const [submitting, setSubmitting] = useState(false);

    useEffect(() => {
        if (!token) {
            return;
        }

        async function checkFactors() {
            try {
                const result = await api.get<{ factors: Factor[] }>("/api/v1/auth/mfa/factors", { token: token! });
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
    }, [token]);

    async function handleEnroll() {
        if (!token) {
            return;
        }

        setError("");
        setSubmitting(true);
        try {
            const result = await api.post<EnrollData>(
                "/api/v1/auth/mfa/enroll",
                { friendly_name: "Authenticator" },
                { token },
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
        if (!token || !enrollData) {
            return;
        }

        setError("");
        setSubmitting(true);
        try {
            await api.post(
                "/api/v1/auth/mfa/verify",
                { factor_id: enrollData.factor_id, code },
                { token },
            );
            setStep("success");
        } catch (e) {
            setError((e as Error).message);
        } finally {
            setSubmitting(false);
        }
    }

    async function handleUnenroll(factorId: string) {
        if (!token) {
            return;
        }

        setError("");
        try {
            await api.post("/api/v1/auth/mfa/unenroll", { factor_id: factorId }, { token });
            setFactors((current) => current.filter((f) => f.id !== factorId));
            setStep("enroll");
        } catch (e) {
            setError((e as Error).message);
        }
    }

    if (step === "loading") {
        return (
            <div className="mx-auto max-w-lg py-20 text-center">
                <p className="text-sm text-slate-500">Checking MFA status...</p>
            </div>
        );
    }

    return (
        <div className="mx-auto max-w-lg space-y-6">
            <div>
                <button
                    className="mb-4 text-sm font-medium text-blue-600 hover:underline"
                    onClick={() => router.push("/settings")}
                    type="button"
                >
                    &larr; Back to Settings
                </button>
                <h1 className="text-2xl font-bold text-slate-900">Multi-Factor Authentication</h1>
                <p className="mt-1 text-sm text-slate-500">
                    Add an extra layer of security to your account using a TOTP authenticator app.
                </p>
            </div>

            {error ? <p className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p> : null}

            {step === "already_enrolled" ? (
                <Card className="space-y-4">
                    <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-green-100 text-lg">
                            &#x2713;
                        </div>
                        <div>
                            <p className="font-semibold text-slate-900">MFA is enabled</p>
                            <p className="text-sm text-slate-500">
                                Your account is protected with {factors.length} authenticator{factors.length > 1 ? "s" : ""}.
                            </p>
                        </div>
                    </div>
                    {factors.map((factor) => (
                        <div className="flex items-center justify-between rounded-lg border border-slate-200 px-4 py-3" key={factor.id}>
                            <div>
                                <p className="text-sm font-medium text-slate-700">{factor.friendly_name ?? "Authenticator"}</p>
                                <p className="text-xs text-slate-400">
                                    Added {factor.created_at ? new Date(factor.created_at).toLocaleDateString() : "—"}
                                </p>
                            </div>
                            <button
                                className="text-sm font-medium text-red-600 hover:underline"
                                onClick={() => handleUnenroll(factor.id)}
                                type="button"
                            >
                                Remove
                            </button>
                        </div>
                    ))}
                </Card>
            ) : null}

            {step === "enroll" ? (
                <Card className="space-y-4">
                    <div>
                        <h2 className="text-lg font-semibold text-slate-900">Set up authenticator</h2>
                        <p className="mt-1 text-sm text-slate-500">
                            You will need an authenticator app like Google Authenticator, Authy, or 1Password.
                        </p>
                    </div>
                    <Button disabled={submitting} onClick={handleEnroll}>
                        {submitting ? "Setting up..." : "Begin setup"}
                    </Button>
                </Card>
            ) : null}

            {step === "verify" && enrollData ? (
                <Card className="space-y-5">
                    <div>
                        <h2 className="text-lg font-semibold text-slate-900">Scan QR code</h2>
                        <p className="mt-1 text-sm text-slate-500">
                            Open your authenticator app and scan the QR code below, then enter the 6-digit code.
                        </p>
                    </div>
                    <div className="flex justify-center rounded-xl bg-white p-4">
                        {/* eslint-disable-next-line @next/next/no-img-element -- QR code is a data URI, not optimizable */}
                        <img alt="TOTP QR Code" className="h-48 w-48" src={enrollData.totp.qr_code} />
                    </div>
                    <div className="rounded-lg bg-slate-50 px-4 py-3">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Manual entry key</p>
                        <p className="mt-1 select-all font-mono text-sm text-slate-700">{enrollData.totp.secret}</p>
                    </div>
                    <form className="space-y-4" onSubmit={handleVerify}>
                        <Input
                            autoComplete="one-time-code"
                            inputMode="numeric"
                            label="6-digit code"
                            maxLength={6}
                            onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
                            placeholder="000000"
                            value={code}
                        />
                        <Button disabled={submitting || code.length !== 6} fullWidth type="submit">
                            {submitting ? "Verifying..." : "Verify and enable"}
                        </Button>
                    </form>
                </Card>
            ) : null}

            {step === "success" ? (
                <Card className="space-y-4 text-center">
                    <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-green-100 text-3xl text-green-600">
                        &#x2713;
                    </div>
                    <h2 className="text-lg font-semibold text-slate-900">MFA enabled successfully</h2>
                    <p className="text-sm text-slate-500">
                        Your account is now protected with two-factor authentication.
                    </p>
                    <Button onClick={() => router.push("/settings")}>Back to Settings</Button>
                </Card>
            ) : null}
        </div>
    );
}
