"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { MedWatchDraftCard } from "@/components/features/medwatch-draft-card";
import { saveBlob } from "@/components/features/form-3500-download-dialog";
import type { ReportStep } from "@/components/features/medwatch-stepper";
import { patientCode, productName, reportTabOf } from "@/components/features/medwatch-report-meta";
import { Badge, ErrorState, Skeleton } from "@/components/ui";
import { ApprovalSeal } from "@/components/ui/approval-seal";
import { Icon } from "@/components/ui/icons";
import {
    amendMedWatchSubmission,
    approveMedWatchDraft,
    discardMedWatchDraft,
    exportMedWatchDraft,
    fetchMedWatchDraft,
    recordMedWatchSubmission,
    updateMedWatchDraft,
    type MedWatchApprovalInput,
    type MedWatchDiscardInput,
    type MedWatchDraft,
    type MedWatchFormData,
    type MedWatchSubmissionInput,
} from "@/services/clinicians";

function ReportSkeleton() {
    return (
        <div aria-label="Loading MedWatch report" className="space-y-5" role="status">
            <Skeleton className="h-4 w-48" variant="text" />
            <Skeleton className="h-8 w-64" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-64 w-full" />
        </div>
    );
}

function initialStep(draft: MedWatchDraft): ReportStep {
    const tab = reportTabOf(draft);
    return tab === "approved" || tab === "submitted" ? "download" : "complete";
}

