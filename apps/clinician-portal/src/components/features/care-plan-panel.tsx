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
    type CarePlanReviewContext,
} from "@/services/clinicians";

interface CarePlanPanelProps {
    patientId: string;
    onPublished?: () => void;
}

type EditableItem = CarePlanItem & { clinician_confirmed: boolean; language_verified: boolean };
type ActiveMedication = CarePlanReviewContext["active_medications"][number];

function distinctSources(item: CarePlanItem) {
    const unique: NonNullable<CarePlanItem["sources"]> = [];
    for (const source of item.sources?.length ? item.sources : item.source ? [item.source] : []) {
        const excerpt = source.excerpt?.replace(/\s+/g, " ").trim() ?? "";
        const index = unique.findIndex((prior) => {
            const earlier = prior.excerpt?.replace(/\s+/g, " ").trim() ?? "";
            return prior.document_id === source.document_id && prior.location?.page === source.location?.page &&
                (earlier === excerpt || Boolean(earlier && excerpt && (earlier.includes(excerpt) || excerpt.includes(earlier))));
        });
        if (index < 0) unique.push(source);
        else if (excerpt.length > (unique[index].excerpt?.length ?? 0)) unique[index] = source;
    }
    return unique;
}

function medicationText(value: unknown): string {
    return typeof value === "string" ? value : "";
}

function missingRequiredEvidence(item: CarePlanItem): boolean {
    return !item.title.trim() || !item.instructions.trim() || !item.frequency.trim() ||
        item.frequency.trim().toLowerCase() === "as directed" ||
        (item.category === "medication" && ["name", "dosage", "route", "frequency"].some(
            (field) => !medicationText(item.medication[field]).trim(),
        ));
}

function distinctDocuments(item: CarePlanItem) {
    const byDocument = new Map<string, ReturnType<typeof distinctSources>[number]>();
    for (const source of distinctSources(item)) {
        if (source.document_id && !byDocument.has(source.document_id)) byDocument.set(source.document_id, source);
    }
    return [...byDocument.values()];
}

function displaySource(item: CarePlanItem): string {
    const page = item.source?.location?.page ? ` · page ${item.source.location.page}` : "";
    return item.source?.excerpt ? `“${item.source.excerpt}”${page}` : "Source excerpt unavailable";
}

