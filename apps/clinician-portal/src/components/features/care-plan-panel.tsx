"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { carePlanChanges } from "@/components/features/care-plan-changes";
import { DocumentSourceViewer } from "@/components/features/document-source-viewer";
import {
    approveClinicianCarePlan,
    fetchClinicianCarePlanReviewContext,
    fetchClinicianCarePlanGeneration,
    fetchClinicianDocumentSource,
    retryClinicianCarePlanGeneration,
    updateClinicianCarePlan,
    type CarePlanItem,
    type ClinicianDocumentSource,
    type CarePlanGeneration,
    type CarePlanVersion,
} from "@/services/clinicians";

interface CarePlanPanelProps {
    patientId: string;
}

type EditableItem = CarePlanItem & { clinician_confirmed: boolean };

function displaySource(item: CarePlanItem): string {
    const page = item.source?.location?.page ? ` · page ${item.source.location.page}` : "";
    return item.source?.excerpt ? `“${item.source.excerpt}”${page}` : "Source excerpt unavailable";
}

/** Clinician-controlled publication surface. No browser mutation bypasses this API. */
export function CarePlanPanel({ patientId }: CarePlanPanelProps) {
    const [plan, setPlan] = useState<CarePlanVersion | null>(null);
    const [activePlan, setActivePlan] = useState<CarePlanVersion | null>(null);
    const [patientLocale, setPatientLocale] = useState("en-US");
    const [generation, setGeneration] = useState<CarePlanGeneration | null>(null);
    const [items, setItems] = useState<EditableItem[]>([]);
    const [note, setNote] = useState("");
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [selectedSourceItemId, setSelectedSourceItemId] = useState<string | null>(null);
    const [selectedSourceDocumentId, setSelectedSourceDocumentId] = useState<string | null>(null);
    const [source, setSource] = useState<ClinicianDocumentSource | null>(null);
    const [sourceLoading, setSourceLoading] = useState(false);
    const [sourceError, setSourceError] = useState<string | null>(null);

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const [context, nextGeneration] = await Promise.all([
                fetchClinicianCarePlanReviewContext(patientId),
                fetchClinicianCarePlanGeneration(patientId),
            ]);
            const next = context.latest;
            setPlan(next);
            setActivePlan(context.active ?? (next?.status === "approved" ? next : null));
            setPatientLocale(context.patient_locale);
            setGeneration(nextGeneration);
            setItems((next?.items ?? []).map((item) => ({ ...item, clinician_confirmed: false })));
            setHasUnsavedChanges(false);
            setSelectedSourceItemId(null);
            setSelectedSourceDocumentId(null);
        } catch (cause) {
            setError(cause instanceof Error ? cause.message : "Unable to load the care plan.");
        } finally {
            setLoading(false);
        }
    }, [patientId]);

    useEffect(() => { void load(); }, [load]);

    const selectedSourceItem = useMemo(
        () => items.find((item) => item.id === selectedSourceItemId) ?? null,
        [items, selectedSourceItemId],
    );

    useEffect(() => {
        const documentId = selectedSourceDocumentId;
        if (!documentId) {
            setSource(null);
            setSourceLoading(false);
            setSourceError(null);
            return;
        }
        let cancelled = false;
        setSourceLoading(true);
        setSourceError(null);
        void fetchClinicianDocumentSource(patientId, documentId)
            .then((next) => { if (!cancelled) setSource(next); })
            .catch((cause: unknown) => {
                if (!cancelled) {
                    setSource(null);
                    setSourceError(cause instanceof Error ? cause.message : "Unable to open this source document.");
                }
            })
            .finally(() => { if (!cancelled) setSourceLoading(false); });
        return () => { cancelled = true; };
    }, [patientId, selectedSourceDocumentId]);

    const unresolved = useMemo(
        () => items.filter((item) => !item.is_removed && Boolean(item.blocker_reason) && !item.clinician_confirmed),
        [items],
    );
    const changes = useMemo(() => carePlanChanges(items, activePlan), [items, activePlan]);
    const previousByFact = useMemo(
        () => new Map((activePlan?.items ?? []).filter((item) => item.source_fact_id).map((item) => [item.source_fact_id, item])),
        [activePlan],
    );
    const sourceDocuments = useMemo(() => {
        const byId = new Map<string, string>();
        for (const item of items) {
            for (const source of item.sources ?? (item.source ? [item.source] : [])) {
                if (source.document_id) byId.set(source.document_id, source.file_name || source.document_id);
            }
        }
        return [...byId.entries()];
    }, [items]);

    function patchItem(id: string, change: Partial<EditableItem>) {
        setItems((current) => current.map((item) => item.id === id ? { ...item, ...change } : item));
        setHasUnsavedChanges(true);
    }

    async function save() {
        if (!plan || plan.status !== "draft") return;
        setSaving(true); setError(null);
        try {
            const saved = await updateClinicianCarePlan(patientId, plan.id, items.map((item) => ({
                id: item.id, title: item.title, instructions: item.instructions,
                frequency: item.frequency, schedule: item.schedule, medication: item.medication,
                is_removed: item.is_removed, clinician_confirmed: item.clinician_confirmed,
            })));
            setPlan(saved);
            setItems(saved.items.map((item) => ({ ...item, clinician_confirmed: false })));
            setHasUnsavedChanges(false);
        } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to save the draft."); }
        finally { setSaving(false); }
    }

    async function approve() {
        if (!plan || unresolved.length || !note.trim() || hasUnsavedChanges) return;
        setSaving(true); setError(null);
        try { await approveClinicianCarePlan(patientId, plan.id, note); await load(); }
        catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to approve this care plan."); }
        finally { setSaving(false); }
    }

    async function retry() {
        setSaving(true); setError(null);
        try { await retryClinicianCarePlanGeneration(patientId); await load(); }
        catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to retry draft generation."); }
        finally { setSaving(false); }
    }

    if (loading) return <p className="text-sm text-slate-600">Loading care plan…</p>;
    if (!plan) return <div className="rounded-xl border border-slate-200 bg-slate-50 p-5 text-sm text-slate-700"><p className="font-semibold">{generation?.status === "failed" ? "Automatic evidence draft failed" : "Waiting for an automatic evidence draft"}</p><p className="mt-1">{generation?.status === "failed" ? "The previous approved plan, if any, remains active. Retry uses the same grounded evidence and never publishes a plan automatically." : "A draft is created after newly processed evidence has been quiet for five minutes. Nothing is visible to the patient until approval."}</p>{generation?.status === "failed" ? <button className="mt-3 rounded-lg border border-blue-200 px-3 py-2 text-sm font-semibold text-blue-700 disabled:opacity-60" disabled={saving} onClick={() => void retry()} type="button">Retry generation</button> : null}</div>;

    return <section aria-labelledby="tab-btn-care-plan" id="tab-panel-care-plan" role="tabpanel" className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
            <div><h2 className="text-lg font-semibold text-slate-900">Care plan</h2><p className="text-sm text-slate-600">Version {plan.version_number} · {plan.status === "draft" ? "AI-generated draft — not visible to patient" : `Status: ${plan.status}`}</p></div>
            {generation?.status === "retry" ? <p className="text-sm text-amber-700">Automatic retry scheduled{generation.next_attempt_at ? ` for ${new Date(generation.next_attempt_at).toLocaleString()}` : ""}.</p> : null}
        </div>
        {plan.status === "draft" ? <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-slate-800">
            <p className="font-semibold">Proposed version {plan.version_number} · Patient language: {patientLocale}</p>
            <p className="mt-1">{activePlan ? `Approved version ${activePlan.version_number} remains active in Today until this version is approved.` : "No approved care plan is active yet."} Check every patient-facing instruction against the patient language and source before publication.</p>
            <p className="mt-2 font-medium">Documents linked to proposed items</p>
            {sourceDocuments.length ? <ul className="mt-1 list-disc pl-5">{sourceDocuments.map(([id, name]) => <li key={id}>{name}</li>)}</ul> : <p>No source document is linked to these items.</p>}
            {activePlan ? <details className="mt-3"><summary className="cursor-pointer font-semibold">View currently approved version {activePlan.version_number}</summary><ul className="mt-2 list-disc pl-5">{activePlan.items.filter((item) => !item.is_removed).map((item) => <li key={item.id}>{item.title} · {item.frequency}</li>)}</ul></details> : null}
            <p className="mt-2 text-xs text-slate-600">“New evidence” means a new source fact, not a verified new therapy. Reconcile overlapping medication instructions before approval.</p>
        </div> : null}
        {error ? <p className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700" role="alert">{error}</p> : null}
        {hasUnsavedChanges ? <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">Save your edits before approving. New evidence may have changed the draft while you reviewed it.</p> : null}
        {unresolved.length ? <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">{unresolved.length} unresolved item{unresolved.length === 1 ? "" : "s"} block whole-plan approval. Edit, remove, or explicitly confirm each one.</p> : null}
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(22rem,0.85fr)]">
        <div className="space-y-4">{items.map((item) => <article className={`rounded-xl border p-4 ${item.is_removed ? "border-slate-200 bg-slate-50 opacity-65" : "border-slate-200 bg-white"}`} key={item.id}>
            <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{item.category}{activePlan && plan.status === "draft" ? ` · ${changes.get(item.id)}` : ""}</p><p className="mt-1 text-sm font-semibold text-slate-900">{item.title}</p></div><span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">{item.confidence_score == null ? "Confidence unavailable" : `${Math.round(item.confidence_score * 100)}% confidence`}</span></div>
            {changes.get(item.id) === "edited" && previousByFact.get(item.source_fact_id) ? <div className="mt-2 rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs text-slate-700"><p className="font-semibold">Approved version {activePlan?.version_number} wording</p><p>{previousByFact.get(item.source_fact_id)?.title} — {previousByFact.get(item.source_fact_id)?.instructions} · {previousByFact.get(item.source_fact_id)?.frequency}</p></div> : null}
            {item.source?.file_name ? <p className="mt-1 text-xs text-slate-500">Source: {item.source.file_name}</p> : null}
            {(item.sources?.length ? item.sources : [item.source]).filter((citation) => Boolean(citation?.excerpt)).map((citation, index) => <p className="mt-2 border-l-2 border-blue-200 pl-2 text-xs text-slate-600" key={`${citation?.document_id}-${index}`}>{citation?.file_name ? `${citation.file_name}: ` : ""}“{citation?.excerpt}”{citation?.location?.page ? ` · page ${citation.location.page}` : ""}</p>)}
            {!item.source?.excerpt ? <p className="mt-2 border-l-2 border-blue-200 pl-2 text-xs text-slate-600">{displaySource(item)}</p> : null}
            {(item.sources ?? (item.source ? [item.source] : [])).filter((source) => source.document_id).map((source, index) => <button aria-pressed={selectedSourceItemId === item.id && selectedSourceDocumentId === source.document_id} className="mr-2 mt-3 rounded-lg border border-blue-200 px-3 py-2 text-sm font-semibold text-blue-700 hover:bg-blue-50" key={`${source.document_id}-${index}`} onClick={() => { setSelectedSourceItemId(item.id); setSelectedSourceDocumentId(source.document_id ?? null); }} type="button">{index === 0 ? "Review source beside item" : `Review source: ${source.file_name || source.document_id}`}</button>)}
            {plan.status === "draft" ? <div className="mt-3 grid gap-3 md:grid-cols-3"><label className="text-xs font-semibold text-slate-600">Title<input className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm" value={item.title} onChange={(event) => patchItem(item.id, { title: event.target.value })} /></label><label className="text-xs font-semibold text-slate-600">Instructions<input className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm" value={item.instructions} onChange={(event) => patchItem(item.id, { instructions: event.target.value })} /></label><label className="text-xs font-semibold text-slate-600">Frequency<input className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm" value={item.frequency} onChange={(event) => patchItem(item.id, { frequency: event.target.value })} /></label></div> : <p className="mt-3 text-sm text-slate-700">{item.instructions} · {item.frequency}</p>}
            {item.blocker_reason && !item.is_removed ? <div className="mt-3 flex flex-wrap items-center gap-3"><p className="text-sm text-amber-800">{item.blocker_reason}</p>{plan.status === "draft" ? <label className="flex items-center gap-2 text-sm text-slate-700"><input checked={item.clinician_confirmed} type="checkbox" onChange={(event) => patchItem(item.id, { clinician_confirmed: event.target.checked })} /> Confirm after review</label> : null}</div> : null}
            {plan.status === "draft" ? <label className="mt-3 flex items-center gap-2 text-sm text-slate-600"><input checked={item.is_removed} type="checkbox" onChange={(event) => patchItem(item.id, { is_removed: event.target.checked })} /> Remove from this version</label> : null}
        </article>)}</div>
        <aside className="min-h-80 rounded-xl border border-slate-200 bg-slate-50 p-3"><p className="mb-3 text-sm font-semibold text-slate-900">Protected source preview</p>{!selectedSourceItem ? <p className="text-sm text-slate-600">Select an item with document evidence to inspect its authorized source beside the draft.</p> : null}{selectedSourceItem && !selectedSourceDocumentId ? <p className="text-sm text-slate-600">This is a clinician-authored entry. Its recorded instruction is shown in the source excerpt; no document preview is available.</p> : null}{sourceLoading ? <p className="text-sm text-slate-600">Loading source preview…</p> : null}{sourceError ? <p className="rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{sourceError}</p> : null}{source ? <DocumentSourceViewer fileName={source.file_name} previewMimeType={source.preview_mime_type} previewStatus={source.preview_status} previewUrl={source.preview_url} sourceMimeType={source.mime_type} sourceUrl={source.file_url} /> : null}</aside>
        </div>
        {plan.status === "draft" ? <div className="rounded-xl border border-slate-200 bg-slate-50 p-4"><h3 className="font-semibold text-slate-900">Proposed publication summary</h3><p className="mt-1 text-sm text-slate-600">These items would be projected to Today after approval. This is not an exact Today preview; patient timezone and reminder settings affect the final display.</p><ul className="mt-2 list-disc pl-5 text-sm text-slate-700">{items.filter((item) => !item.is_removed).map((item) => <li key={item.id}>{item.title} — {item.instructions} · {item.frequency}</li>)}</ul><label className="mt-3 block text-sm font-medium text-slate-700">Approval note<textarea className="mt-1 min-h-20 w-full rounded-lg border border-slate-300 p-2" placeholder="Record the basis for your approval." value={note} onChange={(event) => setNote(event.target.value)} /></label><div className="mt-3 flex gap-3"><button className="rounded-lg border border-blue-200 px-3 py-2 text-sm font-semibold text-blue-700 disabled:opacity-60" disabled={saving} onClick={() => void save()} type="button">{saving ? "Saving…" : "Save review"}</button><button className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-60" disabled={saving || hasUnsavedChanges || unresolved.length > 0 || !note.trim()} onClick={() => void approve()} type="button">Approve and publish plan</button></div></div> : null}
    </section>;
}
