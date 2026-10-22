"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Badge, EmptyState, ErrorState, Skeleton } from "@/components/ui";
import { listSharedWithMe, type SharedHandoffItem } from "@/services/handoff-summaries";

const day = (value: string) => value.slice(0, 10);

/** Approved summaries colleagues shared with me. Optionally limited to one patient. */
export function SharedWithMeList({ patientId }: { patientId?: string }) {
    const [items, setItems] = useState<SharedHandoffItem[] | null>(null);
    const [failed, setFailed] = useState(false);
    const [attempt, setAttempt] = useState(0);

    useEffect(() => {
        let active = true;
        listSharedWithMe().then(
            (result) => { if (active) { setItems(result); setFailed(false); } },
            () => { if (active) setFailed(true); },
        );
        return () => { active = false; };
    }, [attempt]);

    const shown = items && patientId ? items.filter((item) => item.patient_id === patientId) : items;

    return (
        <section aria-labelledby="shared-with-me" className="space-y-3">
            <h2 className="text-[15px] font-semibold text-ink" id="shared-with-me">Shared with me</h2>
            {failed ? <ErrorState description="Summaries shared with you could not be loaded." onRetry={() => setAttempt((value) => value + 1)} title="Unable to load shared summaries" /> : null}
            {!failed && shown === null ? <div aria-label="Loading shared summaries" role="status"><Skeleton className="h-16 w-full" /></div> : null}
            {shown && shown.length === 0 ? <EmptyState description="When a colleague shares an approved handoff summary with you, it appears here and in your notifications." title="Nothing shared with you" /> : null}
            {shown && shown.length > 0 ? (
                <ul className="space-y-2">
                    {shown.map((item) => (
                        <li key={item.share_id}>
                            <Link className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-surface px-4 py-3 hover:bg-surface-2" href={`/handoff-shared/${encodeURIComponent(item.share_id)}`}>
                                <span className="min-w-0">
                                    <span className="block [overflow-wrap:anywhere] text-sm font-semibold text-ink">{item.title}</span>
                                    <span className="block [overflow-wrap:anywhere] text-xs text-muted">{item.patient_name} · from Dr. {item.author_name} ({item.author_specialty}) · version {item.version} · shared {day(item.shared_at)}</span>
                                </span>
                                {item.newer ? <Badge variant="warning">A newer version exists</Badge> : <Badge variant="success">Approved</Badge>}
                            </Link>
                        </li>
                    ))}
                </ul>
            ) : null}
        </section>
    );
}