function ReportContent() {
    const params = useParams<{ draftId: string }>();
    const draftId = params.draftId;
    const router = useRouter();
    const searchParams = useSearchParams();
    const from = searchParams.get("from");
    const listHref = from ? `/medwatch?${from}` : "/medwatch";
    const [draft, setDraft] = useState<MedWatchDraft | null>(null);
    const [step, setStep] = useState<ReportStep>("complete");
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);
    const [busy, setBusy] = useState(false);
    const [notice, setNotice] = useState<string | null>(null);
    const loaded = useRef(false);

    const load = useCallback(async () => {
        setLoading(true);
        setError(false);
        try {
            const result = await fetchMedWatchDraft(draftId);
            setDraft(result);
            if (!loaded.current) {
                loaded.current = true;
                setStep(initialStep(result));
            }
        } catch {
            setError(true);
        } finally {
            setLoading(false);
        }
    }, [draftId]);

    useEffect(() => {
        void load();
    }, [load]);

    /** Run one write with the busy flag held; the card shows any failure it throws. */
    const guarded = useCallback(async <T,>(operation: () => Promise<T>): Promise<T> => {
        setBusy(true);
        setNotice(null);
        try {
            return await operation();
        } finally {
            setBusy(false);
        }
    }, []);

    const save = useCallback(
        (id: string, formData: MedWatchFormData, revision: number) =>
            guarded(async () => {
                setDraft(await updateMedWatchDraft(id, formData, revision));
                setNotice("MedWatch draft changes saved and audited.");
            }),
        [guarded],
    );

    const approve = useCallback(
        (id: string, input: MedWatchApprovalInput) =>
            guarded(async () => {
                setDraft(await approveMedWatchDraft(id, input));
                setNotice("Report approved for export. It was not submitted to the FDA.");
            }),
        [guarded],
    );

    const exportJson = useCallback(
        (id: string) =>
            guarded(async () => {
                const artifact = await exportMedWatchDraft(id);
                saveBlob(
                    new Blob([JSON.stringify(artifact.content, null, 2)], { type: artifact.media_type }),
                    artifact.filename,
                );
                setNotice("Approved report exported locally. No FDA submission was performed.");
            }),
        [guarded],
    );

    const discard = useCallback(
        (id: string, input: MedWatchDiscardInput) =>
            guarded(async () => {
                await discardMedWatchDraft(id, input);
                router.push("/medwatch?tab=discarded");
            }),
        [guarded, router],
    );

    const record = useCallback(
        (id: string, input: MedWatchSubmissionInput & { expectedRevision: number }) =>
            guarded(async () => {
                await recordMedWatchSubmission(id, input);
                setNotice("Submission recorded. The report is now read-only under Submitted. MediAgent sent nothing to FDA.");
                setDraft(await fetchMedWatchDraft(id));
            }),
        [guarded],
    );

    const amend = useCallback(
        (id: string, input: MedWatchSubmissionInput & { amendsId: string; reason: string }) =>
            guarded(async () => {
                await amendMedWatchSubmission(id, input);
                setNotice("Submission record amended. The original record is kept.");
                setDraft(await fetchMedWatchDraft(id));
            }),
        [guarded],
    );

    const pdfDownloaded = useCallback(() => {
        setNotice(
            "Form 3500 PDF downloaded and audited. MediAgent did not submit this report. You submit it to FDA.",
        );
    }, []);

    const tab = draft ? reportTabOf(draft) : null;
    const code = draft ? patientCode(draft) : "";

    return (
        <div className="ma-page space-y-5">
            {loading && !draft ? <ReportSkeleton /> : null}
            {error && !draft ? (
                <ErrorState
                    action={
                        <Link className="text-sm font-semibold text-primary" href={listHref}>
                            Back to MedWatch
                        </Link>
                    }
                    description="This report could not be loaded. It may no longer be available to you."
                    onRetry={() => void load()}
                    title="Unable to load this report"
                />
            ) : null}
            {draft ? (
                <>
                    <div className="space-y-3">
                        <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-sm">
                            <Link className="rounded-md text-muted hover:text-ink" href={listHref}>
                                MedWatch
                            </Link>
                            <Icon aria-hidden="true" className="h-3.5 w-3.5 text-[#94A3B8]" name="chevron" />
                            <span aria-current="page" className="font-mono font-medium text-ink">
                                {code}
                            </span>
                        </nav>
                        <header className="flex flex-wrap items-start justify-between gap-3">
                            <div className="min-w-0">
                                <h1 className="text-[26px] font-semibold leading-tight tracking-[-0.02em] text-ink">
                                    Form FDA 3500 report
                                </h1>
                                <p className="mt-1 text-[15px] text-ink-2">
                                    <span className="font-mono">{code}</span> <span aria-hidden="true">·</span>{" "}
                                    {productName(draft)}
                                </p>
                            </div>
                            <div className="flex flex-wrap items-center gap-2">
                                {tab === "discarded" ? (
                                    <Badge variant="neutral">Discarded</Badge>
                                ) : tab === "submitted" ? (
                                    <Badge variant="info">Submitted outside MediAgent</Badge>
                                ) : tab === "approved" ? (
                                    <ApprovalSeal pill>Approved for export</ApprovalSeal>
                                ) : (
                                    <Badge variant="neutral">Draft</Badge>
                                )}
                                <Badge variant="warning">
                                    {tab === "submitted" ? "Not submitted to FDA by MediAgent" : "Not submitted to FDA"}
                                </Badge>
                            </div>
                        </header>
                        <Link
                            className="inline-flex items-center gap-1.5 text-[13px] font-semibold text-primary hover:text-primary-hover"
                            href={`/adr-reviews/${draft.adrAssessmentId}`}
                        >
                            View ADR case
                        </Link>
                    </div>
                    {notice ? (
                        <p className="ma-enter flex items-start gap-2.5 rounded-xl border border-ok-line bg-ok-soft px-4 py-3 text-sm text-ok-ink" role="status">
                            <Icon className="mt-0.5 h-4 w-4 shrink-0" name="check" />
                            {notice}
                        </p>
                    ) : null}
                    <MedWatchDraftCard
                        busy={busy || loading}
                        draft={draft}
                        key={draft.id}
                        onAmendSubmission={amend}
                        onApprove={approve}
                        onDiscard={discard}
                        onExport={exportJson}
                        onPdfDownloaded={pdfDownloaded}
                        onRecordSubmission={record}
                        onSave={save}
                        workspace={{ onStepChange: setStep, step }}
                    />
                </>
            ) : null}
        </div>
    );
}

export default function MedWatchReportPage() {
    return (
        <Suspense fallback={<ReportSkeleton />}>
            <ReportContent />
        </Suspense>
    );
}
