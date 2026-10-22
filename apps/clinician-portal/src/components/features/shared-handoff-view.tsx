"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Badge, Button, ErrorState, Skeleton } from "@/components/ui";
import { ApprovalSeal } from "@/components/ui/approval-seal";
import { Section, stamp } from "@/components/features/handoff-section";
import { ApiClientError } from "@/services/api";
import { exportSharedHandoff, fetchSharedHandoff, type SharedHandoffDetail } from "@/services/handoff-summaries";

/** Read-only view of one approved version a colleague shared. No editing, approval or record links. */
export function SharedHandoffView({ shareId }: { shareId: string }) {
    const [detail, setDetail] = useState<SharedHandoffDetail | null>(null);
    const [state, setState] = useState<"loading" | "ready" | "denied" | "error">("loading");
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);

    const load = useCallback(async () => {
        setState("loading");
        try {
            setDetail(await fetchSharedHandoff(shareId));
            setState("ready");
        } catch (failure) {
            setState(failure instanceof ApiClientError && (failure.status === 404 || failure.status === 403) ? "denied" : "error");
        }
    }, [shareId]);

    useEffect(() => {
        void load();
    }, [load]);

    if (state === "loading") {
        return <div aria-label="Loading shared summary" className="space-y-4" role="status"><Skeleton className="h-8 w-64" /><Skeleton className="h-48 w-full" /></div>;
    }
    if (state === "denied") {
        return <ErrorState description="This summary is no longer shared with you, or does not exist." title="Summary not available" />;
    }
    if (state === "error" || !detail) {
        return <ErrorState description="The summary could not be loaded." onRetry={() => void load()} title="Unable to load this summary" />;
    }

    async function exportAs(format: "print" | "fhir") {
        setBusy(true);
        setMessage(null);
        try {
            const result = await exportSharedHandoff(shareId, format);
            if (format === "fhir" && result.bundle) {
                const blob = new Blob([JSON.stringify(result.bundle, null, 2)], { type: "application/fhir+json" });
                const url = URL.createObjectURL(blob);
                const anchor = document.createElement("a");
                anchor.href = url;
                anchor.download = `handoff-summary-v${result.summary.version}.fhir.json`;
                document.body.appendChild(anchor);
                anchor.click();
                anchor.remove();
                URL.revokeObjectURL(url);
                setMessage({ tone: "ok", text: "FHIR bundle exported and recorded in the audit history." });
            } else {
                setMessage({ tone: "ok", text: "Print export recorded in the audit history." });
                window.print();
            }
        } catch {
            setMessage({ tone: "error", text: "That did not complete. Nothing was exported. Try again." });
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="space-y-5">
            <header className="flex flex-wrap items-start justify-between gap-3" data-print-hide>
                <div className="min-w-0">
                    <Link className="text-[13px] font-medium text-primary" href="/handoff-shared">Shared with me</Link>
                    <h1 className="mt-1 [overflow-wrap:anywhere] text-[24px] font-semibold leading-tight tracking-[-0.02em] text-ink">{detail.title}</h1>
                    <p className="mt-1 text-sm text-muted">Shared by Dr. {detail.author_name} on {detail.shared_at.slice(0, 10)} · version {detail.version}</p>
                </div>
                <ApprovalSeal pill>Approved</ApprovalSeal>
            </header>

            {detail.newer ? (
                <p className="rounded-xl border border-warn-line bg-warn-soft px-4 py-3 text-sm text-warn-ink" data-print-hide role="status">
                    A newer version exists. <Link className="font-semibold underline" href={`/handoff-shared/${encodeURIComponent(detail.newer.share_id)}`}>Open version {detail.newer.version}</Link>
                </p>
            ) : null}
            {message ? <p className={`rounded-xl border px-4 py-3 text-sm ${message.tone === "ok" ? "border-ok-line bg-ok-soft text-ok-ink" : "border-risk-line bg-risk-soft text-risk-ink"}`} data-print-hide role={message.tone === "ok" ? "status" : "alert"}>{message.text}</p> : null}

            <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
                <div className="ma-print-root min-w-0 space-y-4">
                    <div className="rounded-xl border border-line bg-surface px-4 py-3">
                        <p className="text-sm font-semibold text-ink">{detail.title}</p>
                        <p className="text-xs text-muted">
                            {detail.patient_name} · Approved {stamp(detail.approved_at)}{detail.approved_by_name ? ` by Dr. ${detail.approved_by_name}` : ""} · Built {stamp(detail.built_at)}. Synthetic demo data.
                        </p>
                        <p className="mt-1 text-xs text-muted" data-print-hide>Shared with you by Dr. {detail.author_name}, {detail.author_specialty}{detail.author_clinic ? `, ${detail.author_clinic}` : ""}. Read-only.</p>
                    </div>
                    {detail.sections.map((section) => <Section key={section.key} section={section} />)}
                    {(detail.narrative || detail.notes) ? (
                        <section className="rounded-xl border border-line bg-surface px-4 py-3 ma-print-section">
                            <h3 className="text-sm font-semibold text-ink">Clinician narrative and notes</h3>
                            {detail.narrative ? <p className="mt-2 whitespace-pre-wrap [overflow-wrap:anywhere] text-sm text-ink">{detail.narrative}</p> : null}
                            {detail.notes ? <p className="mt-2 whitespace-pre-wrap [overflow-wrap:anywhere] text-sm text-ink-2">{detail.notes}</p> : null}
                            <p className="mt-2 text-xs text-muted">Written by the clinician, not generated.</p>
                        </section>
                    ) : null}
                </div>
                <aside className="min-w-0" data-print-hide>
                    <section aria-labelledby="shared-actions" className="rounded-xl border border-line bg-surface p-4">
                        <h2 className="text-sm font-semibold text-ink" id="shared-actions">Print or export</h2>
                        <div className="mt-3 flex flex-wrap gap-2">
                            <Button disabled={busy} onClick={() => void exportAs("print")} variant="secondary">Print</Button>
                            <Button disabled={busy} onClick={() => void exportAs("fhir")} variant="secondary">Export FHIR</Button>
                        </div>
                        <p className="mt-2 text-xs text-muted">Every export is recorded for the author. This summary does not include the patient&apos;s record.</p>
                        <div className="mt-3"><Badge variant="info">Read-only</Badge></div>
                    </section>
                </aside>
            </div>
        </div>
    );
}
