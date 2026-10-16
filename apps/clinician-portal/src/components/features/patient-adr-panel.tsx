"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Badge, EmptyState, ErrorState, Skeleton } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { queueTabOf, STATUS_LABELS, type QueueTab } from "@/components/features/adr-queue";
import { formatReviewTimestamp } from "@/components/features/review-time";
import { CausalityPill } from "@/components/features/work-list";
import { fetchADRReviewQueue, type ADRReviewQueueItem } from "@/services/clinicians";

const STATUS_VARIANT: Record<QueueTab, "warning" | "info" | "success" | "neutral"> = {
    awaiting: "warning",
    information: "info",
    reviewed: "success",
    dismissed: "neutral",
};

/** This patient's ADR cases, current and past, each linking to the case page. */
export function PatientADRPanel({ patientId }: { patientId: string }) {
    const [items, setItems] = useState<ADRReviewQueueItem[] | null>(null);
    const [error, setError] = useState(false);
    const [attempt, setAttempt] = useState(0);

    useEffect(() => {
        let cancelled = false;
        fetchADRReviewQueue({ status: "all", patientId }).then(
            (result) => {
                if (!cancelled) setItems(result);
            },
            () => {
                if (!cancelled) setError(true);
            },
        );
        return () => {
            cancelled = true;
        };
    }, [patientId, attempt]);

    return (
        <section aria-labelledby="tab-btn-adr" id="tab-panel-adr" role="tabpanel">
            <h2 className="mb-1 text-lg font-semibold tracking-[-0.01em] text-ink">Adverse drug reactions</h2>
            <p className="mb-4 text-sm text-ink-2">
                Suspected reactions for this patient. Scores are decision support, not a verdict.
            </p>
            {error ? (
                <ErrorState
                    description="Unable to load this patient's ADR cases."
                    onRetry={() => {
                        setItems(null);
                        setError(false);
                        setAttempt((current) => current + 1);
                    }}
                    title="Unable to load ADR cases"
                />
            ) : items === null ? (
                <div aria-label="Loading ADR cases" className="space-y-2" role="status">
                    <Skeleton className="h-14 w-full" />
                    <Skeleton className="h-14 w-full" />
                </div>
            ) : items.length === 0 ? (
                <EmptyState
                    description="Suspected reactions reported by this patient appear here."
                    icon={<Icon name="inbox" />}
                    title="No ADR cases"
                />
            ) : (
                <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line">
                    {items.map((item) => {
                        const tab = queueTabOf(item);
                        return (
                            <li key={item.id}>
                                <Link
                                    className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 bg-surface px-4 py-3 outline-none hover:bg-surface-2 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary"
                                    href={`/adr-reviews/${item.id}`}
                                >
                                    <div className="min-w-0">
                                        <p className="truncate text-sm font-semibold text-ink">
                                            {item.symptom} <span aria-hidden="true">·</span> {item.suspectMedicationName}
                                        </p>
                                        <p className="text-xs text-muted">
                                            Captured{" "}
                                            <time className="font-mono" dateTime={item.createdAt}>
                                                {formatReviewTimestamp(item.createdAt)}
                                            </time>
                                        </p>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <CausalityPill band={item.causality} score={item.naranjoScore} />
                                        <Badge variant={STATUS_VARIANT[tab]}>{STATUS_LABELS[tab]}</Badge>
                                    </div>
                                </Link>
                            </li>
                        );
                    })}
                </ul>
            )}
        </section>
    );
}
