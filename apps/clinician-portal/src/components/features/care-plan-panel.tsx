"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
    approveClinicianCarePlan,
    fetchClinicianCarePlan,
    retryClinicianCarePlanGeneration,
    updateClinicianCarePlan,
    type CarePlanItem,
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
    const [items, setItems] = useState<EditableItem[]>([]);
    const [note, setNote] = useState("");
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const next = await fetchClinicianCarePlan(patientId);
            setPlan(next);
            setItems((next?.items ?? []).map((item) => ({ ...item, clinician_confirmed: false })));
        } catch (cause) {
            setError(cause instanceof Error ? cause.message : "Unable to load the care plan.");
        } finally {
            setLoading(false);
        }
    }, [patientId]);

    useEffect(() => { void load(); }, [load]);

    const unresolved = useMemo(
        () => items.filter((item) => !item.is_removed && Boolean(item.blocker_reason) && !item.clinician_confirmed),
        [items],
    );

    function patchItem(id: string, change: Partial<EditableItem>) {
        setItems((current) => current.map((item) => item.id === id ? { ...item, ...change } : item));
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
        } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to save the draft."); }
        finally { setSaving(false); }
    }

    async function approve() {
        if (!plan || unresolved.length || !note.trim()) return;
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
    if (!plan) return <div className="rounded-xl border border-slate-200 bg-slate-50 p-5 text-sm text-slate-700"><p className="font-semibold">Waiting for an automatic evidence draft</p><p className="mt-1">A draft is created after newly processed evidence has been quiet for five minutes. Nothing is visible to the patient until approval.</p></div>;

    return <section aria-labelledby="tab-btn-care-plan" id="tab-panel-care-plan" role="tabpanel" className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
            <div><h2 className="text-lg font-semibold text-slate-900">Care plan</h2><p className="text-sm text-slate-600">Version {plan.version_number} · {plan.status === "draft" ? "AI-generated draft — not visible to patient" : `Status: ${plan.status}`}</p></div>
            {plan.status === "generation_failed" ? <button className="rounded-lg border border-blue-200 px-3 py-2 text-sm font-semibold text-blue-700 disabled:opacity-60" disabled={saving} onClick={() => void retry()} type="button">Retry generation</button> : null}
        </div>
        {error ? <p className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700" role="alert">{error}</p> : null}
        {unresolved.length ? <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">{unresolved.length} unresolved item{unresolved.length === 1 ? "" : "s"} block whole-plan approval. Edit, remove, or explicitly confirm each one.</p> : null}
        {items.map((item) => <article className={`rounded-xl border p-4 ${item.is_removed ? "border-slate-200 bg-slate-50 opacity-65" : "border-slate-200 bg-white"}`} key={item.id}>
            <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{item.category}</p><p className="mt-1 text-sm font-semibold text-slate-900">{item.title}</p></div><span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">{item.confidence_score == null ? "Confidence unavailable" : `${Math.round(item.confidence_score * 100)}% confidence`}</span></div>
            <p className="mt-2 border-l-2 border-blue-200 pl-2 text-xs text-slate-600">{displaySource(item)}</p>
            {plan.status === "draft" ? <div className="mt-3 grid gap-3 md:grid-cols-3"><label className="text-xs font-semibold text-slate-600">Title<input className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm" value={item.title} onChange={(event) => patchItem(item.id, { title: event.target.value })} /></label><label className="text-xs font-semibold text-slate-600">Instructions<input className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm" value={item.instructions} onChange={(event) => patchItem(item.id, { instructions: event.target.value })} /></label><label className="text-xs font-semibold text-slate-600">Frequency<input className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm" value={item.frequency} onChange={(event) => patchItem(item.id, { frequency: event.target.value })} /></label></div> : <p className="mt-3 text-sm text-slate-700">{item.instructions} · {item.frequency}</p>}
            {item.blocker_reason && !item.is_removed ? <div className="mt-3 flex flex-wrap items-center gap-3"><p className="text-sm text-amber-800">{item.blocker_reason}</p>{plan.status === "draft" ? <label className="flex items-center gap-2 text-sm text-slate-700"><input checked={item.clinician_confirmed} type="checkbox" onChange={(event) => patchItem(item.id, { clinician_confirmed: event.target.checked })} /> Confirm after review</label> : null}</div> : null}
            {plan.status === "draft" ? <label className="mt-3 flex items-center gap-2 text-sm text-slate-600"><input checked={item.is_removed} type="checkbox" onChange={(event) => patchItem(item.id, { is_removed: event.target.checked })} /> Remove from this version</label> : null}
        </article>)}
        {plan.status === "draft" ? <div className="rounded-xl border border-slate-200 bg-slate-50 p-4"><h3 className="font-semibold text-slate-900">Patient-visible preview</h3><p className="mt-1 text-sm text-slate-600">Only the active items above, after approval, will be projected to Today.</p><label className="mt-3 block text-sm font-medium text-slate-700">Approval note<textarea className="mt-1 min-h-20 w-full rounded-lg border border-slate-300 p-2" placeholder="Record the basis for your approval." value={note} onChange={(event) => setNote(event.target.value)} /></label><div className="mt-3 flex gap-3"><button className="rounded-lg border border-blue-200 px-3 py-2 text-sm font-semibold text-blue-700 disabled:opacity-60" disabled={saving} onClick={() => void save()} type="button">{saving ? "Saving…" : "Save review"}</button><button className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-60" disabled={saving || unresolved.length > 0 || !note.trim()} onClick={() => void approve()} type="button">Approve and publish plan</button></div></div> : null}
    </section>;
}
