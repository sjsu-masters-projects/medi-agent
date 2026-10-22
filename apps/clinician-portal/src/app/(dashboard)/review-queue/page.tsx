"use client";

import { ClinicChip, ClinicFilterEmpty, ClinicFilterField } from "@/components/features/clinic-chip";
import { SourceFileIcon } from "@/components/features/source-file";
import { clinicScopeLabel } from "@/hooks/clinic-scope";
import { useClinicFilter } from "@/hooks/use-clinic-filter";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import {
    DocumentTypeTile,
    ParseStatusBadge,
    ReviewStatusBadge,
} from "@/components/features/document-review-badges";
import { Modal, Skeleton } from "@/components/ui";
import { AiChip } from "@/components/ui/ai-chip";
import { Icon } from "@/components/ui/icons";
import {
    approveDocumentReview,
    fetchDocumentReviewQueue,
    rejectDocumentReview,
    type ClinicReviewQueueItem,
} from "@/services/clinicians";
import { loadPatientDeepDive } from "@/store/slices/patient-detail-slice";
import type { AppDispatch, RootState } from "@/store/store";
import { formatClinicianDateTime } from "@/utils/dates";
import {
    DocumentReviewStatus,
    getDocumentTypeLabel,
} from "@/types";

const QUEUE_COLUMNS =
    "xl:grid-cols-[minmax(0,2fr)_minmax(0,1.1fr)_minmax(0,1fr)_minmax(0,1.3fr)_300px]";

