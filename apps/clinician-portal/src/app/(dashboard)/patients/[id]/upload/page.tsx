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

            {/* Care-plan publication boundary */}
            <Card padding="lg">
                <div className="flex items-center justify-between">
                    <div>
                        <h2 className="text-base font-semibold text-gray-900">Review care plan</h2>
                        <p className="text-sm text-gray-500">
                            Uploaded instructions are staged as evidence-backed draft items. Review,
                            edit, and approve the complete plan before anything appears in Today.
                        </p>
                    </div>
                    <button
                        className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
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
