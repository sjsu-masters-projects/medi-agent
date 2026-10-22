"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Badge, Button, ErrorState, Modal, Skeleton } from "@/components/ui";
import { ApprovalSeal } from "@/components/ui/approval-seal";
import { ApiClientError } from "@/services/api";
import { errorCode } from "@/services/care-team-plans";
import {
    approveHandoffSummary,
    exportHandoffSummary,
    fetchHandoffSummary,
    saveHandoffSummary,
    type HandoffDetail,
    type HandoffItem,
    type HandoffSection,
} from "@/services/handoff-summaries";

const EVENT_LABELS: Record<string, string> = {
    created: "Draft built",
    edited: "Edited",
    refreshed: "Rebuilt from current records",
    approved: "Approved",
    exported: "Exported",
};

function stamp(value: string): string {
    return value.replace("T", " ").slice(0, 16);
}

function SourceChip({ item }: { item: HandoffItem }) {
    const chip = "inline-flex max-w-full items-center rounded-md border border-line bg-surface-2 px-2 py-0.5 text-xs text-ink-2";
    if (item.source.href) {
        return <Link className={`${chip} break-words hover:bg-sunken hover:text-ink`} href={item.source.href}>Source: {item.source.label}</Link>;
    }
    return <span className={`${chip} break-words`}>Source: {item.source.label}</span>;
}

function Section({ section }: { section: HandoffSection }) {
    const [open, setOpen] = useState(true);
    const panel = `handoff-section-${section.key}`;
    return (
        <section className="rounded-xl border border-line bg-surface ma-print-section" data-testid={`section-${section.key}`}>
            <h3>
                <button aria-controls={panel} aria-expanded={open} className="flex min-h-11 w-full items-center justify-between gap-3 px-4 py-2.5 text-left text-sm font-semibold text-ink" onClick={() => setOpen(!open)} type="button">
                    <span>{section.title}</span>
                    <span className="flex items-center gap-2 text-xs font-normal text-muted">
                        {section.status === "unavailable" ? <Badge variant="danger">Unavailable</Badge> : `${section.items.length} ${section.items.length === 1 ? "line" : "lines"}`}
                        <span aria-hidden="true">{open ? "−" : "+"}</span>
                    </span>
                </button>
            </h3>
            <div className={`border-t border-line px-4 py-3 ${open ? "" : "hidden print:block"}`} id={panel}>
                {section.note ? <p className={`mb-2 text-sm ${section.status === "unavailable" ? "font-medium text-risk-ink" : "text-muted"}`} role={section.status === "unavailable" ? "alert" : undefined}>{section.note}</p> : null}
                <ul className="space-y-3">
                    {section.items.map((item) => (
                        <li className="min-w-0" key={item.id}>
                            <p className="break-words text-sm text-ink">{item.text}</p>
                            {item.detail ? <p className="break-words text-xs text-muted">{item.detail}</p> : null}
                            <div className="mt-1"><SourceChip item={item} /></div>
                        </li>
                    ))}
                </ul>
            </div>
        </section>
    );
}