/** Clinician-controlled publication surface. No browser mutation bypasses this API. */
export function CarePlanPanel({ patientId, onPublished }: CarePlanPanelProps) {
    const [plan, setPlan] = useState<CarePlanVersion | null>(null);
    const [activePlan, setActivePlan] = useState<CarePlanVersion | null>(null);
    const [patientLocale, setPatientLocale] = useState("en-US");
    const [activeMedications, setActiveMedications] = useState<ActiveMedication[]>([]);
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
    const [sourceRetry, setSourceRetry] = useState(0);

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
            setActiveMedications(context.active_medications ?? []);
            setGeneration(nextGeneration);
            setItems((next?.items ?? []).map((item) => ({ ...item, clinician_confirmed: false, language_verified: item.reviewed_locale === context.patient_locale })));
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
        setSource(null);
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
    }, [patientId, selectedSourceDocumentId, sourceRetry]);

    const unresolved = useMemo(
        () => items.filter((item) => !item.is_removed && (missingRequiredEvidence(item) || Boolean(item.blocker_reason) && !item.clinician_confirmed)),
        [items],
    );
    const unverified = items.filter((item) => !item.is_removed && !item.language_verified);
    const undecidedMedications = items.filter((item) => !item.is_removed && item.category === "medication" && !["create", "update"].includes(medicationText(item.medication.decision)));
    const generationBlocked = Boolean(generation && generation.status !== "completed");
    const changes = useMemo(() => carePlanChanges(items, activePlan), [items, activePlan]);
    const previousByFact = useMemo(
        () => new Map((activePlan?.items ?? []).filter((item) => item.source_fact_id).map((item) => [item.source_fact_id, item])),
        [activePlan],
    );
    const sourceDocuments = useMemo(() => {
        const byId = new Map<string, string>();
        for (const item of items) {
            for (const source of distinctSources(item)) {
                if (source.document_id) byId.set(source.document_id, source.file_name || source.document_id);
            }
        }
        return [...byId.entries()];
    }, [items]);

    function patchItem(id: string, change: Partial<EditableItem>) {
        setItems((current) => current.map((item) => item.id === id ? {
            ...item, ...change,
            language_verified: change.language_verified ?? (change.is_removed === true ? false : item.language_verified && change.title === undefined && change.instructions === undefined && change.frequency === undefined && change.medication === undefined),
        } : item));
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
                language_verified: item.language_verified,
                verified_locale: item.language_verified && (patientLocale === "en-US" || patientLocale === "es-MX") ? patientLocale : null,
            })));
            setPlan(saved);
            setItems(saved.items.map((item) => ({ ...item, clinician_confirmed: false, language_verified: item.reviewed_locale === patientLocale })));
            setHasUnsavedChanges(false);
        } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to save the draft."); }
        finally { setSaving(false); }
    }

    async function approve() {
        if (!plan || generationBlocked || unresolved.length || unverified.length || undecidedMedications.length || !note.trim() || hasUnsavedChanges) return;
        setSaving(true); setError(null);
        try { await approveClinicianCarePlan(patientId, plan.id, note); await load(); onPublished?.(); }
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
    if (!plan && error) return <div className="rounded-xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-800" role="alert"><p className="font-semibold">Care plan could not be loaded</p><p className="mt-1">{error}</p><button className="mt-3 rounded-lg border border-rose-300 px-3 py-2 font-semibold" onClick={() => void load()} type="button">Try again</button></div>;
    if (!plan) return <div className="rounded-xl border border-slate-200 bg-slate-50 p-5 text-sm text-slate-700"><p className="font-semibold">{generation?.status === "failed" ? "Automatic evidence draft failed" : "Waiting for an automatic evidence draft"}</p><p className="mt-1">{generation?.status === "failed" ? "The previous approved plan, if any, remains active. Retry uses the same grounded evidence and never publishes a plan automatically." : "A draft is created after newly processed evidence has been quiet for five minutes. Nothing is visible to the patient until approval."}</p>{generation?.status === "failed" ? <button className="mt-3 rounded-lg border border-blue-200 px-3 py-2 text-sm font-semibold text-blue-700 disabled:opacity-60" disabled={saving} onClick={() => void retry()} type="button">Retry generation</button> : null}</div>;

    return <section aria-labelledby="tab-btn-care-plan" id="tab-panel-care-plan" role="tabpanel" className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
            <div><h2 className="text-lg font-semibold text-slate-900">Care plan</h2><p className="text-sm text-slate-600">Version {plan.version_number} · {plan.status === "draft" ? "AI-generated draft — not visible to patient" : `Status: ${plan.status}`}</p></div>
            {generation?.status === "retry" ? <p className="text-sm text-amber-700">Automatic retry scheduled{generation.next_attempt_at ? ` for ${new Date(generation.next_attempt_at).toLocaleString()}` : ""}.</p> : null}
        </div>
        {plan.status === "approved" && generation && generation.status !== "completed" ? <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-slate-800">
            <p className="font-semibold">{generation.status === "failed" ? "New-evidence draft failed" : generation.status === "processing" ? "Preparing a new-evidence draft" : "New evidence is queued for a draft"}</p>
            <p className="mt-1">Approved version {plan.version_number} remains active. A replacement is never published without clinician review and approval.</p>
            {generation.status === "pending" ? <p className="mt-1">Generation waits for a five-minute evidence quiet window and the next worker run.</p> : null}
            {generation.status === "failed" ? <button className="mt-2 rounded-lg border border-blue-200 bg-white px-3 py-2 font-semibold text-blue-700" disabled={saving} onClick={() => void retry()} type="button">Retry generation</button> : null}
        </div> : null}
        {plan.status === "draft" ? <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-slate-800">
            <p className="font-semibold">Proposed version {plan.version_number} · Patient language: {patientLocale}</p>
            <p className="mt-1">{activePlan ? `Approved version ${activePlan.version_number} remains active in Today until this version is approved.` : "No approved care plan is active yet."} Check every patient-facing instruction against the patient language and source before publication.</p>
            <p className="mt-2 font-medium">Documents linked to proposed items</p>
            {sourceDocuments.length ? <ul className="mt-1 list-disc pl-5">{sourceDocuments.map(([id, name]) => <li key={id}>{name}</li>)}</ul> : <p>No source document is linked to these items.</p>}
            {activePlan ? <details className="mt-3"><summary className="cursor-pointer font-semibold">View currently approved version {activePlan.version_number}</summary><ul className="mt-2 list-disc pl-5">{activePlan.items.filter((item) => !item.is_removed).map((item) => <li key={item.id}>{item.title} · {item.frequency}</li>)}</ul></details> : null}
            <p className="mt-2 text-xs text-slate-600">“New evidence” means a new source fact, not a verified new therapy. Reconcile overlapping medication instructions before approval.</p>
        </div> : null}
        {plan.status === "draft" && generationBlocked ? <div role="alert" className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
            <p className="font-semibold">{generation?.status === "failed" ? "Draft generation failed — publication blocked" : "Draft generation is incomplete — publication blocked"}</p>
            <p className="mt-1">The displayed draft may contain only part of the evidence. Generation must complete before publication. The previous approved plan, if any, remains active.</p>
            {generation?.failure_code === "source_fields_incomplete" ? <p className="mt-1">Some source facts lack required wording or exceed the draft field limits. Repeating the same request will not repair this evidence; the draft persistence contract needs repair.</p> : null}
            {generation?.status === "failed" ? <button className="mt-2 rounded-lg border border-blue-200 bg-white px-3 py-2 font-semibold text-blue-700" disabled={saving} onClick={() => void retry()} type="button">Retry generation</button> : null}
        </div> : null}
        {error ? <p className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700" role="alert">{error}</p> : null}
        {hasUnsavedChanges ? <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">Save your edits before approving. New evidence may have changed the draft while you reviewed it.</p> : null}
        {unresolved.length ? <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">{unresolved.length} unresolved item{unresolved.length === 1 ? "" : "s"} block whole-plan approval. Edit, remove, or explicitly confirm each one.</p> : null}
        {unverified.length ? <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">Verify the final patient-facing wording of {unverified.length} item{unverified.length === 1 ? "" : "s"} in {patientLocale} before approval. This review does not translate source text automatically.</p> : null}
        {undecidedMedications.length ? <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">Choose whether each medication updates a matching active record or creates a new record. Remove an unchanged proposal rather than publishing a duplicate.</p> : null}
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(22rem,0.85fr)]">
        <div className="space-y-4">{items.map((item) => <article className={`rounded-xl border p-4 ${item.is_removed ? "border-slate-200 bg-slate-50 opacity-65" : "border-slate-200 bg-white"}`} key={item.id}>
            <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{item.category}{activePlan && plan.status === "draft" ? ` · ${changes.get(item.id)}` : ""}</p><p className="mt-1 text-sm font-semibold text-slate-900">{item.title}</p></div><span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">{item.confidence_score == null ? "Confidence unavailable" : `${Math.round(item.confidence_score * 100)}% confidence`}</span></div>
            {changes.get(item.id) === "edited" && previousByFact.get(item.source_fact_id) ? <div className="mt-2 rounded-lg border border-slate-200 bg-slate-50 p-2 text-xs text-slate-700"><p className="font-semibold">Approved version {activePlan?.version_number} wording</p><p>{previousByFact.get(item.source_fact_id)?.title} — {previousByFact.get(item.source_fact_id)?.instructions} · {previousByFact.get(item.source_fact_id)?.frequency}</p></div> : null}
            {item.source?.file_name ? <p className="mt-1 text-xs text-slate-500">Source: {item.source.file_name}</p> : null}
            {distinctSources(item).filter((citation) => Boolean(citation.excerpt)).map((citation, index) => <p className="mt-2 border-l-2 border-blue-200 pl-2 text-xs text-slate-600" key={`${citation.document_id}-${index}`}>{citation.file_name ? `${citation.file_name}: ` : ""}“{citation.excerpt}”{citation.location?.page ? ` · page ${citation.location.page}` : ""}</p>)}
            {!item.source?.excerpt ? <p className="mt-2 border-l-2 border-blue-200 pl-2 text-xs text-slate-600">{displaySource(item)}</p> : null}
            {distinctDocuments(item).map((source) => <button aria-pressed={selectedSourceItemId === item.id && selectedSourceDocumentId === source.document_id} className="mr-2 mt-3 rounded-lg border border-blue-200 px-3 py-2 text-sm font-semibold text-blue-700 hover:bg-blue-50" key={source.document_id} onClick={() => { setSelectedSourceItemId(item.id); setSelectedSourceDocumentId(source.document_id ?? null); }} type="button">Review source: {source.file_name || source.document_id}</button>)}
            {plan.status === "draft" ? <div className="mt-3 grid gap-3 md:grid-cols-3"><label className="text-xs font-semibold text-slate-600">Title<input className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm" value={item.title} onChange={(event) => patchItem(item.id, { title: event.target.value })} /></label><label className="text-xs font-semibold text-slate-600">Instructions<input className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm" value={item.instructions} onChange={(event) => patchItem(item.id, { instructions: event.target.value })} /></label><label className="text-xs font-semibold text-slate-600">Frequency<input className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm" value={item.frequency} onChange={(event) => patchItem(item.id, { frequency: event.target.value, ...(item.category === "medication" ? { medication: { ...item.medication, frequency: event.target.value } } : {}) })} /></label></div> : <p className="mt-3 text-sm text-slate-700">{item.instructions} · {item.frequency}</p>}
            {plan.status === "draft" && item.category === "medication" && !item.is_removed ? <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
                <p className="font-semibold">Medication reconciliation</p>
                <p className="mt-1 text-xs">Compare with active records. Creating a new record is blocked if this exact medication name is already active.</p>
                <ul className="mt-2 list-disc pl-5 text-xs">{activeMedications.length ? activeMedications.map((medication) => <li key={medication.id}>{medication.name} · {medication.dosage} · {medication.frequency} · {medication.route}</li>) : <li>No active medications found.</li>}</ul>
                <div className="mt-3 grid gap-3 md:grid-cols-3">{["name", "dosage", "route"].map((field) => <label key={field} className="text-xs font-semibold">Medication {field}<input className="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5 text-sm" value={medicationText(item.medication[field])} onChange={(event) => patchItem(item.id, { medication: { ...item.medication, [field]: event.target.value } })} /></label>)}</div>
                <label className="mt-3 block text-xs font-semibold">Publication decision<select className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm" value={medicationText(item.medication.decision) === "update" ? `update:${medicationText(item.medication.target_id)}` : medicationText(item.medication.decision)} onChange={(event) => { const [decision, targetId] = event.target.value.split(":"); patchItem(item.id, { medication: { ...item.medication, decision: decision || undefined, target_id: targetId || undefined } }); }}><option value="">Choose a decision</option><option value="create">Create a new medication record</option>{activeMedications.filter((medication) => medication.name.trim().toLocaleLowerCase() === medicationText(item.medication.name).trim().toLocaleLowerCase()).map((medication) => <option key={medication.id} value={`update:${medication.id}`}>Update {medication.name} · {medication.dosage} · {medication.frequency}</option>)}</select></label>
                <div className="mt-3 grid gap-2 sm:grid-cols-3"><label className="text-xs font-semibold">Medication name<input className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm" value={medicationText(item.medication.name)} onChange={(event) => patchItem(item.id, { medication: { ...item.medication, name: event.target.value, decision: undefined, target_id: undefined } })} /></label><label className="text-xs font-semibold">Dose<input className="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm" value={medicationText(item.medication.dosage)} onChange={(event) => patchItem(item.id, { medication: { ...item.medication, dosage: event.target.value } })} /></label><label className="text-xs font-semibold">Route<select className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm" value={medicationText(item.medication.route)} onChange={(event) => patchItem(item.id, { medication: { ...item.medication, route: event.target.value } })}><option value="">Choose route</option>{["oral", "topical", "inhaled", "iv", "im", "subcutaneous"].map((route) => <option key={route} value={route}>{route}</option>)}</select></label></div>
            </div> : null}
            {plan.status === "draft" && !item.is_removed ? <label className="mt-3 flex items-start gap-2 text-xs text-slate-700"><input checked={item.language_verified} className="mt-0.5" type="checkbox" onChange={(event) => patchItem(item.id, { language_verified: event.target.checked })} /><span>I checked this final title, instructions, frequency, and medication wording for the patient&apos;s {patientLocale} language against the source. This does not translate the document.</span></label> : null}
            {item.blocker_reason && !item.is_removed ? <div className="mt-3 flex flex-wrap items-center gap-3"><p className="text-sm text-amber-800">{item.blocker_reason}</p>{plan.status === "draft" ? <label className="flex items-center gap-2 text-sm text-slate-700"><input checked={item.clinician_confirmed} type="checkbox" onChange={(event) => patchItem(item.id, { clinician_confirmed: event.target.checked })} /> Confirm after review</label> : null}</div> : null}
            {plan.status === "draft" ? <label className="mt-3 flex items-center gap-2 text-sm text-slate-600"><input checked={item.is_removed} type="checkbox" onChange={(event) => patchItem(item.id, { is_removed: event.target.checked })} /> Remove from this version</label> : null}
        </article>)}</div>
        <aside className="min-h-80 rounded-xl border border-slate-200 bg-slate-50 p-3">
            <p className="mb-3 text-sm font-semibold text-slate-900">Protected source preview</p>
            {!selectedSourceItem ? <p className="text-sm text-slate-600">Select an item with document evidence to inspect its authorized source beside the draft.</p> : null}
            {selectedSourceItem && !selectedSourceDocumentId ? <p className="text-sm text-slate-600">This is a clinician-authored entry. Its recorded instruction is shown in the source excerpt; no document preview is available.</p> : null}
            {sourceLoading ? <p className="text-sm text-slate-600">Loading source preview…</p> : null}
            {sourceError ? <div role="alert" className="rounded-lg bg-rose-50 p-3 text-sm text-rose-700"><p>{sourceError}</p><button onClick={() => setSourceRetry((current) => current + 1)} type="button">Retry source preview</button></div> : null}
            {source ? <DocumentSourceViewer fileName={source.file_name} initialPage={selectedSourceItem ? distinctDocuments(selectedSourceItem).find((citation) => citation.document_id === selectedSourceDocumentId)?.location?.page ?? 1 : 1} previewMimeType={source.preview_mime_type} previewStatus={source.preview_status} previewUrl={source.preview_url} sourceMimeType={source.mime_type} sourceUrl={source.file_url} /> : null}
        </aside>
        </div>
        {plan.status === "draft" ? <div className="rounded-xl border border-slate-200 bg-slate-50 p-4"><h3 className="font-semibold text-slate-900">Proposed publication summary</h3><p className="mt-1 text-sm text-slate-600">These items would be projected to Today after approval. This is not an exact Today preview; patient timezone and reminder settings affect the final display.</p><ul className="mt-2 list-disc pl-5 text-sm text-slate-700">{items.filter((item) => !item.is_removed).map((item) => <li key={item.id}>{item.title} — {item.instructions} · {item.frequency}{item.category === "medication" ? ` · ${medicationText(item.medication.decision) || "no medication decision"}` : ""}</li>)}</ul><label className="mt-3 block text-sm font-medium text-slate-700">Approval note<textarea className="mt-1 min-h-20 w-full rounded-lg border border-slate-300 p-2" placeholder="Record the basis for your approval." value={note} onChange={(event) => setNote(event.target.value)} /></label><div className="mt-3 flex gap-3"><button className="rounded-lg border border-blue-200 px-3 py-2 text-sm font-semibold text-blue-700 disabled:opacity-60" disabled={saving} onClick={() => void save()} type="button">{saving ? "Saving…" : "Save review"}</button><button className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-60" disabled={saving || generationBlocked || hasUnsavedChanges || unresolved.length > 0 || unverified.length > 0 || undecidedMedications.length > 0 || !note.trim()} onClick={() => void approve()} type="button">Approve and publish plan</button></div></div> : null}
    </section>;
}
