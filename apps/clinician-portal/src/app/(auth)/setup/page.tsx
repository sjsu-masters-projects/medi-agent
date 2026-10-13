"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSelector } from "react-redux";
import { Button, Input } from "@/components/ui";
import { api } from "@/services/api";
import type { RootState } from "@/store/store";

export default function ClinicSetupPage() {
    const router = useRouter();
    const accessToken = useSelector((state: RootState) => state.auth.accessToken);
    const [npiNumber, setNpiNumber] = useState("");
    const [specialty, setSpecialty] = useState("");
    const [error, setError] = useState("");
    const [submitting, setSubmitting] = useState(false);

    async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        setError("");
        setSubmitting(true);

        if (!accessToken) {
            setError("Please sign in first so we can save your clinician profile.");
            setSubmitting(false);
            return;
        }

        try {
            await api.put(
                "/api/v1/clinicians/me",
                {
                    type1_npi: npiNumber || undefined,
                    specialty,
                },
                { token: accessToken },
            );
            router.replace("/dashboard");
        } catch (submissionError) {
            setError((submissionError as Error).message);
            setSubmitting(false);
        }
    }

    return (
        <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-6 py-12">
            <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 bottom-0 h-[360px] overflow-hidden"><div className="radar-floor" /></div>
            <div className="ma-enter relative w-full max-w-xl space-y-6 rounded-2xl border border-line bg-surface p-8 shadow-[0_24px_48px_-28px_rgba(15,23,42,.28),var(--shadow-card)]">
                <div>
                    <p className="font-mono text-[11px] uppercase tracking-[0.06em] text-primary">Clinician profile</p>
                    <h1 className="mt-1 text-[26px] font-semibold tracking-[-0.02em] text-ink">Complete your profile</h1>
                    <p className="mt-2 text-sm text-muted">Add your specialty and individual NPI, if available.</p>
                </div>
                <form className="space-y-4" onSubmit={handleSubmit}>
                    <Input label="NPI number" onChange={(event) => setNpiNumber(event.target.value)} value={npiNumber} />
                    <Input label="Specialty" onChange={(event) => setSpecialty(event.target.value)} value={specialty} />
                    {error ? <p role="alert" className="rounded-lg bg-risk-soft px-3 py-2 text-sm text-risk-ink">{error}</p> : null}
                    <Button disabled={submitting} fullWidth size="lg" type="submit">
                        {submitting ? "Saving..." : "Save and continue"}
                    </Button>
                </form>
            </div>
        </div>
    );
}