/** Review, edit, approve and export one handoff summary. */
export function HandoffSummaryReview({ patientId, summaryId }: { patientId: string; summaryId: string }) {
    const [detail, setDetail] = useState<HandoffDetail | null>(null);
    const [viewing, setViewing] = useState<number | null>(null);
    const [state, setState] = useState<"loading" | "ready" | "denied" | "error">("loading");
    const [narrative, setNarrative] = useState("");
    const [notes, setNotes] = useState("");
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
    const [confirming, setConfirming] = useState(false);

    const adopt = useCallback((next: HandoffDetail) => {
        setDetail(next);
        setNarrative(next.version.narrative ?? "");
        setNotes(next.version.notes ?? "");
    }, []);

    const load = useCallback(async (version?: number) => {
        setState("loading");
        try {
            adopt(await fetchHandoffSummary(patientId, summaryId, version));
            setViewing(version ?? null);
            setState("ready");
        } catch (failure) {
            const status = failure instanceof ApiClientError ? failure.status : 0;
            setState(status === 403 || status === 404 ? "denied" : "error");
        }
    }, [adopt, patientId, summaryId]);

    useEffect(() => {
        void load();
    }, [load]);

    if (state === "loading" && !detail) {
        return <div aria-label="Loading handoff summary" className="space-y-4" role="status"><Skeleton className="h-8 w-64" /><Skeleton className="h-48 w-full" /></div>;
    }
    if (state === "denied") {
        return <ErrorState description="This summary does not exist or is not available to you." title="Summary not available" />;
    }
    if (state === "error" || !detail) {
        return <ErrorState description="The summary could not be loaded." onRetry={() => void load()} title="Unable to load this summary" />;
    }

    const readOnly = viewing !== null && viewing !== detail.current_version;
    const dirty = !readOnly && (narrative.trim() !== (detail.version.narrative ?? "") || notes.trim() !== (detail.version.notes ?? ""));
    const approved = detail.status === "approved" && detail.approved_version === detail.current_version;
    const unavailable = detail.version.sections.some((section) => section.status === "unavailable");
    const canExport = approved && !dirty && !readOnly;

    async function run(action: () => Promise<void>) {
        setBusy(true);
        setMessage(null);
        try {
            await action();
        } catch (failure) {
            const code = errorCode(failure);
            setMessage({
                tone: "error",
                text: code === "HANDOFF_VERSION_CONFLICT"
                    ? "This summary changed since you opened it. Reload to review the latest version."
                    : code === "HANDOFF_SECTION_UNAVAILABLE"
                        ? "A section could not be read. Rebuild the summary before approving it."
                        : code === "HANDOFF_NOT_APPROVED"
                            ? "Approve the current version before exporting it."
                            : "That did not complete. Nothing was changed. Try again.",
            });
        } finally {
            setBusy(false);
        }
    }

    const save = (refresh: boolean) => run(async () => {
        adopt(await saveHandoffSummary(patientId, summaryId, {
            expected_version: detail.current_version,
            narrative: narrative.trim() || null,
            notes: notes.trim() || null,
            refresh,
        }));
        setMessage({ tone: "ok", text: refresh ? "Rebuilt from current records as a new version." : "Saved as a new version." });
    });

    const approve = () => run(async () => {
        setConfirming(false);
        adopt(await approveHandoffSummary(patientId, summaryId, detail.current_version));
        setMessage({ tone: "ok", text: "Approved. This version can now be exported." });
    });

    const exportAs = (format: "print" | "fhir") => run(async () => {
        const result = await exportHandoffSummary(patientId, summaryId, detail.current_version, format);
        adopt(await fetchHandoffSummary(patientId, summaryId));
        if (format === "fhir" && result.bundle) {
            const blob = new Blob([JSON.stringify(result.bundle, null, 2)], { type: "application/fhir+json" });
            const url = URL.createObjectURL(blob);
            const anchor = document.createElement("a");
            anchor.href = url;
            anchor.download = `handoff-summary-v${result.summary.version.version}.fhir.json`;
            document.body.appendChild(anchor);
            anchor.click();
            anchor.remove();
            URL.revokeObjectURL(url);
            setMessage({ tone: "ok", text: "FHIR bundle exported and recorded in the audit history." });
        } else {
            setMessage({ tone: "ok", text: "Print export recorded in the audit history." });
            window.print();
        }
    });

    return (
        <div className="space-y-5">
            <header className="flex flex-wrap items-start justify-between gap-3" data-print-hide>
                <div className="min-w-0">
                    <Link className="text-[13px] font-medium text-primary" href={`/patients/${encodeURIComponent(patientId)}/handoff`}>All handoff summaries</Link>
                    <h1 className="mt-1 break-words text-[24px] font-semibold leading-tight tracking-[-0.02em] text-ink">{detail.title}</h1>
                    <p className="mt-1 text-sm text-muted">Version {detail.current_version}{detail.recipient_label ? ` · for ${detail.recipient_label}` : ""}</p>
                </div>
                {approved ? <ApprovalSeal pill>Approved</ApprovalSeal> : <Badge variant="neutral">Draft, not approved</Badge>}
            </header>

            {message ? <p className={`rounded-xl border px-4 py-3 text-sm ${message.tone === "ok" ? "border-ok-line bg-ok-soft text-ok-ink" : "border-risk-line bg-risk-soft text-risk-ink"}`} data-print-hide role={message.tone === "ok" ? "status" : "alert"}>{message.text}</p> : null}
            {readOnly ? (
                <p className="rounded-xl border border-warn-line bg-warn-soft px-4 py-3 text-sm text-warn-ink" data-print-hide role="status">
                    You are viewing version {viewing}, which is read-only. <button className="font-semibold underline" onClick={() => void load()} type="button">Back to the current version</button>
                </p>
            ) : null}

            <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
                <div className="ma-print-root min-w-0 space-y-4">
                    <div className="rounded-xl border border-line bg-surface px-4 py-3">
                        <p className="text-sm font-semibold text-ink">{detail.title}</p>
                        <p className="text-xs text-muted">
                            {detail.patient_name ? `${detail.patient_name} · ` : ""}Built {stamp(detail.version.built_at)} from records visible to the author. Synthetic demo data.
                        </p>
                        <p className="mt-1 text-xs text-muted" data-print-hide>Assembled without a model. Each line shows the record it came from.</p>
                    </div>
                    {detail.version.sections.map((section) => <Section key={section.key} section={section} />)}
                    {(detail.version.narrative || detail.version.notes) ? (
                        <section className="rounded-xl border border-line bg-surface px-4 py-3 ma-print-section">
                            <h3 className="text-sm font-semibold text-ink">Clinician narrative and notes</h3>
                            {detail.version.narrative ? <p className="mt-2 whitespace-pre-wrap break-words text-sm text-ink">{detail.version.narrative}</p> : null}
                            {detail.version.notes ? <p className="mt-2 whitespace-pre-wrap break-words text-sm text-ink-2">{detail.version.notes}</p> : null}
                            <p className="mt-2 text-xs text-muted">Written by the clinician, not generated.</p>
                        </section>
                    ) : null}
                    {approved && detail.approved_at ? <p className="text-xs text-muted">Approved {stamp(detail.approved_at)}. Not submitted anywhere by MediAgent.</p> : null}
                </div>

                <aside className="space-y-4" data-print-hide>
                    {!readOnly ? (
                        <section aria-labelledby="handoff-edit" className="rounded-xl border border-line bg-surface p-4">
                            <h2 className="text-sm font-semibold text-ink" id="handoff-edit">Your narrative and notes</h2>
                            <label className="mt-3 block">
                                <span className="mb-1 block text-[13px] font-medium text-ink-2">Narrative</span>
                                <textarea className="min-h-28 w-full rounded-lg border border-line-strong bg-surface p-2.5 text-sm text-ink" maxLength={4000} onChange={(event) => setNarrative(event.target.value)} value={narrative} />
                            </label>
                            <label className="mt-3 block">
                                <span className="mb-1 block text-[13px] font-medium text-ink-2">Notes for the recipient</span>
                                <textarea className="min-h-20 w-full rounded-lg border border-line-strong bg-surface p-2.5 text-sm text-ink" maxLength={4000} onChange={(event) => setNotes(event.target.value)} value={notes} />
                            </label>
                            <div className="mt-3 flex flex-wrap gap-2">
                                <Button disabled={busy || !dirty} onClick={() => void save(false)} variant="secondary">Save changes</Button>
                                <Button disabled={busy || dirty} onClick={() => void save(true)} variant="ghost">Rebuild from records</Button>
                            </div>
                            {dirty ? <p className="mt-2 text-xs text-muted">Save your changes before approving or exporting.</p> : null}
                        </section>
                    ) : null}

                    <section aria-labelledby="handoff-actions" className="rounded-xl border border-line bg-surface p-4">
                        <h2 className="text-sm font-semibold text-ink" id="handoff-actions">Approve and export</h2>
                        {unavailable ? <p className="mt-2 text-sm text-risk-ink">A section could not be read. Rebuild the summary before approving it.</p> : null}
                        <div className="mt-3 flex flex-wrap gap-2">
                            <Button disabled={busy || approved || dirty || readOnly || unavailable} onClick={() => setConfirming(true)} variant="approve">Approve</Button>
                            <Button disabled={busy || !canExport} onClick={() => void exportAs("print")} variant="secondary">Print</Button>
                            <Button disabled={busy || !canExport} onClick={() => void exportAs("fhir")} variant="secondary">Export FHIR</Button>
                        </div>
                        {!approved ? <p className="mt-2 text-xs text-muted">Export is available once this version is approved. Editing an approved summary returns it to draft.</p> : null}
                    </section>

                    <section aria-labelledby="handoff-history" className="rounded-xl border border-line bg-surface p-4">
                        <h2 className="text-sm font-semibold text-ink" id="handoff-history">Version history</h2>
                        <ul className="mt-2 space-y-1.5">
                            {detail.versions.map((version) => (
                                <li className="flex items-center justify-between gap-2 text-sm" key={version.version}>
                                    <span className="text-ink-2">Version {version.version} · {stamp(version.created_at)}</span>
                                    {version.version === (viewing ?? detail.current_version) ? <Badge variant="info">Viewing</Badge> : <button className="text-xs font-semibold text-primary" onClick={() => void load(version.version)} type="button">View version {version.version}</button>}
                                </li>
                            ))}
                        </ul>
                        <h3 className="mt-4 text-[13px] font-semibold text-ink">Audit</h3>
                        <ul className="mt-1 space-y-1">
                            {detail.events.map((event, index) => (
                                <li className="text-xs text-muted" key={`${event.created_at}-${index}`}>
                                    {EVENT_LABELS[event.event_type] ?? event.event_type}{event.export_format ? ` (${event.export_format})` : ""} · v{event.version} · {stamp(event.created_at)}
                                </li>
                            ))}
                        </ul>
                    </section>
                </aside>
            </div>

            <Modal onClose={() => setConfirming(false)} open={confirming} title="Approve this handoff summary?">
                <p className="text-sm text-ink-2">Approving version {detail.current_version} confirms you reviewed every section and line. It can then be exported. Editing it later returns it to draft.</p>
                <div className="mt-4 flex justify-end gap-2">
                    <Button onClick={() => setConfirming(false)} variant="secondary">Cancel</Button>
                    <Button disabled={busy} onClick={() => void approve()} variant="approve">Approve version {detail.current_version}</Button>
                </div>
            </Modal>
        </div>
    );
}
