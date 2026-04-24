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
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight text-slate-900">
                        Patient Upload Review Queue
                    </h1>
                    <p className="mt-1 text-sm text-slate-500">
                        Review patient-uploaded documents without blocking record storage or AI
                        parsing.
                    </p>
                </div>
                <button
                    className="flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
                    onClick={() => void loadQueue()}
                    type="button"
                >
                    <HiOutlineArrowPath aria-hidden="true" className="h-4 w-4" />
                    Refresh
                </button>
            </div>

            <section className="grid gap-4 md:grid-cols-3">
                <Card className="flex items-center gap-3 px-5 py-4" padding="sm">
                    <div className="rounded-full bg-blue-100 p-3 text-blue-600">
                        <HiOutlineClock className="h-5 w-5" />
                    </div>
                    <div>
                        <p className="text-sm text-slate-500">Pending reviews</p>
                        <p className="text-2xl font-bold text-slate-900">{pendingCount}</p>
                    </div>
                </Card>
                <Card className="flex items-center gap-3 px-5 py-4" padding="sm">
                    <div className="rounded-full bg-emerald-100 p-3 text-emerald-600">
                        <HiOutlineCheckCircle className="h-5 w-5" />
                    </div>
                    <div>
                        <p className="text-sm text-slate-500">Workflow</p>
                        <p className="text-sm font-semibold text-slate-900">
                            Shared across assigned clinicians
                        </p>
                    </div>
                </Card>
                <Card className="flex items-center gap-3 px-5 py-4" padding="sm">
                    <div className="rounded-full bg-amber-100 p-3 text-amber-600">
                        <HiOutlineExclamationCircle className="h-5 w-5" />
                    </div>
                    <div>
                        <p className="text-sm text-slate-500">Review scope</p>
                        <p className="text-sm font-semibold text-slate-900">
                            Patient uploads only
                        </p>
                    </div>
                </Card>
            </section>

            {error && (
                <div
                    className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
                    role="alert"
                >
                    {error}
                </div>
            )}

            <Card className="overflow-hidden px-0 py-0" padding="sm">
                <div className="border-b border-slate-200 px-6 py-5">
                    <h2 className="text-lg font-semibold text-slate-900">Pending patient uploads</h2>
                </div>

                {loading ? (
                    <div className="space-y-4 px-6 py-6">
                        {Array.from({ length: 3 }).map((_, index) => (
                            <Skeleton className="h-28 w-full" key={index} />
                        ))}
                    </div>
                ) : items.length === 0 ? (
                    <div className="flex h-48 flex-col items-center justify-center gap-3 px-6 py-10 text-center text-slate-500">
                        <HiOutlineCheckCircle className="h-10 w-10 text-emerald-500" />
                        <div>
                            <p className="text-base font-semibold text-slate-900">
                                Review queue is clear
                            </p>
                            <p className="text-sm">
                                New patient uploads will appear here automatically.
                            </p>
                        </div>
                    </div>
                ) : (
                    <div className="divide-y divide-slate-200">
                        {items.map((item) => (
                            <div className="px-6 py-5" key={item.id}>
                                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                                    <div className="space-y-3">
                                        <div className="flex items-start gap-3">
                                            <div className="rounded-xl bg-blue-50 p-3 text-blue-600">
                                                <HiOutlineDocumentText className="h-5 w-5" />
                                            </div>
                                            <div>
                                                <p className="text-base font-semibold text-slate-900">
                                                    {item.fileName}
                                                </p>
                                                <p className="text-sm text-slate-600">
                                                    {item.patientFirstName} {item.patientLastName}
                                                </p>
                                                <p className="mt-1 text-xs text-slate-500">
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
                                            <p className="max-w-3xl rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
                                                {item.aiSummary}
                                            </p>
                                        )}
                                    </div>

                                    <div className="flex flex-wrap items-center gap-3 lg:justify-end">
                                        <Link
                                            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
                                            href={`/patients/${item.patientId}?tab=documents`}
                                        >
                                            Open deep dive
                                        </Link>
                                        <button
                                            className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                                            disabled={busyDocumentId === item.id}
                                            onClick={() => void handleApprove(item)}
                                            type="button"
                                        >
                                            {busyDocumentId === item.id ? "Saving..." : "Approve"}
                                        </button>
                                        <button
                                            className="rounded-lg border border-rose-200 px-4 py-2 text-sm font-semibold text-rose-600 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-60"
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
                    <p className="text-sm text-slate-600">
                        Add an optional note so the next clinician sees why this upload was
                        rejected.
                    </p>
                    <label className="block text-sm font-medium text-slate-700">
                        Review note
                        <textarea
                            className="mt-2 min-h-28 w-full rounded-xl border border-slate-300 px-3 py-2 text-sm text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500"
                            onChange={(event) => setRejectNote(event.target.value)}
                            placeholder="Optional follow-up note."
                            value={rejectNote}
                        />
                    </label>
                    <div className="flex justify-end gap-3">
                        <button
                            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
                            onClick={() => {
                                setRejectingItem(null);
                                setRejectNote("");
                            }}
                            type="button"
                        >
                            Cancel
                        </button>
                        <button
                            className="rounded-lg bg-rose-600 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-60"
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
