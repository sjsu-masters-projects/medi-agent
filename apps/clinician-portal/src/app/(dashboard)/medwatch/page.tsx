"use client";

import { useCallback, useEffect, useState } from "react";
import {
    HiOutlineArrowPath,
    HiOutlineBeaker,
    HiOutlineClipboardDocumentCheck,
    HiOutlineExclamationTriangle,
} from "react-icons/hi2";
import { ADRReviewCard } from "@/components/features/adr-review-card";
import { Card, EmptyState, ErrorState, Skeleton } from "@/components/ui";
import { fetchADRReviewQueue, type ADRReviewQueueItem } from "@/services/clinicians";

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

    const loadQueue = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            setItems(await fetchADRReviewQueue());
        } catch (queueError) {
            setError(
                queueError instanceof Error
                    ? queueError.message
                    : "Unable to load ADR assessments.",
            );
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        void loadQueue();
    }, [loadQueue]);

    return (
        <div className="mx-auto max-w-7xl space-y-6">
            <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight text-gray-900">
                        ADR Review Queue
                    </h1>
                    <p className="mt-1 text-sm text-gray-500">
                        Review deterministic Naranjo assistance and the patient’s source evidence.
                    </p>
                </div>
                <button
                    className="flex items-center justify-center gap-2 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50"
                    onClick={() => void loadQueue()}
                    type="button"
                >
                    <HiOutlineArrowPath aria-hidden="true" className="h-4 w-4" />
                    Refresh
                </button>
            </div>

            <section className="grid gap-4 md:grid-cols-3">
                <Card className="flex items-center gap-3" padding="sm">
                    <div className="rounded-full bg-yellow-100 p-3 text-yellow-800">
                        <HiOutlineExclamationTriangle className="h-5 w-5" />
                    </div>
                    <div>
                        <p className="text-sm text-gray-500">Pending ADR reviews</p>
                        <p className="text-2xl font-bold text-gray-900">{items.length}</p>
                    </div>
                </Card>
                <Card className="flex items-center gap-3" padding="sm">
                    <div className="rounded-full bg-blue-100 p-3 text-blue-800">
                        <HiOutlineBeaker className="h-5 w-5" />
                    </div>
                    <div>
                        <p className="text-sm text-gray-500">Scoring</p>
                        <p className="text-sm font-semibold text-gray-900">
                            Deterministic Naranjo assistance
                        </p>
                    </div>
                </Card>
                <Card className="flex items-center gap-3" padding="sm">
                    <div className="rounded-full bg-green-100 p-3 text-green-800">
                        <HiOutlineClipboardDocumentCheck className="h-5 w-5" />
                    </div>
                    <div>
                        <p className="text-sm text-gray-500">MedWatch status</p>
                        <p className="text-sm font-semibold text-gray-900">
                            Generated only after review
                        </p>
                    </div>
                </Card>
            </section>

            {loading ? <LoadingQueue /> : null}
            {!loading && error ? (
                <ErrorState
                    description={error}
                    onRetry={() => void loadQueue()}
                    title="Unable to load ADR reviews"
                />
            ) : null}
            {!loading && !error && items.length === 0 ? (
                <EmptyState
                    description="New patient-grounded ADR assessments will appear here for clinician review."
                    icon={<HiOutlineExclamationTriangle />}
                    title="No ADR assessments awaiting review"
                />
            ) : null}
            {!loading && !error && items.length > 0 ? (
                <section className="space-y-4" aria-label="ADR assessments awaiting review">
                    {items.map((item) => (
                        <ADRReviewCard item={item} key={item.id} />
                    ))}
                </section>
            ) : null}
        </div>
    );
}
