"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useSelector } from "react-redux";
import { Button, Card, Input } from "@/components/ui";
import { api } from "@/services/api";
import type { RootState } from "@/store/store";

export default function ClinicSetupPage() {
    const router = useRouter();
    const accessToken = useSelector((state: RootState) => state.auth.accessToken);
    const [clinicName, setClinicName] = useState("City Health Primary Care");
    const [npiNumber, setNpiNumber] = useState("1234567890");
    const [specialty, setSpecialty] = useState("Primary Care");
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
                    clinic_name: clinicName,
                    npi_number: npiNumber,
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
        <div className="flex min-h-screen items-center justify-center bg-gray-50 px-6 py-12">
            <Card className="w-full max-w-xl space-y-6" padding="lg">
                <div>
                    <p className="text-sm font-medium text-blue-600">Clinic setup</p>
                    <h1 className="mt-1 text-3xl font-bold text-gray-900">Configure your workspace</h1>
                </div>
                <form className="space-y-4" onSubmit={handleSubmit}>
                    <Input label="Clinic name" onChange={(event) => setClinicName(event.target.value)} value={clinicName} />
                    <Input label="NPI number" onChange={(event) => setNpiNumber(event.target.value)} value={npiNumber} />
                    <Input label="Specialty" onChange={(event) => setSpecialty(event.target.value)} value={specialty} />
                    {error ? <p className="text-sm text-red-600">{error}</p> : null}
                    <Button disabled={submitting} fullWidth type="submit">
                        {submitting ? "Saving..." : "Save and continue"}
                    </Button>
                </form>
            </Card>
        </div>
    );
}
