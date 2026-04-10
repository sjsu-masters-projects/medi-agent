"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { HiOutlineArrowLeft, HiOutlineCheckCircle } from "react-icons/hi2";
import { Card } from "@/components/ui";
import { DocumentUploadZone } from "@/components/features/document-upload-zone";
import { setPatientObligation } from "@/services/clinicians";

// ── Obligation form types ─────────────────────────────────────────────────────

const OBLIGATION_TYPES = [
    { value: "diet", label: "Diet / Nutrition" },
    { value: "exercise", label: "Exercise / Physical Activity" },
    { value: "custom", label: "Custom" },
] as const;

const FREQUENCIES = [
    "Daily",
    "Twice daily",
    "3x per week",
    "Weekly",
    "With each meal",
    "Before bed",
    "As needed",
] as const;

type ObligationType = (typeof OBLIGATION_TYPES)[number]["value"];

interface ObligationFormState {
    obligation_type: ObligationType;
    description: string;
    frequency: string;
    notes: string;
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function ClinicianUploadPage() {
    const params = useParams();
    const router = useRouter();
    const patientId = params["id"] as string;

    const [uploadedDocIds, setUploadedDocIds] = useState<string[]>([]);
    const [showObligationForm, setShowObligationForm] = useState(false);
    const [obligationSubmitting, setObligationSubmitting] = useState(false);
    const [obligationSuccess, setObligationSuccess] = useState(false);
    const [obligationError, setObligationError] = useState<string | null>(null);

    const [obligationForm, setObligationForm] = useState<ObligationFormState>({
        obligation_type: "diet",
        description: "",
        frequency: "Daily",
        notes: "",
    });

    async function handleObligationSubmit(e: React.FormEvent) {
        e.preventDefault();
        setObligationSubmitting(true);
        setObligationError(null);

        try {
            await setPatientObligation(patientId, {
                obligation_type: obligationForm.obligation_type,
                description: obligationForm.description,
                frequency: obligationForm.frequency,
                notes: obligationForm.notes || undefined,
            });
            setObligationSuccess(true);
        } catch (err) {
            setObligationError(err instanceof Error ? err.message : "Failed to set obligation");
        } finally {
            setObligationSubmitting(false);
        }
    }

    function resetObligationForm() {
        setObligationForm({
            obligation_type: "diet",
            description: "",
            frequency: "Daily",
            notes: "",
        });
        setObligationSuccess(false);
        setObligationError(null);
    }

    return (
        <div className="mx-auto max-w-3xl space-y-6">
            {/* Header */}
            <div className="flex items-center gap-4">
                <button
                    aria-label="Back to patient"
                    className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-900"
                    onClick={() => router.back()}
                    type="button"
                >
                    <HiOutlineArrowLeft aria-hidden="true" className="h-4 w-4" />
                    Back
                </button>
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Upload Patient Document</h1>
                    <p className="text-sm text-gray-500">
                        Upload clinical notes, lab results, or prescriptions for AI parsing
                    </p>
                </div>
            </div>

            {/* Upload zone */}
            <Card padding="lg">
                <h2 className="mb-4 text-base font-semibold text-gray-900">Select Files</h2>
                <DocumentUploadZone
                    onComplete={(ids) => setUploadedDocIds(ids)}
                    patientId={patientId}
                />

                {uploadedDocIds.length > 0 && (
                    <div className="mt-4 flex items-center gap-2 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
                        <HiOutlineCheckCircle aria-hidden="true" className="h-5 w-5" />
                        {uploadedDocIds.length} document(s) uploaded and queued for AI parsing.
                    </div>
                )}
            </Card>

            {/* Obligation form toggle */}
            <Card padding="lg">
                <div className="flex items-center justify-between">
                    <div>
                        <h2 className="text-base font-semibold text-gray-900">
                            Set Patient Obligation (Optional)
                        </h2>
                        <p className="text-sm text-gray-500">
                            Assign a diet, exercise, or monitoring obligation for this patient
                        </p>
                    </div>
                    <button
                        aria-expanded={showObligationForm}
                        className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                        id="toggle-obligation-form-btn"
                        onClick={() => setShowObligationForm((prev) => !prev)}
                        type="button"
                    >
                        {showObligationForm ? "Cancel" : "Add Obligation"}
                    </button>
                </div>

                {showObligationForm && (
                    <form
                        aria-label="Set patient obligation form"
                        className="mt-6 space-y-4"
                        id="obligation-form"
                        onSubmit={handleObligationSubmit}
                    >
                        {/* Type */}
                        <div>
                            <label
                                className="mb-1 block text-sm font-medium text-gray-700"
                                htmlFor="obligation-type"
                            >
                                Obligation Type <span className="text-red-500">*</span>
                            </label>
                            <select
                                className="w-full rounded-xl border border-gray-300 bg-white px-3 py-2.5 text-sm text-gray-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                id="obligation-type"
                                onChange={(e) =>
                                    setObligationForm((prev) => ({
                                        ...prev,
                                        obligation_type: e.target.value as ObligationType,
                                    }))
                                }
                                required
                                value={obligationForm.obligation_type}
                            >
                                {OBLIGATION_TYPES.map(({ value, label }) => (
                                    <option key={value} value={value}>
                                        {label}
                                    </option>
                                ))}
                            </select>
                        </div>

                        {/* Description */}
                        <div>
                            <label
                                className="mb-1 block text-sm font-medium text-gray-700"
                                htmlFor="obligation-description"
                            >
                                Description <span className="text-red-500">*</span>
                            </label>
                            <textarea
                                className="w-full rounded-xl border border-gray-300 px-3 py-2.5 text-sm text-gray-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                id="obligation-description"
                                minLength={1}
                                onChange={(e) =>
                                    setObligationForm((prev) => ({
                                        ...prev,
                                        description: e.target.value,
                                    }))
                                }
                                placeholder="e.g. Walk 30 minutes after each meal"
                                required
                                rows={3}
                                value={obligationForm.description}
                            />
                        </div>

                        {/* Frequency */}
                        <div>
                            <label
                                className="mb-1 block text-sm font-medium text-gray-700"
                                htmlFor="obligation-frequency"
                            >
                                Frequency <span className="text-red-500">*</span>
                            </label>
                            <select
                                className="w-full rounded-xl border border-gray-300 bg-white px-3 py-2.5 text-sm text-gray-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                id="obligation-frequency"
                                onChange={(e) =>
                                    setObligationForm((prev) => ({
                                        ...prev,
                                        frequency: e.target.value,
                                    }))
                                }
                                required
                                value={obligationForm.frequency}
                            >
                                {FREQUENCIES.map((f) => (
                                    <option key={f} value={f}>
                                        {f}
                                    </option>
                                ))}
                            </select>
                        </div>

                        {/* Notes */}
                        <div>
                            <label
                                className="mb-1 block text-sm font-medium text-gray-700"
                                htmlFor="obligation-notes"
                            >
                                Additional Notes (optional)
                            </label>
                            <textarea
                                className="w-full rounded-xl border border-gray-300 px-3 py-2.5 text-sm text-gray-700 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
                                id="obligation-notes"
                                onChange={(e) =>
                                    setObligationForm((prev) => ({
                                        ...prev,
                                        notes: e.target.value,
                                    }))
                                }
                                placeholder="Any special instructions or context…"
                                rows={2}
                                value={obligationForm.notes}
                            />
                        </div>

                        {obligationError && (
                            <p className="text-sm text-red-600" role="alert">
                                {obligationError}
                            </p>
                        )}

                        {obligationSuccess && (
                            <div className="flex items-center gap-2 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
                                <HiOutlineCheckCircle aria-hidden="true" className="h-5 w-5" />
                                Obligation created successfully
                            </div>
                        )}

                        {obligationSuccess && (
                            <button
                                className="w-full rounded-xl border border-green-300 px-4 py-2.5 text-sm font-semibold text-green-700 hover:bg-green-50"
                                onClick={resetObligationForm}
                                type="button"
                            >
                                Add Another Obligation
                            </button>
                        )}

                        <button
                            className="flex w-full items-center justify-center rounded-xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
                            disabled={
                                obligationSubmitting ||
                                !obligationForm.description.trim()
                            }
                            id="obligation-submit-btn"
                            type="submit"
                        >
                            {obligationSubmitting ? "Creating…" : "Create Obligation"}
                        </button>
                    </form>
                )}
            </Card>

            {/* Done button */}
            <div className="flex justify-end">
                <button
                    className="rounded-xl border border-gray-300 px-6 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
                    id="upload-done-btn"
                    onClick={() => router.back()}
                    type="button"
                >
                    Done
                </button>
            </div>
        </div>
    );
}
