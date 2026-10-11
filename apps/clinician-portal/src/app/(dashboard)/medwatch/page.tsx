"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ADRReviewCard } from "@/components/features/adr-review-card";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { ProcessingDots } from "@/components/ui/motion";
import {
    fetchADRReviewQueue,
    reviewADRAssessment,
    type ADRReviewDecisionInput,
    type ADRReviewQueueItem,
} from "@/services/clinicians";

function LoadingQueue() {
    return (
        <div className="space-y-5" aria-label="Loading ADR reviews">
            {Array.from({ length: 2 }).map((_, index) => (
                <div
                    className="rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]"
                    key={index}
                >
                    <div className="flex items-center justify-between gap-3 border-b border-line px-6 py-4">
                        <div className="space-y-2">
                            <Skeleton className="h-5 w-40" variant="text" />
                            <Skeleton className="h-3 w-28" variant="text" />
                        </div>
                        <Skeleton className="h-6 w-20" />
                    </div>
                    <div className="grid gap-6 p-6 xl:grid-cols-[minmax(0,1fr)_360px]">
                        <div className="space-y-3">
                            <Skeleton className="h-4 w-32" variant="text" />
                            <Skeleton className="h-4 w-3/4" variant="text" />
                            <Skeleton className="h-16 w-full" />
                            <Skeleton className="h-16 w-full" />
                        </div>
                        <div className="space-y-3">
                            <Skeleton className="h-20 w-full" />
                            <Skeleton className="h-28 w-full" />
                        </div>
                    </div>
                </div>
            ))}
        </div>
    );
}

