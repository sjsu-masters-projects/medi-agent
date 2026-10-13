"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ADRReviewCard } from "@/components/features/adr-review-card";
import { MedWatchDraftCard } from "@/components/features/medwatch-draft-card";
import { saveBlob } from "@/components/features/form-3500-download-dialog";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { ProcessingDots } from "@/components/ui/motion";
import { SegmentedControl } from "@/components/ui/toolbar";
import {
    fetchADRReviewQueue,
    fetchMedWatchDrafts,
    createMedWatchDraft,
    updateMedWatchDraft,
    approveMedWatchDraft,
    exportMedWatchDraft,
    discardMedWatchDraft,
    recordMedWatchSubmission,
    amendMedWatchSubmission,
    reviewADRAssessment,
    type ADRReviewDecisionInput,
    type ADRReviewQueueItem,
    type MedWatchApprovalInput,
    type MedWatchDiscardInput,
    type MedWatchDraft,
    type MedWatchDraftState,
    type MedWatchFormData,
    type MedWatchSubmissionInput,
} from "@/services/clinicians";

const DRAFT_VIEWS: { value: MedWatchDraftState; label: string }[] = [
    { value: "active", label: "Active" },
    { value: "submitted", label: "Submitted" },
    { value: "discarded", label: "Discarded" },
];

const VIEW_COPY: Record<MedWatchDraftState, { description: string; empty: string; emptyDetail: string }> = {
    active: {
        description:
            "Edit, approve, preview and download Form FDA 3500 drafts. MediAgent never submits a report to FDA; you submit it yourself.",
        empty: "No active MedWatch drafts",
        emptyDetail: "Prepare a draft from a reviewed ADR assessment to start one.",
    },
    submitted: {
        description:
            "Drafts you recorded as submitted to FDA outside MediAgent. They are read-only; correct a record with an audited amendment.",
        empty: "No submitted MedWatch drafts",
        emptyDetail: "Drafts appear here after you record a submission you made to FDA.",
    },
    discarded: {
        description: "Discarded drafts are kept read-only with their reason. Their ADR assessments returned to review.",
        empty: "No discarded MedWatch drafts",
        emptyDetail: "Discarded drafts appear here with the reason and date.",
    },
};

function parseView(value: string | null): MedWatchDraftState {
    return value === "submitted" || value === "discarded" ? value : "active";
}

