"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
    HiOutlineArrowPath,
    HiOutlineCheckCircle,
    HiOutlineClock,
    HiOutlineDocumentText,
    HiOutlineExclamationCircle,
} from "react-icons/hi2";
import { useDispatch, useSelector } from "react-redux";
import {
    ParseStatusBadge,
    ReviewStatusBadge,
} from "@/components/features/document-review-badges";
import { Card, Modal, Skeleton } from "@/components/ui";
import {
    approveDocumentReview,
    fetchDocumentReviewQueue,
    rejectDocumentReview,
} from "@/services/clinicians";
import { loadPatientDeepDive } from "@/store/slices/patient-detail-slice";
import type { AppDispatch, RootState } from "@/store/store";
import {
    DocumentReviewStatus,
    getDocumentTypeLabel,
    type DocumentReviewQueueItem,
} from "@/types";

export default function ReviewQueuePage() {
    const dispatch = useDispatch<AppDispatch>();
    const activePatientId = useSelector(
        (state: RootState) => state.patientDetail.data?.patient_id ?? null,
    );
    const [items, setItems] = useState<DocumentReviewQueueItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [busyDocumentId, setBusyDocumentId] = useState<string | null>(null);
    const [rejectingItem, setRejectingItem] = useState<DocumentReviewQueueItem | null>(null);
    const [rejectNote, setRejectNote] = useState("");

    const pendingCount = useMemo(() => items.length, [items.length]);

    const loadQueue = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const result = await fetchDocumentReviewQueue();
            setItems(result);
        } catch (queueError) {
            setError(
                queueError instanceof Error
                    ? queueError.message
                    : "Unable to load the review queue.",
            );
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        void loadQueue();
    }, [loadQueue]);

    async function handleApprove(item: DocumentReviewQueueItem) {
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
        <div className="mx-auto max-w-7xl space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight text-ink">
                        Patient Upload Review Queue
                    </h1>
                    <p className="mt-1 text-sm text-muted">
                        Review patient-uploaded sources before they can support a new care plan. Document approval does not publish instructions; the complete plan requires separate approval.
                    </p>
                </div>
                <button
                    disabled={loading || busyDocumentId !== null}
                    className="flex items-center gap-2 rounded-lg border border-line px-4 py-2 text-sm font-medium text-ink-2 hover:bg-surface-2"
                    onClick={() => void loadQueue()}
                    type="button"
                >
                    <HiOutlineArrowPath aria-hidden="true" className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                    {loading ? "Refreshing…" : "Refresh"}
                </button>
            </div>

            <section className="grid gap-4 md:grid-cols-3">
                <Card className="flex items-center gap-3 px-5 py-4" padding="sm">
                    <div className="rounded-full bg-ai-tint p-3 text-primary">
                        <HiOutlineClock className="h-5 w-5" />
                    </div>
                    <div>
                        <p className="text-sm text-muted">Pending reviews</p>
                        <p className="text-2xl font-bold text-ink">{loading || error ? "—" : pendingCount}</p>
                    </div>
                </Card>
                <Card className="flex items-center gap-3 px-5 py-4" padding="sm">
                    <div className="rounded-full bg-ok-tint p-3 text-ok-ink">
                        <HiOutlineCheckCircle className="h-5 w-5" />
                    </div>
                    <div>
                        <p className="text-sm text-muted">Workflow</p>
                        <p className="text-sm font-semibold text-ink">
                            Shared across assigned clinicians
                        </p>
                    </div>
                </Card>
                <Card className="flex items-center gap-3 px-5 py-4" padding="sm">
                    <div className="rounded-full bg-warn-tint p-3 text-warn-ink">
                        <HiOutlineExclamationCircle className="h-5 w-5" />
                    </div>
                    <div>
                        <p className="text-sm text-muted">Review scope</p>
                        <p className="text-sm font-semibold text-ink">
                            Patient uploads only
                        </p>
                    </div>
                </Card>
            </section>

            {error && (
                <div
                    className="rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink"
                    role="alert"
                >
                    {error}
                </div>
            )}

            <Card className="overflow-hidden px-0 py-0" padding="sm">
                <div className="border-b border-line px-6 py-5">
                    <h2 className="text-lg font-semibold text-ink">Pending patient uploads</h2>
                </div>

                {loading ? (
                    <div className="space-y-4 px-6 py-6">
                        {Array.from({ length: 3 }).map((_, index) => (
                            <Skeleton className="h-28 w-full" key={index} />
                        ))}
                    </div>
                ) : error && items.length === 0 ? (
                    <p className="px-6 py-10 text-sm text-ink-2">The review queue could not be loaded. Refresh to check pending uploads.</p>
                ) : items.length === 0 ? (
                    <div className="flex h-48 flex-col items-center justify-center gap-3 px-6 py-10 text-center text-muted">
                        <HiOutlineCheckCircle className="h-10 w-10 text-ok" />
                        <div>
                            <p className="text-base font-semibold text-ink">
                                Review queue is clear
                            </p>
                            <p className="text-sm">
                                Refresh to check for new patient uploads.
                            </p>
                        </div>
                    </div>
                ) : (
                    <div className="divide-y divide-line">
                        {items.map((item) => (
                            <div className="px-6 py-5" key={item.id}>
                                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                                    <div className="space-y-3">
                                        <div className="flex items-start gap-3">
                                            <div className="rounded-xl bg-primary-tint p-3 text-primary">
                                                <HiOutlineDocumentText className="h-5 w-5" />
                                            </div>
                                            <div>
                                                <p className="text-base font-semibold text-ink">
                                                    {item.fileName}
                                                </p>
                                                <p className="text-sm text-ink-2">
                                                    {item.patientFirstName} {item.patientLastName}
                                                </p>
                                                <p className="mt-1 text-xs text-muted">
                                                    {getDocumentTypeLabel(item.documentType)} ·{" "}
                                                    Uploaded {new Date(item.createdAt).toLocaleString()}
                                                    {item.sourceClinic ? ` · ${item.sourceClinic}` : ""}
                                                </p>
                                            </div>
                                        </div>

                                        <div className="flex flex-wrap gap-2 text-xs font-medium">
                                            <ParseStatusBadge parseStatus={item.parseStatus} />
                                            <ReviewStatusBadge
                                                reviewStatus={DocumentReviewStatus.PENDING}
                                            />
                                        </div>

                                        {item.aiSummary && (
                                            <p className="max-w-3xl rounded-xl bg-surface-2 px-4 py-3 text-sm text-ink-2">
                                                {item.aiSummary}
                                            </p>
                                        )}
                                    </div>

                                    <div className="flex flex-wrap items-center gap-3 lg:justify-end">
                                        <Link
                                            className="rounded-lg border border-line px-4 py-2 text-sm font-medium text-ink-2 hover:bg-surface-2"
                                            href={`/patients/${item.patientId}?tab=documents#document-${item.id}`}
                                        >
                                            Review document
                                        </Link>
                                        <button
                                            className="rounded-lg bg-ok px-4 py-2 text-sm font-semibold text-white hover:bg-ok-strong disabled:cursor-not-allowed disabled:opacity-60"
                                            disabled={busyDocumentId === item.id}
                                            onClick={() => void handleApprove(item)}
                                            type="button"
                                        >
                                            {busyDocumentId === item.id ? "Saving..." : "Approve"}
                                        </button>
                                        <button
                                            className="rounded-lg border border-risk-line px-4 py-2 text-sm font-semibold text-risk-ink hover:bg-risk-soft disabled:cursor-not-allowed disabled:opacity-60"
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
                            </div>
                        ))}
                    </div>
                )}
            </Card>

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
                    <label className="block text-sm font-medium text-ink-2">
                        Review note
                        <textarea
                            className="mt-2 min-h-28 w-full rounded-xl border border-line-strong px-3 py-2 text-sm text-ink outline-none focus:border-primary focus:ring-2 focus:ring-primary"
                            onChange={(event) => setRejectNote(event.target.value)}
                            placeholder="Optional follow-up note."
                            value={rejectNote}
                        />
                    </label>
                    <div className="flex justify-end gap-3">
                        <button
                            className="rounded-lg border border-line px-4 py-2 text-sm font-medium text-ink-2 hover:bg-surface-2"
                            onClick={() => {
                                setRejectingItem(null);
                                setRejectNote("");
                            }}
                            type="button"
                        >
                            Cancel
                        </button>
                        <button
                            className="rounded-lg bg-risk px-4 py-2 text-sm font-semibold text-white hover:bg-risk-strong disabled:cursor-not-allowed disabled:opacity-60"
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