export default function MedWatchPage() {
    const [items, setItems] = useState<ADRReviewQueueItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [submittingId, setSubmittingId] = useState<string | null>(null);
    const [notice, setNotice] = useState<string | null>(null);
    const [reviewError, setReviewError] = useState<string | null>(null);
    const queuePending = useRef(false);
    const reviewPending = useRef(false);

    const loadQueue = useCallback(async () => {
        if (queuePending.current) return;
        queuePending.current = true;
        setLoading(true);
        setError(null);
        try {
            setItems(await fetchADRReviewQueue());
        } catch {
            setError(
                "Unable to refresh ADR assessments. Try loading the queue again.",
            );
        } finally {
            queuePending.current = false;
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        void loadQueue();
    }, [loadQueue]);

    const reviewAssessment = useCallback(
        async (assessmentId: string, input: ADRReviewDecisionInput) => {
            if (reviewPending.current || queuePending.current || error) {
                throw new Error(
                    "Refresh the queue before reviewing an assessment.",
                );
            }
            reviewPending.current = true;
            setSubmittingId(assessmentId);
            setReviewError(null);
            setNotice(null);
            try {
                await reviewADRAssessment(assessmentId, input);
                // A confirmed terminal write must not remain available for resubmission.
                if (input.action !== "request_information") {
                    setItems((current) =>
                        current.filter((item) => item.id !== assessmentId),
                    );
                }
                setNotice(
                    input.action === "request_information"
                        ? "Information request saved and audited."
                        : "ADR review saved and audited.",
                );
                await loadQueue();
            } catch {
                const message =
                    "Unable to save the ADR review. Your draft is retained. Try again.";
                setReviewError(message);
                throw new Error(message);
            } finally {
                reviewPending.current = false;
                setSubmittingId(null);
            }
        },
        [error, loadQueue],
    );

    const initialLoad = loading && items.length === 0;

    return (
        <div className="ma-page space-y-5">
            {/* Header band: Risk Radar layout without the perspective floor */}
            <section
                aria-label="ADR review summary"
                className="relative flex flex-wrap items-end justify-between gap-x-10 gap-y-6 overflow-hidden rounded-[20px] border border-line bg-surface px-7 py-[26px] shadow-[var(--shadow-card)]"
            >
                <div className="flex min-w-0 max-w-[72ch] flex-col gap-1.5">
                    <p className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">
                        Pharmacovigilance
                    </p>
                    <h1 className="text-[34px] font-semibold leading-[1.05] tracking-[-0.025em] text-ink">
                        ADR Review Queue
                    </h1>
                    <p className="text-[15px] leading-relaxed text-ink-2">
                        Review possible adverse drug reactions against patient evidence. Naranjo scores support your review; they do not make a clinical decision.
                    </p>
                </div>
                <div className="flex flex-wrap items-end gap-x-9 gap-y-5">
                    <dl className="flex flex-wrap gap-x-9 gap-y-4">
                        <div className="flex flex-col-reverse gap-0.5">
                            <dt className="text-[13px] text-muted">
                                Pending ADR reviews
                            </dt>
                            <dd className="font-mono text-[28px] font-medium leading-tight text-warn-ink">
                                {initialLoad ? (
                                    <Skeleton className="h-8 w-14" />
                                ) : loading || error ? (
                                    "—"
                                ) : (
                                    items.length
                                )}
                            </dd>
                        </div>
                        <div className="flex flex-col-reverse gap-0.5">
                            <dt className="text-[13px] text-muted">Scoring</dt>
                            <dd className="flex min-h-[35px] max-w-[20ch] items-end text-[15px] font-semibold leading-snug text-ink">
                                Naranjo assessment support
                            </dd>
                        </div>
                        <div className="flex flex-col-reverse gap-0.5">
                            <dt className="text-[13px] text-muted">
                                MedWatch status
                            </dt>
                            <dd className="flex min-h-[35px] max-w-[22ch] items-end text-[15px] font-semibold leading-snug text-ink">
                                ADR review does not create a report
                            </dd>
                        </div>
                    </dl>
                    <button
                        disabled={loading || Boolean(submittingId)}
                        className="ma-press inline-flex h-[34px] items-center justify-center gap-2 rounded-[9px] border border-line-strong bg-surface px-4 text-[13px] font-medium text-ink-2 hover:bg-surface-2 hover:text-ink disabled:cursor-not-allowed disabled:text-[#94A3B8] disabled:hover:bg-surface"
                        onClick={() => void loadQueue()}
                        type="button"
                    >
                        <Icon aria-hidden="true" className="h-4 w-4" name="refresh" />
                        Refresh
                    </button>
                </div>
            </section>

            {notice ? (
                <p
                    className="ma-enter flex items-start gap-2.5 rounded-xl border border-ok-line bg-ok-soft px-4 py-3 text-sm text-ok-ink"
                    role="status"
                >
                    <Icon className="mt-0.5 h-4 w-4 shrink-0" name="check" />
                    {notice}
                </p>
            ) : null}

            {reviewError ? (
                <p
                    role="alert"
                    className="ma-enter flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink"
                >
                    <Icon className="mt-0.5 h-4 w-4 shrink-0" name="alert" />
                    {reviewError}
                </p>
            ) : null}
            {initialLoad ? <LoadingQueue /> : null}
            {loading && items.length > 0 ? (
                <p
                    className="flex items-center gap-2.5 text-[13px] text-muted"
                    role="status"
                >
                    <ProcessingDots />
                    Refreshing ADR reviews…
                </p>
            ) : null}
            {!loading && error && items.length === 0 ? (
                <ErrorState
                    description={error}
                    onRetry={() => void loadQueue()}
                    title="Unable to load ADR reviews"
                />
            ) : null}
            {error && items.length > 0 ? (
                <div className="ma-enter flex flex-wrap items-center justify-between gap-3 rounded-xl border border-risk-line bg-risk-soft px-5 py-3.5 text-sm text-risk-ink">
                    <p className="flex items-start gap-2.5" role="alert">
                        <Icon className="mt-0.5 h-4 w-4 shrink-0" name="alert" />
                        {error}
                    </p>
                    <button
                        className="ma-press h-8 rounded-lg border border-risk-line bg-surface px-3 text-xs font-semibold text-risk-ink hover:bg-risk-tint disabled:cursor-not-allowed disabled:text-[#94A3B8] disabled:hover:bg-surface"
                        disabled={loading || Boolean(submittingId)}
                        onClick={() => void loadQueue()}
                        type="button"
                    >
                        Try again
                    </button>
                </div>
            ) : null}
            {!loading && !error && items.length === 0 ? (
                <EmptyState
                    description="New patient-grounded ADR assessments will appear here for clinician review."
                    icon={<Icon name="inbox" />}
                    title="No ADR assessments awaiting review"
                />
            ) : null}
            {items.length > 0 ? (
                <section
                    className="space-y-5"
                    aria-label="ADR assessments awaiting review"
                >
                    {items.map((item) => (
                        <ADRReviewCard
                            item={item}
                            key={item.id}
                            onReview={reviewAssessment}
                            submitting={
                                Boolean(submittingId) ||
                                loading ||
                                Boolean(error)
                            }
                        />
                    ))}
                </section>
            ) : null}
        </div>
    );
}
