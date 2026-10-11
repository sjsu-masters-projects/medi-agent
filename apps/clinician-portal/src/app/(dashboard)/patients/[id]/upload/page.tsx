"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Icon } from "@/components/ui/icons";
import { DocumentUploadZone } from "@/components/features/document-upload-zone";

// ── Component ─────────────────────────────────────────────────────────────────

export default function ClinicianUploadPage() {
    const params = useParams();
    const router = useRouter();
    const patientId = params["id"] as string;

    const [uploadedDocIds, setUploadedDocIds] = useState<string[]>([]);
    return (
        <div className="ma-page space-y-5">
            {/* Header */}
            <div className="space-y-3">
                <button
                    aria-label="Back to patient"
                    className="ma-press -ml-2 inline-flex h-8 items-center gap-1.5 rounded-lg px-2 text-[13px] font-medium text-muted hover:bg-sunken hover:text-ink"
                    onClick={() => router.push(`/patients/${patientId}?tab=documents`)}
                    type="button"
                >
                    <Icon name="back" aria-hidden="true" className="h-4 w-4" />
                    Back
                </button>
                <div>
                    <h1 className="text-2xl font-semibold tracking-[-0.02em] text-ink">Upload Patient Document</h1>
                    <p className="mt-1 text-sm text-muted">
                        Upload clinical notes, lab results, or prescriptions for AI parsing
                    </p>
                </div>
            </div>

            <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
                {/* Upload zone */}
                <section className="rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]">
                    <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
                        <h2 className="text-[15px] font-semibold text-ink">Select Files</h2>
                    </div>
                    <div className="p-5">
                        <DocumentUploadZone
                            onComplete={(ids) => setUploadedDocIds(ids)}
                            patientId={patientId}
                        />

                        {uploadedDocIds.length > 0 && (
                            <div className="ma-enter mt-4 flex items-start gap-2.5 rounded-xl border border-ok-line bg-ok-soft px-4 py-3 text-sm text-ok-ink">
                                <Icon name="check" aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
                                <span>
                                    {uploadedDocIds.length} document{uploadedDocIds.length === 1 ? "" : "s"} uploaded. Check Documents for processing results.
                                </span>
                            </div>
                        )}
                    </div>
                </section>

                {/* Care-plan publication boundary */}
                <section className="rounded-2xl border border-line bg-surface p-5 shadow-[var(--shadow-card)]">
                    <div className="flex items-start gap-3">
                        <span aria-hidden="true" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-warn-soft text-warn-ink">
                            <Icon name="shield" className="h-[18px] w-[18px]" />
                        </span>
                        <div className="min-w-0">
                            <h2 className="text-[15px] font-semibold text-ink">Review care plan</h2>
                            <p className="mt-1 text-sm leading-relaxed text-muted">
                                Uploaded instructions are staged as evidence-backed draft items. Review,
                                edit, and approve the complete plan before anything appears in Today.
                            </p>
                        </div>
                    </div>
                    <button
                        className="ma-press mt-4 inline-flex h-[34px] items-center gap-2 rounded-[9px] border border-line-strong bg-surface px-4 text-[13px] font-medium text-ink-2 hover:bg-surface-2 hover:text-ink"
                        onClick={() => router.push(`/patients/${patientId}?tab=care-plan`)}
                        type="button"
                    >
                        Open Care Plan
                        <Icon name="arrow" aria-hidden="true" className="h-4 w-4" />
                    </button>
                </section>
            </div>

            {/* Done button */}
            <div className="flex justify-end">
                <button
                    className="ma-press h-[42px] rounded-[10px] border border-line-strong bg-surface px-[18px] text-sm font-medium text-ink-2 hover:bg-surface-2 hover:text-ink"
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
