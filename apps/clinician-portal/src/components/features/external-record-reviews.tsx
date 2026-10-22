"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ClinicChip } from "@/components/features/clinic-chip";
import { fetchExternalRecordReviews, type ExternalRecordReviewsResponse } from "@/services/clinicians";

function SourceTime({ value }: { value: string }) {
    return <time dateTime={value}>{new Date(value).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" })}</time>;
}

function ReviewPage({ clinicId, page, setPage }: { clinicId: string | null; page: number; setPage: (page: number) => void }) {
    const [data, setData] = useState<ExternalRecordReviewsResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);
    const [retry, setRetry] = useState(0);

    useEffect(() => {
        let active = true;
        let running = false;
        const refresh = async () => {
            if (!active || running || document.visibilityState !== "visible") return;
            running = true;
            setLoading(true);
            try {
                const result = await fetchExternalRecordReviews(page, clinicId);
                if (active) { setData(result); setError(false); }
            } catch {
                if (active) setError(true);
            } finally {
                running = false;
                if (active) setLoading(false);
            }
        };
        void refresh();
        const onVisible = () => { void refresh(); };
        const timer = window.setInterval(onVisible, 15000);
        window.addEventListener("focus", onVisible);
        document.addEventListener("visibilitychange", onVisible);
        return () => {
            active = false;
            window.clearInterval(timer);
            window.removeEventListener("focus", onVisible);
            document.removeEventListener("visibilitychange", onVisible);
        };
    }, [clinicId, page, retry]);

    const pending = data?.items.reduce((sum, item) => sum + item.pending_count, 0);
    return <section aria-label="External record reviews" className="overflow-hidden rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line p-4">
            <div>
                <h2 className="font-semibold text-ink">External record reviews</h2>
                <p className="mt-1 text-sm text-muted">Pending medication, condition, allergy and other imported evidence. These reviews are separate from notification and unread counts.</p>
            </div>
            <button type="button" disabled={loading} onClick={() => setRetry((value) => value + 1)} className="min-h-9 rounded-lg border border-line-strong px-3 text-sm text-ink-2 disabled:opacity-50">Refresh external reviews</button>
        </div>
        {error && <p role="alert" className="p-4 text-sm text-risk-ink">Unable to refresh external record reviews. {data ? "Previously retrieved rows are retained and may be out of date." : "Review counts are unavailable."}</p>}
        {!data && loading && <p role="status" className="p-4 text-sm text-muted">Loading external record reviews when this tab is visible…</p>}
        {data && <>
            <div className="space-y-1 border-b border-line p-4 text-sm text-muted">
                <p className="font-medium text-ink">{pending} pending candidates across {data.items.length} {data.items.length === 1 ? "patient" : "patients"} on this page</p>
                <p>Source state retrieved: <SourceTime value={data.retrieved_at} />{loading ? " · Refreshing…" : ""}</p>
                <p>Examined {data.patients_examined} of {data.assigned_patients} assigned patients returned in this scope · page {page}. Counts apply to this patient page only. Assignment coverage may be limited; this is not a complete roster audit.</p>
                <p>Source times inspect at most {data.candidate_limit} candidates per patient and {data.citation_limit} citations per candidate. Capture time is not the clinical event date or last review.</p>
            </div>
            {!data.items.length && <p className="p-4 text-sm text-muted">No pending external record reviews among the assigned patients on this page.</p>}
            <ul className="divide-y divide-line">
                {data.items.map((item) => {
                    const params = new URLSearchParams({ tab: "imports" });
                    if (clinicId) params.set("clinic", clinicId);
                    return <li key={item.patient_id} className="space-y-1 p-4 text-sm [overflow-wrap:anywhere]">
                        <h3 className="font-medium text-ink">{item.patient_name} <ClinicChip name={item.clinic_name} /></h3>
                        <p>{item.pending_count} pending {item.pending_count === 1 ? "candidate" : "candidates"}</p>
                        <p className="text-muted">{item.source_times_complete ? "Oldest captured source" : "Oldest captured source inspected"}: {item.oldest_source_captured_at ? <SourceTime value={item.oldest_source_captured_at} /> : "Unavailable"}</p>
                        {!item.source_times_complete && <p className="text-muted">Source-time coverage is incomplete ({item.inspected_candidates} candidates inspected); the full queue may contain older sources.</p>}
                        <Link className="inline-flex min-h-9 items-center font-medium text-primary hover:underline" href={`/patients/${encodeURIComponent(item.patient_id)}?${params}`}>Review External Records for {item.patient_name}</Link>
                    </li>;
                })}
            </ul>
            <div className="flex gap-4 border-t border-line p-4 text-sm">
                <button type="button" disabled={page <= 1} className="min-h-9 font-medium text-primary disabled:opacity-50" onClick={() => setPage(page - 1)}>Previous patients</button>
                <button type="button" disabled={!data.has_more} className="min-h-9 font-medium text-primary disabled:opacity-50" onClick={() => setPage(page + 1)}>Next patients</button>
            </div>
        </>}
    </section>;
}

function ReviewScope({ clinicId }: { clinicId: string | null }) {
    const [page, setPage] = useState(1);
    return <ReviewPage key={page} clinicId={clinicId} page={page} setPage={setPage} />;
}

export function ExternalRecordReviews({ clinicId, ready }: { clinicId: string | null; ready: boolean }) {
    if (!ready) return <p role="status">Loading external review scope…</p>;
    return <ReviewScope key={clinicId ?? "all"} clinicId={clinicId} />;
}
