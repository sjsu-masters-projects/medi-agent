"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
    HiOutlineArrowPath,
    HiOutlineBeaker,
    HiOutlineClipboardDocumentCheck,
    HiOutlineExclamationTriangle,
} from "react-icons/hi2";
import { ADRReviewCard } from "@/components/features/adr-review-card";
import {
    Button,
    Card,
    EmptyState,
    ErrorState,
    Skeleton,
} from "@/components/ui";
import {
    fetchADRReviewQueue,
    reviewADRAssessment,
    type ADRReviewDecisionInput,
    type ADRReviewQueueItem,
} from "@/services/clinicians";

function LoadingQueue() {
    return (
        <div className="space-y-4" aria-label="Loading ADR reviews">
            <Skeleton className="h-48 w-full" />
            <Skeleton className="h-48 w-full" />
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

    return (
        <div className="mx-auto max-w-7xl space-y-6">
            <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight text-ink">
                        ADR Review Queue
                    </h1>
                    <p className="mt-1 text-sm text-muted">
                        Review possible adverse drug reactions against patient evidence. Naranjo scores support your review; they do not make a clinical decision.
                    </p>
                </div>
                <button
                    disabled={loading || Boolean(submittingId)}
                    className="flex items-center justify-center gap-2 rounded-lg border border-line-strong bg-surface px-4 py-2 text-sm font-medium text-ink-2 shadow-sm hover:bg-surface-2"
                    onClick={() => void loadQueue()}
                    type="button"
                >
                    <HiOutlineArrowPath
                        aria-hidden="true"
                        className="h-4 w-4"
                    />
                    Refresh
                </button>
            </div>

            <section className="grid gap-4 md:grid-cols-3">
                <Card className="flex items-center gap-3" padding="sm">
                    <div className="rounded-full bg-warn-tint p-3 text-warn-ink">
                        <HiOutlineExclamationTriangle className="h-5 w-5" />
                    </div>
                    <div>
                        <p className="text-sm text-muted">
                            Pending ADR reviews
                        </p>
                        <p className="text-2xl font-bold text-ink">
                            {loading || error ? "—" : items.length}
                        </p>
                    </div>
                </Card>
                <Card className="flex items-center gap-3" padding="sm">
                    <div className="rounded-full bg-ai-tint p-3 text-ai-ink">
                        <HiOutlineBeaker className="h-5 w-5" />
                    </div>
                    <div>
                        <p className="text-sm text-muted">Scoring</p>
                        <p className="text-sm font-semibold text-ink">
                            Naranjo assessment support
                        </p>
                    </div>
                </Card>
                <Card className="flex items-center gap-3" padding="sm">
                    <div className="rounded-full bg-ok-tint p-3 text-ok-ink">
                        <HiOutlineClipboardDocumentCheck className="h-5 w-5" />
                    </div>
                    <div>
                        <p className="text-sm text-muted">MedWatch status</p>
                        <p className="text-sm font-semibold text-ink">
                            ADR review does not create a report
                        </p>
                    </div>
                </Card>
            </section>

            {notice ? (
                <p
                    className="rounded-lg border border-ok-line bg-ok-soft px-4 py-3 text-sm text-ok-ink"
                    role="status"
                >
                    {notice}
                </p>
            ) : null}

            {reviewError ? (
                <p
                    role="alert"
                    className="rounded-lg border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink"
                >
                    {reviewError}
                </p>
            ) : null}
            {loading && items.length === 0 ? <LoadingQueue /> : null}
            {loading && items.length > 0 ? (
                <p role="status">Refreshing ADR reviews…</p>
            ) : null}
            {!loading && error && items.length === 0 ? (
                <ErrorState
                    description={error}
                    onRetry={() => void loadQueue()}
                    title="Unable to load ADR reviews"
                />
            ) : null}
            {error && items.length > 0 ? (
                <Card>
                    <p role="alert">{error}</p>
                    <Button
                        disabled={loading || Boolean(submittingId)}
                        onClick={() => void loadQueue()}
                        variant="ghost"
                    >
                        Try again
                    </Button>
                </Card>
            ) : null}
            {!loading && !error && items.length === 0 ? (
                <EmptyState
                    description="New patient-grounded ADR assessments will appear here for clinician review."
                    icon={<HiOutlineExclamationTriangle />}
                    title="No ADR assessments awaiting review"
                />
            ) : null}
            {items.length > 0 ? (
                <section
                    className="space-y-4"
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