function LoadingQueue() {
    return (
        <div className="space-y-5" role="status" aria-label="Loading ADR reviews">
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

function MedWatchContent() {
    const searchParams = useSearchParams();
    const assessmentId = searchParams.get("assessment");
    const urlView = parseView(searchParams.get("state"));
    const [view, setView] = useState<MedWatchDraftState>(urlView);
    const [syncedUrlView, setSyncedUrlView] = useState(urlView);
    const [items, setItems] = useState<ADRReviewQueueItem[]>([]);
    const [drafts, setDrafts] = useState<MedWatchDraft[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [draftsLoading, setDraftsLoading] = useState(true);
    const [draftsError, setDraftsError] = useState<string | null>(null);
    const [submittingId, setSubmittingId] = useState<string | null>(null);
    const [notice, setNotice] = useState<string | null>(null);
    const [reviewError, setReviewError] = useState<string | null>(null);
    const queuePending = useRef(false);
    const reviewPending = useRef(false);
    const draftsRequest = useRef(0);
    const viewRef = useRef(view);

    // Follow a URL change made outside the switch (for example Back).
    if (urlView !== syncedUrlView) {
        setSyncedUrlView(urlView);
        setView(urlView);
    }

    useEffect(() => {
        if (!assessmentId || loading || error) return;
        const target = document.getElementById(`assessment-${assessmentId}`);
        target?.scrollIntoView?.({ block: "center" });
        target?.focus({ preventScroll: true });
    }, [assessmentId, items, loading, error]);

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

    const loadDrafts = useCallback(async (state: MedWatchDraftState) => {
        const request = ++draftsRequest.current;
        setDraftsLoading(true);
        setDraftsError(null);
        try {
            const result = await fetchMedWatchDrafts(state);
            if (request === draftsRequest.current) setDrafts(result);
        } catch {
            if (request === draftsRequest.current) {
                setDraftsError("Unable to load MedWatch drafts. Try again.");
            }
        } finally {
            if (request === draftsRequest.current) setDraftsLoading(false);
        }
    }, []);

    const refreshAll = useCallback(
        () => Promise.all([loadQueue(), loadDrafts(viewRef.current)]).then(() => undefined),
        [loadQueue, loadDrafts],
    );

    useEffect(() => {
        void loadQueue();
    }, [loadQueue]);

    useEffect(() => {
        viewRef.current = view;
        void loadDrafts(view);
    }, [view, loadDrafts]);

    const changeView = useCallback(
        (next: MedWatchDraftState) => {
            if (next === view) return;
            setDrafts([]);
            setNotice(null);
            // The URL catches up through replaceState; `syncedUrlView` follows it then.
            setView(next);
            const params = new URLSearchParams(window.location.search);
            if (next === "active") params.delete("state");
            else params.set("state", next);
            const search = params.toString();
            window.history.replaceState(
                window.history.state,
                "",
                `${window.location.pathname}${search ? `?${search}` : ""}`,
            );
        },
        [view],
    );

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
                await refreshAll();
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
        [error, refreshAll],
    );

    const prepareDraft = useCallback(
        async (assessmentId: string, rationale: string) => {
            if (reviewPending.current || queuePending.current || error) {
                throw new Error("Refresh the queue before preparing a draft.");
            }
            reviewPending.current = true;
            setSubmittingId(assessmentId);
            setReviewError(null);
            setNotice(null);
            try {
                const draft = await createMedWatchDraft(assessmentId, rationale);
                setItems((current) =>
                    current.filter((item) => item.id !== assessmentId),
                );
                if (viewRef.current === "active") {
                    setDrafts((current) => [draft, ...current]);
                }
                setNotice(
                    "Editable MedWatch draft created. Nothing was submitted to the FDA.",
                );
            } catch {
                // Rethrow only: the preparation form renders this failure inline, once.
                throw new Error(
                    "Unable to prepare the MedWatch draft. Try again.",
                );
            } finally {
                reviewPending.current = false;
                setSubmittingId(null);
            }
        },
        [error],
    );

    const replaceDraft = useCallback((updated: MedWatchDraft) => {
        setDrafts((current) =>
            current.map((draft) =>
                draft.id === updated.id ? updated : draft,
            ),
        );
    }, []);

    const saveDraft = useCallback(
        async (
            draftId: string,
            formData: MedWatchFormData,
            revision: number,
        ) => {
            setSubmittingId(draftId);
            setNotice(null);
            try {
                replaceDraft(
                    await updateMedWatchDraft(draftId, formData, revision),
                );
                setNotice("MedWatch draft changes saved and audited.");
            } finally {
                setSubmittingId(null);
            }
        },
        [replaceDraft],
    );

    const approveDraft = useCallback(
        async (draftId: string, input: MedWatchApprovalInput) => {
            setSubmittingId(draftId);
            setNotice(null);
            try {
                replaceDraft(await approveMedWatchDraft(draftId, input));
                setNotice(
                    "MedWatch draft approved for export. It was not submitted to the FDA.",
                );
            } finally {
                setSubmittingId(null);
            }
        },
        [replaceDraft],
    );

    const exportDraft = useCallback(async (draftId: string) => {
        setSubmittingId(draftId);
        setNotice(null);
        try {
            const artifact = await exportMedWatchDraft(draftId);
            const blob = new Blob([JSON.stringify(artifact.content, null, 2)], {
                type: artifact.media_type,
            });
            saveBlob(blob, artifact.filename);
            setNotice(
                "Approved draft exported locally. No FDA submission was performed.",
            );
        } finally {
            setSubmittingId(null);
        }
    }, []);

    const pdfDownloaded = useCallback(() => {
        setNotice(
            "Form 3500 PDF downloaded and audited. MediAgent did not submit this report. You submit it to FDA.",
        );
    }, []);

    const discardDraft = useCallback(
        async (draftId: string, input: MedWatchDiscardInput) => {
            setSubmittingId(draftId);
            setNotice(null);
            try {
                await discardMedWatchDraft(draftId, input);
                setDrafts((current) => current.filter((draft) => draft.id !== draftId));
                setNotice(
                    "MedWatch draft discarded. Its ADR assessment returned to review.",
                );
            } finally {
                setSubmittingId(null);
            }
            await refreshAll();
        },
        [refreshAll],
    );

    const recordSubmission = useCallback(
        async (
            draftId: string,
            input: MedWatchSubmissionInput & { expectedRevision: number },
        ) => {
            setSubmittingId(draftId);
            setNotice(null);
            try {
                await recordMedWatchSubmission(draftId, input);
                setDrafts((current) => current.filter((draft) => draft.id !== draftId));
                setNotice(
                    "Submission recorded. The draft is now read-only under Submitted. MediAgent sent nothing to FDA.",
                );
            } finally {
                setSubmittingId(null);
            }
            await loadDrafts(viewRef.current);
        },
        [loadDrafts],
    );

    const amendSubmission = useCallback(
        async (
            draftId: string,
            input: MedWatchSubmissionInput & { amendsId: string; reason: string },
        ) => {
            setSubmittingId(draftId);
            setNotice(null);
            try {
                await amendMedWatchSubmission(draftId, input);
                setNotice("Submission record amended. The original record is kept.");
            } finally {
                setSubmittingId(null);
            }
            await loadDrafts(viewRef.current);
        },
        [loadDrafts],
    );

    const initialLoad = loading && items.length === 0 && drafts.length === 0;

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
                <div className="flex w-full flex-wrap items-end justify-between gap-x-9 gap-y-5 xl:w-auto">
                    <dl className="grid flex-1 grid-cols-3 gap-x-8 gap-y-4 xl:flex xl:flex-none xl:gap-x-9">
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
                            <dt className="text-[13px] text-muted">Scoring aid</dt>
                            <dd className="flex min-h-[35px] items-end text-[15px] font-semibold leading-snug text-ink">
                                Naranjo scale
                            </dd>
                        </div>
                        <div className="flex flex-col-reverse gap-0.5">
                            <dt className="text-[13px] text-muted">
                                MedWatch drafts
                            </dt>
                            <dd className="flex min-h-[35px] items-end text-[15px] font-semibold leading-snug text-ink" title="Draft approval permits a local export; it does not submit a report to the FDA.">
                                {view === "active" && !draftsLoading && !draftsError
                                    ? `${drafts.filter((draft) => draft.status === "draft").length} awaiting approval`
                                    : "—"}
                            </dd>
                        </div>
                    </dl>
                    <button
                        disabled={loading || Boolean(submittingId)}
                        className="ma-press inline-flex h-[34px] items-center justify-center gap-2 rounded-[9px] border border-line-strong bg-surface px-4 text-[13px] font-medium text-ink-2 hover:bg-surface-2 hover:text-ink disabled:cursor-not-allowed disabled:text-[#94A3B8] disabled:hover:bg-surface"
                        onClick={() => void refreshAll()}
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
            {assessmentId && !loading && !error && !items.some((item) => item.id === assessmentId) && <p role="status" className="text-sm text-ink-2">The linked assessment is no longer awaiting review or is unavailable to you.</p>}

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
            {loading && (items.length > 0 || drafts.length > 0) ? (
                <p
                    className="flex items-center gap-2.5 text-[13px] text-ink-2"
                    role="status"
                >
                    <ProcessingDots />
                    Refreshing ADR reviews…
                </p>
            ) : null}
            {!loading && error && items.length === 0 && drafts.length === 0 ? (
                <ErrorState
                    description={error}
                    onRetry={() => void loadQueue()}
                    title="Unable to load ADR reviews"
                />
            ) : null}
            {error && (items.length > 0 || drafts.length > 0) ? (
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
                        <div key={item.id} id={`assessment-${item.id}`} tabIndex={item.id === assessmentId ? -1 : undefined} className={item.id === assessmentId ? "scroll-mt-6 rounded-2xl ring-2 ring-primary" : ""}>
                        <ADRReviewCard
                            item={item}
                            key={item.id}
                            onPrepareDraft={prepareDraft}
                            onReview={reviewAssessment}
                            submitting={
                                Boolean(submittingId) ||
                                loading ||
                                Boolean(error)
                            }
                        />
                        </div>
                    ))}
                </section>
            ) : null}
            {!initialLoad ? (
                <section className="space-y-5" aria-label="MedWatch drafts">
                    <div className="flex flex-wrap items-end justify-between gap-3">
                        <div className="min-w-0 max-w-[80ch]">
                            <h2 className="text-xl font-semibold text-ink">
                                MedWatch drafts
                            </h2>
                            <p className="mt-1 text-sm text-ink-2">
                                {VIEW_COPY[view].description}
                            </p>
                        </div>
                        <SegmentedControl
                            label="MedWatch draft state"
                            onChange={changeView}
                            options={DRAFT_VIEWS}
                            value={view}
                        />
                    </div>
                    {draftsLoading && drafts.length === 0 ? (
                        <div aria-label="Loading MedWatch drafts" className="space-y-3" role="status">
                            <Skeleton className="h-24 w-full" />
                            <Skeleton className="h-24 w-full" />
                        </div>
                    ) : null}
                    {draftsError ? (
                        <ErrorState
                            description={draftsError}
                            onRetry={() => void loadDrafts(view)}
                            title="Unable to load MedWatch drafts"
                        />
                    ) : null}
                    {!draftsLoading && !draftsError && drafts.length === 0 ? (
                        <EmptyState
                            description={VIEW_COPY[view].emptyDetail}
                            icon={<Icon name="file" />}
                            title={VIEW_COPY[view].empty}
                        />
                    ) : null}
                    {drafts.map((draft) => (
                        <MedWatchDraftCard
                            busy={
                                Boolean(submittingId) ||
                                loading ||
                                draftsLoading ||
                                Boolean(error)
                            }
                            draft={draft}
                            key={draft.id}
                            onAmendSubmission={amendSubmission}
                            onApprove={approveDraft}
                            onDiscard={discardDraft}
                            onExport={exportDraft}
                            onPdfDownloaded={pdfDownloaded}
                            onRecordSubmission={recordSubmission}
                            onSave={saveDraft}
                        />
                    ))}
                </section>
            ) : null}
        </div>
    );
}

export default function MedWatchPage() {
    return (
        <Suspense fallback={<LoadingQueue />}>
            <MedWatchContent />
        </Suspense>
    );
}
