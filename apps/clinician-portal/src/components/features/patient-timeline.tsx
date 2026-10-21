"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button, ErrorState } from "@/components/ui";
import { fetchPatientTimeline, type PatientTimelineResponse } from "@/services/clinicians";

function Timestamp({ value }: { value: string }) {
    const date = Date.parse(value);
    return Number.isFinite(date) ? <time dateTime={value}>{new Date(date).toLocaleString("en-US")}</time> : <>Date unknown</>;
}

export function PatientTimeline({ patientId }: { patientId: string }) {
    const [snapshot, setSnapshot] = useState<PatientTimelineResponse | null>(null);
    const [failedPatient, setFailedPatient] = useState<string | null>(null);
    const [attempt, setAttempt] = useState(0);
    const [expanded, setExpanded] = useState<string | null>(null);
    const data = snapshot?.patient_id === patientId ? snapshot : null;
    const failed = failedPatient === patientId;

    useEffect(() => {
        let active = true;
        fetchPatientTimeline(patientId).then(
            (result) => { if (active) setSnapshot(result); },
            () => { if (active) setFailedPatient(patientId); },
        );
        return () => { active = false; };
    }, [patientId, attempt]);

    useEffect(() => {
        const reveal = () => {
            const target = window.location.hash.slice(1);
            if (target.startsWith("source-")) setExpanded(target.slice("source-".length));
        };
        reveal();
        window.addEventListener("hashchange", reveal);
        return () => window.removeEventListener("hashchange", reveal);
    }, []);

    useEffect(() => {
        if (!data || !expanded) return;
        const target = document.getElementById(`source-${expanded}`);
        target?.focus({ preventScroll: true });
        target?.scrollIntoView?.({ block: "nearest" });
    }, [data, expanded]);

    function refresh() {
        setFailedPatient(null);
        setSnapshot(null);
        setAttempt((value) => value + 1);
    }

    return <section aria-labelledby="tab-btn-timeline" id="tab-panel-timeline" role="tabpanel" className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-ink">Patient timeline</h2>
            <Button onClick={refresh}>Refresh timeline</Button>
        </div>
        <p className="text-sm text-ink-2">Recent source records across documents, medications, confirmed symptoms, adherence, your private conversations, appointments, and recorded approval/action events. At most 40 records per source, with messages from your 10 most recently active conversations for this patient. This bounded view is not a full audit trail. Medication recording is not a dose change; current statuses are not historical snapshots.</p>
        {failed ? <ErrorState title="Unable to load timeline" description="Timeline retrieval failed. No empty-history conclusion can be drawn." onRetry={refresh} /> : !data ? <p role="status" className="text-sm text-muted">Loading timeline…</p> : <>
            <p className="text-xs text-muted">Retrieved <Timestamp value={data.retrieved_at} />. Retrieval time is not a clinical event date.</p>
            {expanded && !data.events.some((event) => event.id === expanded) && <p role="status" className="text-sm text-muted">The linked source is not in this bounded result. Check coverage and refresh; no source deletion or clinical conclusion is implied.</p>}
            <details className="rounded-xl border border-line p-3 text-xs text-muted" open={data.sources.some((source) => source.status === "unavailable" || source.omitted_invalid > 0)}>
                <summary className="cursor-pointer font-medium text-ink-2">Coverage and limits by source</summary>
                <ul className="mt-2 space-y-2">
                    {data.sources.map((source) => <li key={source.source}>
                        <span className="break-all">{source.source}</span>: {source.status === "unavailable" ? <span role="alert">Unavailable — source read failed; retry to check this history.</span> : <>{source.returned} returned; most recent {source.limit} records maximum.{source.has_more ? " More records exist outside this view." : ""}</>}
                        {source.conversation_limit != null && <> Private messages are limited to your {source.conversation_limit} most recently active conversations for this patient; the exact conversation, clinic, assignment and active membership are rechecked.{source.conversations_truncated ? " Additional conversations omitted." : ""}</>}
                        {source.omitted_invalid > 0 && <span role="alert"> {source.omitted_invalid} records omitted because source dates or identity were invalid.</span>}
                    </li>)}
                </ul>
            </details>
            {data.events.length === 0 ? <p className="text-sm text-muted">No dated events returned in this bounded view. Check source coverage above for unavailable or omitted records.</p> : <ol className="divide-y divide-line rounded-xl border border-line bg-surface">
                {data.events.map((event) => <li key={event.id} className="space-y-2 p-4">
                    <div className="flex flex-wrap items-baseline justify-between gap-2">
                        <h3 className="text-sm font-semibold text-ink">{event.title}</h3>
                        <p className="text-xs text-muted">{event.timestamp_label} <Timestamp value={event.occurred_at} /></p>
                    </div>
                    <p className="break-words text-sm text-ink-2">{event.details["file_name"] ?? event.details["name"] ?? event.details["symptom"] ?? event.details["event_type"] ?? event.details["action"] ?? event.details["status"] ?? event.domain}</p>
                    <div className="flex flex-wrap gap-4 text-sm">
                        <Link aria-label={`Source record for ${event.title} ${event.source_id}`} className="text-primary underline" href={event.source_href} onClick={() => setExpanded(event.id)}>Source record</Link>
                        {event.destination_href && <Link aria-label={`Open ${event.domain === "message" ? "your conversation" : "source workspace"} for ${event.source_id}`} className="text-primary underline" href={event.destination_href}>Open {event.domain === "message" ? "your conversation" : "source workspace"}</Link>}
                    </div>
                    <details id={`source-${event.id}`} tabIndex={-1} open={expanded === event.id} className="scroll-mt-24 rounded-lg bg-surface-2 p-3 text-xs text-muted">
                        <summary onClick={(action) => { action.preventDefault(); setExpanded((current) => current === event.id ? null : event.id); }} className="cursor-pointer text-ink-2">Recorded source fields</summary>
                        <dl className="mt-2 space-y-2 break-words">
                            <div><dt className="font-medium">Source</dt><dd>{event.source_table} · {event.source_id}</dd></div>
                            {Object.entries(event.details).map(([key, value]) => <div key={key}><dt className="font-medium">{key.replaceAll("_", " ")}</dt><dd>{value ?? "Unknown / not recorded"}</dd></div>)}
                        </dl>
                    </details>
                </li>)}
            </ol>}
        </>}
    </section>;
}