export default function ReviewQueuePage() {
    const dispatch = useDispatch<AppDispatch>();
    const activePatientId = useSelector(
        (state: RootState) => state.patientDetail.data?.patient_id ?? null,
    );
    const [items, setItems] = useState<ClinicReviewQueueItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [busyDocumentId, setBusyDocumentId] = useState<string | null>(null);
    const [rejectingItem, setRejectingItem] = useState<ClinicReviewQueueItem | null>(null);
    const [rejectNote, setRejectNote] = useState("");
    const requestSequence = useRef(0);

    const pendingCount = useMemo(() => items.length, [items.length]);

    const clinicFilter = useClinicFilter();
    const { clinicId, ready } = clinicFilter;

    const loadQueue = useCallback(async (background = false) => {
        const sequence = ++requestSequence.current;
        if (!background) {
            setLoading(true);
            setError(null);
        }
        try {
            const result = await fetchDocumentReviewQueue(clinicId);
            if (sequence === requestSequence.current) {
                setItems(result);
                setError(null);
            }
        } catch (queueError) {
            if (sequence !== requestSequence.current) return;
            setError(
                queueError instanceof Error
                    ? queueError.message
                    : "Unable to load the review queue.",
            );
        } finally {
            if (sequence === requestSequence.current) setLoading(false);
        }
    }, [clinicId]);

    useEffect(() => {
        setItems([]);
        setRejectingItem(null);
        if (ready) {
            void loadQueue();
        }
        return () => { requestSequence.current += 1; };
    }, [loadQueue, ready]);

    useEffect(() => {
        // Another assigned reviewer may finish this work. Re-read source state without
        // replacing the list with a spinner or interrupting an open review decision.
        if (!ready || busyDocumentId || rejectingItem) return;
        const refresh = () => {
            if (document.visibilityState === "visible") void loadQueue(true);
        };
        const timer = window.setInterval(refresh, 15_000);
        window.addEventListener("focus", refresh);
        document.addEventListener("visibilitychange", refresh);
        return () => {
            window.clearInterval(timer);
            window.removeEventListener("focus", refresh);
            document.removeEventListener("visibilitychange", refresh);
        };
    }, [ready, busyDocumentId, rejectingItem, loadQueue]);

    async function handleApprove(item: ClinicReviewQueueItem) {
        requestSequence.current += 1;
        setBusyDocumentId(item.id);
        setError(null);
        try {
            await approveDocumentReview(item.patientId, item.id);
            setItems((current) => current.filter((entry) => entry.id !== item.id));
            if (activePatientId === item.patientId) {
                void dispatch(loadPatientDeepDive(item.patientId));
            }
        } catch (reviewError) {
            setError(
                reviewError instanceof Error
                    ? reviewError.message
                    : "Unable to approve this document.",
            );
        } finally {
            setBusyDocumentId(null);
        }
    }

    async function handleReject() {
        if (!rejectingItem) {
            return;
        }

        requestSequence.current += 1;
        setBusyDocumentId(rejectingItem.id);
        setError(null);
        try {
            await rejectDocumentReview(rejectingItem.patientId, rejectingItem.id, rejectNote);
            setItems((current) => current.filter((entry) => entry.id !== rejectingItem.id));
            if (activePatientId === rejectingItem.patientId) {
                void dispatch(loadPatientDeepDive(rejectingItem.patientId));
            }
            setRejectingItem(null);
            setRejectNote("");
        } catch (reviewError) {
            setError(
                reviewError instanceof Error
                    ? reviewError.message
                    : "Unable to reject this document.",
            );
        } finally {
            setBusyDocumentId(null);
        }
    }

    return (
        <div className="ma-page space-y-5">
            <div className="flex flex-wrap items-end justify-between gap-4">
                <div className="min-w-0">
                    <h1 className="text-2xl font-semibold tracking-[-0.02em] text-ink">
                        Patient Upload Review Queue
                    </h1>
                    <p className="mt-1 max-w-[80ch] text-sm text-muted">
                        Review patient-uploaded sources before they can support a new care plan. Document approval does not publish instructions; the complete plan requires separate approval.{clinicScopeLabel(clinicFilter) ? ` · ${clinicScopeLabel(clinicFilter)}` : ""}
                    </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                <Link href={clinicId ? `/alerts?clinic=${encodeURIComponent(clinicId)}` : "/alerts"} className="inline-flex min-h-9 items-center rounded-lg border border-line-strong bg-surface px-3 text-sm font-medium text-ink-2 hover:bg-surface-2">All clinical actions</Link>
                <ClinicFilterField filter={clinicFilter} />
                <button
                    disabled={loading || busyDocumentId !== null}
                    className="ma-press inline-flex h-[34px] items-center gap-2 rounded-[9px] border border-line-strong bg-surface px-4 text-[13px] font-medium text-ink-2 hover:bg-surface-2 hover:text-ink disabled:cursor-not-allowed disabled:text-[#94A3B8]"
                    onClick={() => void loadQueue()}
                    type="button"
                >
                    <Icon name="refresh" aria-hidden="true" className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                    {loading ? "Refreshing…" : "Refresh"}
                </button>
                </div>
            </div>

            <dl className="grid overflow-hidden rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)] md:grid-cols-3">
                <div className="flex items-center gap-3.5 border-b border-line px-[22px] py-4 md:border-b-0 md:border-r">
                    <span aria-hidden="true" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-primary-tint text-primary">
                        <Icon name="clock" className="h-[18px] w-[18px]" />
                    </span>
                    <div className="min-w-0">
                        <dt className="text-[13px] text-muted">Pending reviews</dt>
                        <dd className="font-mono text-[28px] font-medium leading-tight text-ink">{loading || error ? "—" : pendingCount}</dd>
                    </div>
                </div>
                <div className="flex items-center gap-3.5 border-b border-line px-[22px] py-4 md:border-b-0 md:border-r">
                    <span aria-hidden="true" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-sunken text-ink-2">
                        <Icon name="users" className="h-[18px] w-[18px]" />
                    </span>
                    <div className="min-w-0">
                        <dt className="text-[13px] text-muted">Workflow</dt>
                        <dd className="mt-0.5 text-sm font-semibold text-ink">
                            Shared across assigned clinicians
                        </dd>
                    </div>
                </div>
                <div className="flex items-center gap-3.5 px-[22px] py-4">
                    <span aria-hidden="true" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-warn-soft text-warn-ink">
                        <Icon name="shield" className="h-[18px] w-[18px]" />
                    </span>
                    <div className="min-w-0">
                        <dt className="text-[13px] text-muted">Review scope</dt>
                        <dd className="mt-0.5 text-sm font-semibold text-ink">
                            Patient uploads only
                        </dd>
                    </div>
                </div>
            </dl>

            {error && (
                <div
                    className="flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink"
                    role="alert"
                >
                    <Icon name="alert" aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>{error}</span>
                </div>
            )}

            <section className="overflow-hidden rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]">
                <div className="flex items-center justify-between gap-3 border-b border-line px-[22px] py-4">
                    <h2 className="text-[15px] font-semibold text-ink">Pending patient uploads</h2>
                    {!loading && !error && items.length > 0 ? (
                        <span className="rounded-[7px] bg-sunken px-2 py-1 font-mono text-xs font-medium text-ink-2">
                            {pendingCount}
                        </span>
                    ) : null}
                </div>

                {loading ? (
                    <div aria-hidden="true">
                        {Array.from({ length: 3 }).map((_, index) => (
                            <div className="flex items-center gap-3 border-b border-line px-[22px] py-4 last:border-b-0" key={index}>
                                <Skeleton className="h-9 w-9" />
                                <div className="flex-1 space-y-2">
                                    <Skeleton className="h-4 w-56" variant="text" />
                                    <Skeleton className="h-3 w-36" variant="text" />
                                </div>
                                <Skeleton className="hidden h-8 w-64 xl:block" />
                            </div>
                        ))}
                    </div>
                ) : error && items.length === 0 ? (
                    <p className="px-[22px] py-10 text-center text-sm text-ink-2">The review queue could not be loaded. Refresh to check pending uploads.</p>
                ) : items.length === 0 ? (
                    <div className="flex flex-col items-center justify-center gap-3 px-6 py-12 text-center">
                        <span aria-hidden="true" className="flex h-12 w-12 items-center justify-center rounded-2xl bg-sunken text-muted">
                            <Icon name="inbox" className="h-6 w-6" />
                        </span>
                        <div className="space-y-1">
                            <p className="text-[15px] font-semibold text-ink">
                                {clinicId ? <ClinicFilterEmpty filter={clinicFilter} noun="uploads" /> : "Review queue is clear"}
                            </p>
                            {clinicId ? null : <p className="text-sm text-muted">
                                Refresh to check for new patient uploads.
                            </p>}
                        </div>
                    </div>
                ) : (
                    <div>
                        <div
                            aria-hidden="true"
                            className={`hidden gap-4 border-b border-line px-[22px] py-3 font-mono text-[11px] uppercase tracking-[0.06em] text-muted xl:grid ${QUEUE_COLUMNS}`}
                        >
                            <span>Document</span>
                            <span>Patient</span>
                            <span>Uploaded</span>
                            <span>Status</span>
                            <span className="text-right">Actions</span>
                        </div>
                        {items.map((item) => (
                            <div
                                className="border-b border-line px-[22px] py-4 transition-colors duration-[160ms] last:border-b-0 hover:bg-[rgba(100,116,139,.05)]"
                                key={item.id}
                            >
                                <div className={`grid items-center gap-x-4 gap-y-3 ${QUEUE_COLUMNS}`}>
                                    <div className="flex min-w-0 items-center gap-3">
                                        <DocumentTypeTile documentType={item.documentType} />
                                        <div className="min-w-0">
                                            <div className="flex min-w-0 items-start gap-1.5"><SourceFileIcon className="mt-0.5" name={item.fileName} /><div className="min-w-0">{item.displayTitle?.["en-US"] ? <p className="break-words text-sm font-semibold text-ink">{item.displayTitle["en-US"]}</p> : null}<p className={item.displayTitle?.["en-US"] ? "break-all font-mono text-[11px] text-muted" : "break-words text-sm font-semibold text-ink"}>{item.fileName}</p></div></div>
                                            <p className="mt-0.5 text-xs text-muted">
                                                <span className="capitalize">{getDocumentTypeLabel(item.documentType)}</span>
                                                {item.sourceClinic ? ` · ${item.sourceClinic}` : ""}
                                            </p>
                                        </div>
                                    </div>
                                    <div className="flex min-w-0 flex-col items-start gap-0.5">
                                        <p className="min-w-0 break-words text-[13px] text-ink-2">
                                            {item.patientFirstName} {item.patientLastName}
                                        </p>
                                        <ClinicChip name={clinicFilter.multi ? item.clinicName : null} />
                                    </div>
                                    <p className="text-[13px] text-ink-2">
                                        <span className="text-muted xl:sr-only">Uploaded </span>
                                        <time className="font-mono text-[12.5px]" dateTime={item.createdAt}>
                                            {formatClinicianDateTime(item.createdAt)}
                                        </time>
                                    </p>
                                    <div className="flex flex-wrap gap-1.5">
                                        <ParseStatusBadge parseStatus={item.parseStatus} />
                                        <ReviewStatusBadge
                                            reviewStatus={DocumentReviewStatus.PENDING}
                                        />
                                    </div>
                                    <div className="flex flex-wrap items-center gap-2 xl:justify-end">
                                        <Link
                                            className="ma-press inline-flex h-8 items-center justify-center gap-1.5 rounded-lg bg-primary px-3 text-[13px] font-semibold text-white hover:bg-primary-hover"
                                            href={`/patients/${item.patientId}?tab=documents#document-${item.id}`}
                                        >
                                            Review document
                                        </Link>
                                        <button
                                            className="ma-press inline-flex h-8 items-center justify-center rounded-lg border border-ok-line bg-surface px-3 text-[13px] font-semibold text-ok-ink hover:bg-ok-soft disabled:cursor-not-allowed disabled:border-line disabled:text-[#94A3B8]"
                                            disabled={busyDocumentId === item.id}
                                            onClick={() => void handleApprove(item)}
                                            type="button"
                                        >
                                            {busyDocumentId === item.id ? "Saving..." : "Approve"}
                                        </button>
                                        <button
                                            className="ma-press inline-flex h-8 items-center justify-center rounded-lg border border-risk-line bg-surface px-3 text-[13px] font-semibold text-risk-ink hover:bg-risk-soft disabled:cursor-not-allowed disabled:border-line disabled:text-[#94A3B8]"
                                            disabled={busyDocumentId === item.id}
                                            onClick={() => {
                                                setRejectingItem(item);
                                                setRejectNote("");
                                            }}
                                            type="button"
                                        >
                                            Reject
                                        </button>
                                    </div>
                                </div>

                                {item.aiSummary && (
                                    <div className="mt-3 max-w-[80ch] rounded-xl border border-line bg-surface-2 px-4 py-3 xl:ml-12">
                                        <AiChip>AI summary</AiChip>
                                        <p className="mt-2 text-sm leading-relaxed text-ink-2">
                                            {item.aiSummary}
                                        </p>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </section>

            <Modal
                onClose={() => {
                    if (busyDocumentId) {
                        return;
                    }
                    setRejectingItem(null);
                    setRejectNote("");
                }}
                open={Boolean(rejectingItem)}
                title="Reject patient upload"
            >
                <div className="space-y-4">
                    <p className="text-sm text-ink-2">
                        Add an optional note so the next clinician sees why this upload was
                        rejected.
                    </p>
                    <label className="block text-[13px] font-medium text-ink-2">
                        Review note
                        <textarea
                            className="mt-1.5 min-h-28 w-full rounded-[10px] border border-line-strong bg-surface px-3.5 py-2.5 text-sm text-ink outline-none transition placeholder:text-[#94A3B8] focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)]"
                            onChange={(event) => setRejectNote(event.target.value)}
                            placeholder="Optional follow-up note."
                            value={rejectNote}
                        />
                    </label>
                    <div className="flex justify-end gap-2">
                        <button
                            className="ma-press h-[34px] rounded-[9px] border border-line-strong bg-surface px-4 text-[13px] font-medium text-ink-2 hover:bg-surface-2 hover:text-ink"
                            onClick={() => {
                                setRejectingItem(null);
                                setRejectNote("");
                            }}
                            type="button"
                        >
                            Cancel
                        </button>
                        <button
                            className="ma-press h-[34px] rounded-[9px] bg-risk px-4 text-[13px] font-semibold text-white hover:bg-risk-strong disabled:cursor-not-allowed disabled:bg-track disabled:text-[#94A3B8]"
                            disabled={!rejectingItem || busyDocumentId !== null}
                            onClick={() => void handleReject()}
                            type="button"
                        >
                            {busyDocumentId ? "Saving..." : "Confirm rejection"}
                        </button>
                    </div>
                </div>
            </Modal>
        </div>
    );
}
