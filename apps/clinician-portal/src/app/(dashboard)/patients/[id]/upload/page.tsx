"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { HiOutlineArrowLeft, HiOutlineCheckCircle } from "react-icons/hi2";
import { Card } from "@/components/ui";
import { DocumentUploadZone } from "@/components/features/document-upload-zone";

// ── Component ─────────────────────────────────────────────────────────────────

export default function ClinicianUploadPage() {
    const params = useParams();
    const router = useRouter();
    const patientId = params["id"] as string;

    const [uploadedDocIds, setUploadedDocIds] = useState<string[]>([]);
    return (
        <div className="mx-auto max-w-3xl space-y-6">
            {/* Header */}
            <div className="flex items-center gap-4">
                <button
                    aria-label="Back to patient"
                    className="flex items-center gap-2 text-sm text-muted hover:text-ink"
                    onClick={() => router.push(`/patients/${patientId}?tab=documents`)}
                    type="button"
                >
                    <HiOutlineArrowLeft aria-hidden="true" className="h-4 w-4" />
                    Back
                </button>
                <div>
                    <h1 className="text-2xl font-bold text-ink">Upload Patient Document</h1>
                    <p className="text-sm text-muted">
                        Upload clinical notes, lab results, or prescriptions for AI parsing
                    </p>
                </div>
            </div>

            {/* Upload zone */}
            <Card padding="lg">
                <h2 className="mb-4 text-base font-semibold text-ink">Select Files</h2>
                <DocumentUploadZone
                    onComplete={(ids) => setUploadedDocIds(ids)}
                    patientId={patientId}
                />

                {uploadedDocIds.length > 0 && (
                    <div className="mt-4 flex items-center gap-2 rounded-xl border border-ok-line bg-ok-soft px-4 py-3 text-sm text-ok-ink">
                        <HiOutlineCheckCircle aria-hidden="true" className="h-5 w-5" />
                        {uploadedDocIds.length} document{uploadedDocIds.length === 1 ? "" : "s"} uploaded. Check Documents for processing results.
                    </div>
                )}
            </Card>

            {/* Care-plan publication boundary */}
            <Card padding="lg">
                <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                        <h2 className="text-base font-semibold text-ink">Review care plan</h2>
                        <p className="text-sm text-muted">
                            Uploaded instructions are staged as evidence-backed draft items. Review,
                            edit, and approve the complete plan before anything appears in Today.
                        </p>
                    </div>
                    <button
                        className="rounded-lg border border-line-strong px-4 py-2 text-sm font-medium text-ink-2 hover:bg-surface-2"
                        onClick={() => router.push(`/patients/${patientId}?tab=care-plan`)}
                        type="button"
                    >
                        Open Care Plan
                    </button>
                </div>
            </Card>

            {/* Done button */}
            <div className="flex justify-end">
                <button
                    className="rounded-xl border border-line-strong px-6 py-2.5 text-sm font-medium text-ink-2 hover:bg-surface-2"
                    id="upload-done-btn"
                    onClick={() => router.push(`/patients/${patientId}?tab=documents`)}
                    type="button"
                >
                    Done
                </button>
            </div>
        </div>
    );
}
