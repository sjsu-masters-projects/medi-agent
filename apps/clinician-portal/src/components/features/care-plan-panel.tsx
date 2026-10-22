"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { carePlanChanges, carePlanOverlaps } from "@/components/features/care-plan-changes";
import { DocumentSourceViewer } from "@/components/features/document-source-viewer";
import { CarePlanTodayPreviewPanel } from "@/components/features/care-plan-today-preview";
import { AiChip } from "@/components/ui/ai-chip";
import { ApprovalSeal } from "@/components/ui/approval-seal";
import { Icon } from "@/components/ui/icons";
import { Popover } from "@/components/ui/popover";
import { SourceFileIcon, sourceDocumentLabel } from "@/components/features/source-file";
import { formatClinicianDateTime } from "@/utils/dates";
import { InteractionCoverageNote, ItemCrossPlanSection, PublishWithoutDialog, otherPlanLabel, unresolvedBlockers, useCrossPlanReview, type ResolveOutcome } from "@/components/features/cross-plan-conflicts";
import { ApiClientError } from "@/services/api";
import { crossPlanConflictsFrom, errorCode, newIdempotencyKey, resolveConflict } from "@/services/care-team-plans";
import type { CarePlanScope, CrossPlanConflict, CrossPlanResolutionRequest } from "@/types";
import { ApprovedWording, BilingualWording, LOCALE_LABEL, otherLocale, verificationBlocker, wordingComplete, type BackCheck } from "@/components/features/care-plan-wording";
import {
    approveClinicianCarePlan,
    fetchClinicianCarePlanReviewContext,
    fetchClinicianCarePlanGeneration,
    fetchClinicianDocumentSource,
    retryClinicianCarePlanGeneration,
    translateClinicianCarePlanItem,
    updateClinicianCarePlan,
    type CarePlanItem,
    type CarePlanLocale,
    type CarePlanWording,
    type ClinicianDocumentSource,
    type CarePlanGeneration,
    type CarePlanVersion,
    type CarePlanReviewContext,
} from "@/services/clinicians";

interface CarePlanPanelProps {
    patientId: string;
    onPublished?: () => void;
    /** Which of my plans to review when I hold several links to this patient (PLAN-002). */
    scope?: CarePlanScope;
}

type EditableItem = CarePlanItem & { clinician_confirmed: boolean };
type ActiveMedication = CarePlanReviewContext["active_medications"][number];
const SOURCE_TITLE_REVIEW = "Source title exceeds the draft limit; replace it after reviewing the full evidence.";

/** Always show English titles in the clinician portal, falling back to the source title. */
function englishTitle(item: CarePlanItem | EditableItem): string {
    return item.wording?.["en-US"]?.title?.trim() || item.title;
}

/**
 * True when the English title shown to the clinician is a translation of a Spanish source.
 * DV-004: keyed on the SOURCE EVIDENCE language (the fact/document), not the item's authored
 * wording — an English order that produced Spanish-authored wording is not "translated from Spanish".
 */
function isTranslatedFromSpanish(item: CarePlanItem | EditableItem): boolean {
    return item.source_evidence_locale === "es-MX" && Boolean(item.wording?.["en-US"]?.title?.trim());
}
const MEDICATION_ROUTES = ["oral", "topical", "inhaled", "iv", "im", "subcutaneous"];

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
        )) || (item.category === "medication" && !MEDICATION_ROUTES.includes(medicationText(item.medication.route)));
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
export function CarePlanPanel({ patientId, onPublished, scope }: CarePlanPanelProps) {
    const [plan, setPlan] = useState<CarePlanVersion | null>(null);
    const [activePlan, setActivePlan] = useState<CarePlanVersion | null>(null);
    const [patientLocale, setPatientLocale] = useState("en-US");
    const [activeMedications, setActiveMedications] = useState<ActiveMedication[]>([]);
    const [generation, setGeneration] = useState<CarePlanGeneration | null>(null);
    const [items, setItems] = useState<EditableItem[]>([]);
    const focusedReviewTarget = useRef("");
    const [backChecks, setBackChecks] = useState<Record<string, BackCheck>>({});
    const recordBackCheck = useCallback((itemId: string, check: BackCheck) => {
        setBackChecks((current) => {
            const before = current[itemId];
            return before && before.state === check.state && before.guardsOk === check.guardsOk && before.key === check.key ? current : { ...current, [itemId]: check };
        });
    }, []);
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
    const [showRemoved, setShowRemoved] = useState(false);
    const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
    const [reviewTarget, setReviewTarget] = useState("");
    const [justApproved, setJustApproved] = useState(false);
    const cross = useCrossPlanReview(patientId, plan?.status === "draft" ? plan.id : null, true);
    const [publishMessage, setPublishMessage] = useState<string | null>(null);
    const [publishNotice, setPublishNotice] = useState<string | null>(null);
    const [confirmingWithout, setConfirmingWithout] = useState(false);
    const [ackedByItem, setAckedByItem] = useState<Record<string, string[]>>({});
    // One idempotency key per publish attempt; a retry of the same request reuses it.
    const publishAttempt = useRef<{ signature: string; key: string } | null>(null);
    const careTeamId = scope?.careTeamId;
    const carePlanId = scope?.carePlanId;

    useEffect(() => {
        const syncTarget = () => setReviewTarget(window.location.hash.slice(1));
        syncTarget();
        window.addEventListener("hashchange", syncTarget);
        return () => window.removeEventListener("hashchange", syncTarget);
    }, [patientId]);

    useEffect(() => {
        if (!reviewTarget.startsWith("care-plan-item-")) return;
        const itemId = reviewTarget.slice("care-plan-item-".length);
        const targetItem = items.find((item) => item.id === itemId);
        if (!targetItem) return;
        if (targetItem.is_removed) setShowRemoved(true);
        setSelectedItemId(itemId);
    }, [items, reviewTarget]);

    useEffect(() => {
        if (focusedReviewTarget.current === reviewTarget || !reviewTarget.startsWith("care-plan-item-")) return;
        const itemId = reviewTarget.slice("care-plan-item-".length);
        if (selectedItemId !== itemId) return;
        const frame = requestAnimationFrame(() => {
            const target = document.getElementById(reviewTarget);
            if (!target) return;
            focusedReviewTarget.current = reviewTarget;
            target.tabIndex = -1;
            target.scrollIntoView?.({ block: "center" });
            target.focus({ preventScroll: true });
        });
        return () => cancelAnimationFrame(frame);
    }, [items, reviewTarget, selectedItemId, showRemoved]);

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const planScope = careTeamId || carePlanId ? { careTeamId, carePlanId } : undefined;
            const [context, nextGeneration] = await Promise.all([
                planScope ? fetchClinicianCarePlanReviewContext(patientId, planScope) : fetchClinicianCarePlanReviewContext(patientId),
                planScope ? fetchClinicianCarePlanGeneration(patientId, planScope) : fetchClinicianCarePlanGeneration(patientId),
            ]);
            const next = context.latest;
            setPlan(next);
            setActivePlan(context.active ?? (next?.status === "approved" ? next : null));
            setPatientLocale(context.patient_locale);
            setActiveMedications(context.active_medications ?? []);
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
    }, [patientId, careTeamId, carePlanId]);

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
        () => items.filter((item) => !item.is_removed && (missingRequiredEvidence(item) ||
            (item.uncertainty.includes(SOURCE_TITLE_REVIEW) && item.title.trim() === plan?.items.find((original) => original.id === item.id)?.title.trim()) ||
            Boolean(item.blocker_reason) && !item.clinician_confirmed)),
        [items, plan],
    );
    // Both languages are approved together, so a later language switch needs no new review.
    const untranslated = items.filter((item) => !item.is_removed && !wordingComplete(item));
    const unverified = items.filter((item) => !item.is_removed && !(item.wording_verified && wordingComplete(item)));
    const undecidedMedications = items.filter((item) => !item.is_removed && item.category === "medication" && (
        !["create", "update"].includes(medicationText(item.medication.decision)) ||
        (item.medication.decision === "create" && activeMedications.some((active) => active.name.trim().toLowerCase() === medicationText(item.medication.name).trim().toLowerCase()))
    ));
    const generationBlocked = Boolean(generation && generation.status !== "completed");
    const changes = useMemo(() => carePlanChanges(items, activePlan), [items, activePlan]);
    const overlapping = useMemo(() => carePlanOverlaps(items), [items]);
    const previousByFact = useMemo(
        () => new Map((activePlan?.items ?? []).filter((item) => item.source_fact_id).map((item) => [item.source_fact_id, item])),
        [activePlan],
    );
    const importedItems = items.filter((item) => item.imported_evidence && !item.is_removed && !previousByFact.has(item.source_fact_id));
    const removedCount = items.filter((item) => item.is_removed).length;
    const languageLabel = patientLocale === "es-MX" || patientLocale === "en-US" ? LOCALE_LABEL[patientLocale] : "Language not available";
    const sourceDocuments = useMemo(() => {
        const byId = new Map<string, ReturnType<typeof distinctSources>[number]>();
        for (const item of items) {
            for (const source of distinctSources(item)) {
                if (source.document_id) byId.set(source.document_id, source);
            }
        }
        return [...byId.entries()];
    }, [items]);

    function patchItem(id: string, change: Partial<EditableItem>) {
        setItems((current) => current.map((item) => item.id === id ? {
            ...item, ...change,
            // Any wording or medication change needs a fresh check of both languages.
            wording_verified: change.wording_verified ?? (change.is_removed === true ? false : Boolean(item.wording_verified) && change.title === undefined && change.instructions === undefined && change.frequency === undefined && change.medication === undefined && change.wording === undefined),
        } : item));
        setHasUnsavedChanges(true);
    }

    function editWording(item: EditableItem, locale: CarePlanLocale, field: keyof CarePlanWording, value: string) {
        const source = item.source_locale ?? null;
        const isSource = !source || locale === source;
        const change: Partial<EditableItem> = {};
        if (isSource) {
            // The source copy is also the text reconciliation and continuity compare.
            change[field] = value;
            if (field === "frequency" && item.category === "medication") change.medication = { ...item.medication, frequency: value };
        }
        if (source) {
            const current = item.wording?.[locale] ?? { title: "", instructions: "", frequency: "" };
            change.wording = { ...item.wording, [locale]: { ...current, [field]: value } };
        }
        patchItem(item.id, change);
    }

    function writeManually(item: EditableItem, sourceLocale: CarePlanLocale) {
        patchItem(item.id, {
            source_locale: sourceLocale,
            wording: {
                [sourceLocale]: { title: item.title, instructions: item.instructions, frequency: item.frequency },
                [otherLocale(sourceLocale)]: { title: "", instructions: "", frequency: "" },
            },
        });
    }

    function removeItems(ids: string[]) {
        setItems((current) => current.map((item) => ids.includes(item.id)
            ? { ...item, is_removed: true, wording_verified: false } : item));
        setHasUnsavedChanges(true);
    }

    async function translate(item: EditableItem, fromLocale: CarePlanLocale) {
        if (!plan || plan.status !== "draft" || hasUnsavedChanges) return;
        setSaving(true); setError(null);
        try {
            const saved = await translateClinicianCarePlanItem(patientId, plan.id, item.id, fromLocale);
            setPlan(saved);
            setItems(saved.items.map((next) => ({ ...next, clinician_confirmed: false })));
        } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to draft the translation."); }
        finally { setSaving(false); }
    }

    async function save() {
        if (!plan || plan.status !== "draft") return;
        setSaving(true); setError(null);
        try {
            const saved = await updateClinicianCarePlan(patientId, plan.id, items.map((item) => ({
                id: item.id, title: item.title, instructions: item.instructions,
                frequency: item.frequency, schedule: item.schedule, medication: item.medication,
                is_removed: item.is_removed, clinician_confirmed: item.clinician_confirmed,
                wording: item.wording ?? {}, wording_verified: Boolean(item.wording_verified),
                source_locale: item.source_locale ?? null,
            })));
            setPlan(saved);
            setItems(saved.items.map((item) => ({ ...item, clinician_confirmed: false })));
            setHasUnsavedChanges(false);
            void cross.refresh();
        } catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to save the draft."); }
        finally { setSaving(false); }
    }

    async function publish(excludedItemIds: string[] = []) {
        if (!plan || generationBlocked || overlapping.size || unresolved.length || unverified.length || undecidedMedications.length || !note.trim() || hasUnsavedChanges) return;
        const signature = JSON.stringify([plan.id, note, [...excludedItemIds].sort()]);
        if (publishAttempt.current?.signature !== signature) publishAttempt.current = { signature, key: newIdempotencyKey() };
        setSaving(true); setError(null); setPublishMessage(null); setPublishNotice(null);
        try {
            const result = await approveClinicianCarePlan(patientId, plan.id, note, { idempotencyKey: publishAttempt.current.key, excludedItemIds });
            publishAttempt.current = null;
            setConfirmingWithout(false);
            setJustApproved(true);
            const held = result.excluded_item_ids?.length ?? 0;
            const warned = result.warnings?.length ?? 0;
            setPublishNotice([
                held ? `Published without ${held} item${held === 1 ? "" : "s"}. ${held === 1 ? "It stays" : "They stay"} in your next draft as pending.` : null,
                warned ? `${warned} non-blocking overlap${warned === 1 ? "" : "s"} with other care teams ${warned === 1 ? "was" : "were"} noted.` : null,
                result.replayed ? "This publish had already been recorded; nothing was published twice." : null,
            ].filter(Boolean).join(" ") || null);
            await load(); onPublished?.();
        } catch (cause) {
            const conflicts = crossPlanConflictsFrom(cause);
            if (conflicts) {
                publishAttempt.current = null;
                setConfirmingWithout(false);
                setPublishMessage(`Nothing was published. ${conflicts.length === 1 ? "A conflict with another care team's plan needs" : `${conflicts.length} conflicts with other care teams' plans need`} your attention; the list below is refreshed.`);
                void cross.refresh();
            } else if (errorCode(cause) === "IDEMPOTENCY_KEY_REUSED") {
                publishAttempt.current = null;
                setPublishMessage("Nothing was published. This publish attempt was already used for different content. Review the plan and publish again.");
            } else {
                // A definite refusal ends the attempt; an unknown outcome keeps the key so a retry cannot publish twice.
                if (cause instanceof ApiClientError && cause.status >= 400 && cause.status < 500) publishAttempt.current = null;
                const message = cause instanceof Error ? cause.message : "Unable to approve this care plan.";
                if (confirmingWithout) setPublishMessage(message); else setError(message);
            }
        }
        finally { setSaving(false); }
    }
    const approve = () => publish([]);

    function focusItemEditor(itemId: string) {
        const field = document.getElementById(`care-plan-item-${itemId}`)?.closest("article")?.querySelector<HTMLElement>("textarea, input[type='text'], input:not([type])");
        field?.scrollIntoView?.({ block: "center" });
        field?.focus();
    }

    async function resolveCrossConflict(conflict: CrossPlanConflict, body: CrossPlanResolutionRequest): Promise<ResolveOutcome> {
        if (!plan) return { ok: false, message: "The draft is not available." };
        try {
            await resolveConflict(patientId, plan.id, conflict.fingerprint, body);
            if (body.resolution === "keep_both") {
                setAckedByItem((current) => ({ ...current, [conflict.draft_item_id]: [...(current[conflict.draft_item_id] ?? []), conflict.fingerprint] }));
            }
            await cross.refresh();
            return { ok: true };
        } catch (cause) {
            if (errorCode(cause) === "CONFLICT_CHANGED" || (cause instanceof ApiClientError && cause.status === 409)) {
                await cross.refresh();
                return { ok: false, stale: true, message: "This conflict changed since you opened it, so nothing was recorded. The comparison is refreshed; choose again." };
            }
            return { ok: false, message: cause instanceof Error ? cause.message : "Unable to record your decision." };
        }
    }

    async function retry() {
        setSaving(true); setError(null);
        try { await (careTeamId || carePlanId ? retryClinicianCarePlanGeneration(patientId, { careTeamId, carePlanId }) : retryClinicianCarePlanGeneration(patientId)); await load(); }
        catch (cause) { setError(cause instanceof Error ? cause.message : "Unable to retry draft generation."); }
        finally { setSaving(false); }
    }

    const visibleItems = items.filter((item) => showRemoved || !item.is_removed);
    const selectedItem = visibleItems.find((item) => item.id === selectedItemId) ?? visibleItems[0] ?? null;
    const unresolvedIds = new Set(unresolved.map((item) => item.id));
    const undecidedIds = new Set(undecidedMedications.map((item) => item.id));
    const pendingUploadReview = (item: CarePlanItem) => (item.sources ?? (item.source ? [item.source] : [])).some((citation) => citation.upload_review_status && citation.upload_review_status !== "approved");
    const retained = items.filter((item) => !item.is_removed);
    const verifiedCount = retained.filter((item) => item.wording_verified && wordingComplete(item)).length;
    const crossBlockers = unresolvedBlockers(cross.state.review);
    const crossBlockedIds = new Set(crossBlockers.map((conflict) => conflict.draft_item_id).filter((id) => items.some((item) => item.id === id && !item.is_removed)));
    const blockerCount = unresolved.length + overlapping.size + undecidedMedications.length + crossBlockedIds.size;
    const pendingUploads = retained.some(pendingUploadReview);
    const reviewReady = !saving && !generationBlocked && !hasUnsavedChanges && blockerCount === 0 && unverified.length === 0;
    const canApproveIgnoringConflicts = !(saving || generationBlocked || overlapping.size > 0 || hasUnsavedChanges || unresolved.length > 0 || unverified.length > 0 || undecidedMedications.length > 0 || !note.trim());
    const canApprove = canApproveIgnoringConflicts && crossBlockedIds.size === 0;
    const withoutItems = items.filter((item) => crossBlockedIds.has(item.id)).map((item) => ({
        id: item.id, title: englishTitle(item),
        reason: `Conflicts with ${otherPlanLabel(crossBlockers.find((conflict) => conflict.draft_item_id === item.id)?.other_plan ?? null)}`,
    }));
    function itemState(item: EditableItem): "verified" | "blocker" | "unverified" | "removed" {
        if (item.is_removed) return "removed";
        if (unresolvedIds.has(item.id) || overlapping.has(item.id) || undecidedIds.has(item.id) || crossBlockedIds.has(item.id) || pendingUploadReview(item)) return "blocker";
        return item.wording_verified && wordingComplete(item) ? "verified" : "unverified";
    }
    const positionOf = (id: string) => visibleItems.findIndex((item) => item.id === id) + 1;
    const capitalize = (value: string) => value ? value.charAt(0).toUpperCase() + value.slice(1) : value;
    function itemSub(item: EditableItem) {
        const parts = [capitalize(item.category)];
        if (plan?.status === "draft" && overlapping.has(item.id)) parts.push(`Overlaps item ${(overlapping.get(item.id) ?? []).map(positionOf).filter(Boolean).join(", ")}`);
        else if (activePlan && plan?.status === "draft" && changes.get(item.id)) parts.push(capitalize(changes.get(item.id) ?? ""));
        else if (distinctDocuments(item).length) parts.push(`${distinctDocuments(item).length} source${distinctDocuments(item).length === 1 ? "" : "s"}`);
        return parts.join(" · ");
    }
    const selectedCitation = selectedSourceItem && selectedSourceDocumentId
        ? distinctSources(selectedSourceItem).find((citation) => citation.document_id === selectedSourceDocumentId)
        : null;
    const steps: { label: string; state: "done" | "current" | "blocked" | "todo" }[] = [
        { label: "Sources", state: pendingUploads ? "blocked" : "done" },
        { label: `Wording EN · ES ${verifiedCount}/${retained.length}`, state: unverified.length === 0 ? "done" : pendingUploads ? "todo" : "current" },
        { label: `Resolve blockers ${Math.max(0, retained.length - new Set([...unresolvedIds, ...overlapping.keys(), ...undecidedIds, ...crossBlockedIds]).size)}/${retained.length}`, state: blockerCount === 0 && !generationBlocked ? "done" : "blocked" },
        { label: "Preview Today", state: reviewReady ? "current" : "todo" },
        { label: "Approve", state: reviewReady && note.trim() ? "current" : "todo" },
    ];

    if (loading) return <div role="status" aria-label="Loading care plan…" className="grid gap-4 rounded-2xl border border-line bg-surface p-5 xl:grid-cols-[300px_minmax(0,1fr)_400px]"><span className="sr-only">Loading care plan…</span>{[0, 1, 2].map((key) => <div key={key} className="space-y-3"><div className="ma-skeleton h-5 w-40 rounded" /><div className="ma-skeleton h-24 rounded-xl" /><div className="ma-skeleton h-24 rounded-xl" /></div>)}</div>;
    if (!plan && error) return <div className="rounded-2xl border border-risk-line bg-risk-soft p-5 text-sm text-risk-ink" role="alert"><p className="font-semibold">Care plan could not be loaded</p><p className="mt-1">{error}</p><button className="ma-press mt-3 h-[34px] rounded-[9px] border border-risk-line bg-surface px-3 font-semibold hover:bg-risk-tint" onClick={() => void load()} type="button">Try again</button></div>;
    if (!plan) return <div className="flex flex-col items-center gap-3 rounded-2xl border border-line bg-surface px-6 py-12 text-center text-sm text-ink-2">
        <span className={`flex h-12 w-12 items-center justify-center rounded-2xl ${generation?.status === "failed" ? "bg-risk-tint text-risk-ink" : "bg-ai-tint text-ai-ink"}`}>{generation?.status === "failed" ? <Icon name="alert" className="h-6 w-6" /> : <Icon name="spark" className="h-6 w-6" />}</span>
        <p className="text-[15px] font-semibold text-ink">{generation?.status === "failed" ? "Automatic evidence draft failed" : "Waiting for an automatic evidence draft"}</p>
        <p className="max-w-[60ch] leading-relaxed">{generation?.status === "failed" ? "The previous approved plan, if any, remains active. Retry uses the same grounded evidence and never publishes a plan automatically." : "A draft is created after newly processed evidence has been quiet for five minutes. Nothing is visible to the patient until approval."}</p>
        {generation?.status === "failed" ? <button className="ma-press h-[34px] rounded-[9px] border border-line-strong bg-surface px-4 text-[13px] font-semibold text-ink-2 hover:bg-surface-2 disabled:opacity-60" disabled={saving} onClick={() => void retry()} type="button">Retry generation</button> : null}
    </div>;

    const isDraft = plan.status === "draft";
    const statusBox = (state: ReturnType<typeof itemState>) => <span aria-hidden="true" className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md transition-colors duration-[160ms] ${state === "verified" ? "bg-ok text-white" : state === "blocker" ? "border-[1.5px] border-warn text-warn" : state === "removed" ? "border-[1.5px] border-dashed border-[#CBD5E1] text-muted" : "border-[1.5px] border-[#CBD5E1]"}`}>
        {state === "verified" ? <Icon name="check" className="h-3 w-3" strokeWidth={2.6} draw /> : state === "blocker" ? <Icon name="alert" className="h-3 w-3" strokeWidth={2.2} /> : null}
    </span>;
    const fieldClass = "mt-1 w-full rounded-[10px] border border-line-strong bg-surface px-3 py-2 text-sm font-normal text-ink outline-none transition focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)]";

    function renderEditor(item: EditableItem) {
        const overlapPeers = isDraft ? items.filter((other) => overlapping.get(item.id)?.includes(other.id)) : [];
        const citations = distinctSources(item);
        return <article className="space-y-5" key={item.id} aria-labelledby={`care-plan-item-${item.id}`}>
            <header className="space-y-1.5">
                <div className="flex flex-wrap items-center gap-2">
                    <p className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">{item.category}{activePlan && isDraft ? ` · ${changes.get(item.id)}` : ""}</p>
                    {isDraft && overlapping.has(item.id) ? <span className="rounded-md bg-warn-tint px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-warn-ink">Overlap</span> : null}
                    {item.is_removed ? <span className="rounded-md bg-sunken px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.06em] text-muted">Removed</span> : null}
                </div>
                <h3 id={`care-plan-item-${item.id}`} className="break-words text-xl font-semibold leading-snug tracking-[-0.01em] text-ink">{englishTitle(item)}</h3>
                {isTranslatedFromSpanish(item) ? <p className="flex items-center gap-1.5 text-xs text-ai-ink"><Icon name="spark" className="h-3 w-3" />English translated from Spanish source</p> : null}
                {isDraft && overlapping.has(item.id) ? <p className="text-sm text-warn-ink">Overlapping proposals — review before choosing. Compare their sources and keep one reviewed proposal per activity or medication.</p> : null}
            </header>

            {isDraft && !item.is_removed ? <ItemCrossPlanSection acknowledged={new Set(ackedByItem[item.id] ?? [])} busy={saving} itemId={item.id} onChangeItem={() => focusItemEditor(item.id)}
                onRemoveItem={() => patchItem(item.id, { is_removed: true })} onResolve={resolveCrossConflict} onRetry={() => void cross.refresh()} review={cross.state.review} status={cross.state.status} unsaved={hasUnsavedChanges} /> : null}

            {changes.get(item.id) === "edited" && previousByFact.get(item.source_fact_id) ? <div className="rounded-xl border border-line bg-surface-2 p-3 text-xs text-ink-2"><p className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">Approved version {activePlan?.version_number} wording</p><p className="mt-1 text-sm">{previousByFact.get(item.source_fact_id)?.title} — {previousByFact.get(item.source_fact_id)?.instructions} · {previousByFact.get(item.source_fact_id)?.frequency}</p></div> : null}

            {overlapPeers.length ? <div className="space-y-3">
                <div className="grid gap-3 lg:grid-cols-2">
                    {[item, ...overlapPeers].map((candidate) => {
                        const sourceOpen = selectedSourceItemId === candidate.id && Boolean(selectedSourceDocumentId);
                        return <div key={candidate.id} className={`flex flex-col gap-2 rounded-[14px] p-3.5 transition-colors duration-[160ms] ${sourceOpen ? "border-[1.5px] border-primary bg-primary-tint" : "border border-line-strong bg-surface"}`}>
                            <p className={`font-mono text-[11px] uppercase tracking-[0.06em] ${sourceOpen ? "text-primary" : "text-muted"}`}>Item {positionOf(candidate.id) || "—"} · {changes.get(candidate.id) ?? candidate.category}</p>
                            <p className="text-[15px] leading-snug text-ink">{candidate.instructions || candidate.title}</p>
                            <p className="text-xs text-muted">{candidate.frequency}</p>
                            {candidate.source?.file_name ? <p className="flex min-w-0 items-start gap-1.5 text-xs text-muted"><SourceFileIcon className="mt-px" name={candidate.source.file_name} /><span className="min-w-0 break-all">{sourceDocumentLabel(candidate.source)}{candidate.source.location?.page ? ` · p.${candidate.source.location.page}` : ""}</span></p> : null}
                            {isDraft && overlapping.has(candidate.id) ? <button className="ma-press mt-1 self-start rounded-[9px] border border-line-strong bg-surface px-3 py-1.5 text-[13px] font-medium text-ink-2 hover:bg-surface-2 hover:text-ink disabled:opacity-50" disabled={saving} onClick={() => removeItems(overlapping.get(candidate.id) ?? [])} type="button">Keep this proposal; remove its overlaps</button> : null}
                        </div>;
                    })}
                </div>
                <p className="text-xs text-muted">This stages removals only. Save review to persist; no medication or approved instruction changes until publication.</p>
            </div> : null}

            {(item.sources ?? (item.source ? [item.source] : [])).filter((citation) => citation.upload_review_status && citation.upload_review_status !== "approved").map((citation, index) => <p className="flex items-start gap-2 rounded-xl border border-warn-line bg-warn-soft px-3 py-2.5 text-sm text-warn-ink" key={`${citation.document_id}-${index}`}><Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />Patient upload review: {citation.upload_review_status}. Review and approve this source document before previewing or publishing a new plan.</p>)}

            {isDraft ? <div className="space-y-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <p className="text-[13px] font-medium text-ink-2">Patient-facing wording · English and Spanish</p>
                    <p className="text-xs text-muted">Today shows the patient&apos;s chosen language exactly as written</p>
                </div>
                <BilingualWording busy={saving} fieldClass={fieldClass} item={item} patientLocale={patientLocale} unsaved={hasUnsavedChanges} patientId={patientId} planId={plan?.id} onBackCheck={recordBackCheck}
                    onChange={(locale, field, value) => editWording(item, locale, field, value)}
                    onTranslate={(fromLocale) => void translate(item, fromLocale)}
                    onWriteManually={(sourceLocale) => writeManually(item, sourceLocale)} />
            </div> : <ApprovedWording item={item} patientLocale={patientLocale} />}

            {isDraft && item.category === "medication" && !item.is_removed ? <div className="space-y-3 rounded-xl border border-line bg-surface p-3.5 text-sm text-ink-2">
                <div>
                    <p className="font-semibold text-ink">Medication reconciliation</p>
                    <p className="mt-0.5 text-xs text-muted">Compare with active records. Creating a new record is blocked if this exact medication name is already active.</p>
                </div>
                <details className="ma-disclosure"><summary className="min-h-8 py-1 text-[13px] font-medium text-ink-2">Compare active medications ({activeMedications.length})</summary><ul className="mt-2 list-disc space-y-0.5 pl-9 text-xs">{activeMedications.length ? activeMedications.map((medication) => <li key={medication.id}>{medication.name} · {medication.dosage} · {medication.frequency} · {medication.route}</li>) : <li>No active medications found.</li>}</ul></details>
                <label className="block text-xs font-semibold">Publication decision<select className={fieldClass} value={medicationText(item.medication.decision) === "update" ? `update:${medicationText(item.medication.target_id)}` : medicationText(item.medication.decision)} onChange={(event) => { const [decision, targetId] = event.target.value.split(":"); patchItem(item.id, { medication: { ...item.medication, decision: decision || undefined, target_id: targetId || undefined } }); }}><option value="">Choose a decision</option><option value="create">Create a new medication record</option>{activeMedications.filter((medication) => medication.name.trim().toLocaleLowerCase() === medicationText(item.medication.name).trim().toLocaleLowerCase()).map((medication) => <option key={medication.id} value={`update:${medication.id}`}>Update {medication.name} · {medication.dosage} · {medication.frequency}</option>)}</select></label>
                <div className="grid gap-2 sm:grid-cols-3"><label className="text-xs font-semibold">Medication name<input className={fieldClass} value={medicationText(item.medication.name)} onChange={(event) => patchItem(item.id, { medication: { ...item.medication, name: event.target.value, decision: undefined, target_id: undefined } })} /></label><label className="text-xs font-semibold">Dose<input className={fieldClass} value={medicationText(item.medication.dosage)} onChange={(event) => patchItem(item.id, { medication: { ...item.medication, dosage: event.target.value } })} /></label><label className="text-xs font-semibold">Route<select className={fieldClass} value={medicationText(item.medication.route)} onChange={(event) => patchItem(item.id, { medication: { ...item.medication, route: event.target.value } })}><option value="">Choose route</option>{["oral", "topical", "inhaled", "iv", "im", "subcutaneous"].map((route) => <option key={route} value={route}>{route}</option>)}</select></label></div>
            </div> : null}

            {item.blocker_reason && !item.is_removed ? <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warn-line bg-warn-soft px-3.5 py-3"><p className="flex items-start gap-2 text-sm text-warn-ink"><Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />{item.blocker_reason}</p>{isDraft ? <label className="flex items-center gap-2 text-sm font-medium text-ink-2"><input checked={item.clinician_confirmed} className="h-4 w-4 accent-[var(--color-primary)]" type="checkbox" onChange={(event) => patchItem(item.id, { clinician_confirmed: event.target.checked })} /> Confirm after review</label> : null}</div> : null}

            {isDraft && !item.is_removed ? (() => {
                const blocker = verificationBlocker(item, backChecks[item.id], hasUnsavedChanges);
                const checked = Boolean(item.wording_verified) && wordingComplete(item);
                return <label className={`flex items-start gap-3 rounded-xl border p-3.5 text-[13px] leading-relaxed transition-colors duration-[160ms] ${blocker && !checked ? "cursor-not-allowed border-line bg-surface-2 text-muted" : item.wording_verified ? "border-ok-line bg-ok-soft text-ok-ink" : "border-line-strong bg-surface text-ink-2 hover:border-primary-line"}`}><input checked={checked} className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--color-ok)]" disabled={Boolean(blocker) && !checked} type="checkbox" onChange={(event) => patchItem(item.id, { wording_verified: event.target.checked })} /><span>I verified the English wording against the source and confirmed the Spanish through its back-translation and automated safety checks (numbers, doses, medication names).{blocker ? <span className="mt-1 block font-medium" role="status">{blocker}</span> : null}</span></label>;
            })() : null}

            <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-[13px] text-ink-2">
                <span className="font-mono font-medium">{item.confidence_score == null ? "Extraction confidence unavailable" : `${Math.round(item.confidence_score * 100)}% extraction confidence`}</span>
                {distinctDocuments(item).length ? <span className="text-muted">{distinctDocuments(item).length} source document{distinctDocuments(item).length === 1 ? "" : "s"}</span> : null}
            </div>

            <details className="ma-disclosure rounded-xl border border-line bg-surface"><summary className="min-h-10 px-3.5 py-2 text-[13px] font-medium text-ink-2">Source excerpts and confidence ({citations.length})</summary>
                <div className="space-y-2 border-t border-line px-3.5 pb-3.5 pt-2.5">
                    <p className="text-xs text-muted">Extraction confidence is an automated estimate of the extracted information. It is not medical certainty or approval of the instruction.</p>
                    {citations.filter((citation) => Boolean(citation.excerpt)).map((citation, index) => <p className="break-words border-l-2 border-primary-line pl-3 text-xs text-ink-2" key={`${citation.document_id}-${index}`}><span className="flex items-start gap-1.5 font-semibold text-ink">{citation.document_id ? <SourceFileIcon className="mt-px" name={citation.file_name} /> : null}<span className="min-w-0 break-all">{citation.document_id ? sourceDocumentLabel(citation) : citation.file_name || "Clinician-entered evidence"}{citation.location?.page ? ` · page ${citation.location.page}` : ""}</span></span><span className="mt-1 block">“{citation.excerpt}”</span></p>)}
                    {!item.source?.excerpt ? <p className="border-l-2 border-primary-line pl-3 text-xs text-ink-2">{displaySource(item)}</p> : null}
                </div>
            </details>

            <div className="flex flex-wrap items-center gap-2">
                {distinctDocuments(item).map((source, index) => <button aria-label={`Review source: ${sourceDocumentLabel(source)}`} aria-pressed={selectedSourceItemId === item.id && selectedSourceDocumentId === source.document_id} className={`ma-press inline-flex h-[34px] items-center gap-2 rounded-[9px] border px-3 text-[13px] font-semibold transition-colors ${selectedSourceItemId === item.id && selectedSourceDocumentId === source.document_id ? "border-primary bg-primary-tint text-primary" : "border-primary-line bg-surface text-primary hover:bg-primary-tint"}`} key={source.document_id} onClick={() => { setSelectedSourceItemId(item.id); setSelectedSourceDocumentId(source.document_id ?? null); }} type="button"><Icon name="file" className="h-4 w-4" />Review source{distinctDocuments(item).length > 1 ? ` ${index + 1}` : ""}</button>)}
                {isDraft ? <label className="ml-auto flex items-center gap-2 text-[13px] text-muted"><input checked={item.is_removed} className="h-4 w-4 accent-[var(--color-risk)]" type="checkbox" onChange={(event) => patchItem(item.id, { is_removed: event.target.checked })} /> Remove from this version</label> : null}
            </div>
        </article>;
    }

    return <section aria-labelledby="tab-btn-care-plan" id="tab-panel-care-plan" role="tabpanel" className="flex flex-col gap-4">
        <div className="overflow-hidden rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]">
            {/* Header */}
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line px-6 py-4">
                <div className="min-w-0">
                    <h2 className="text-lg font-semibold tracking-[-0.01em] text-ink">Care plan</h2>
                    <p className="text-[13px] text-muted">Version {plan.version_number} · {isDraft ? "AI-generated draft — not visible to patient" : `Status: ${plan.status}`}</p>
                    {isDraft ? <p className="mt-1 text-[13px] text-ink-2">Proposed version {plan.version_number} · Patient reads {languageLabel} · Approved in English and Spanish</p> : null}
                </div>
                <div className="flex flex-col items-end gap-2">
                    <div className="flex flex-wrap items-center justify-end gap-2.5 text-[13px]" aria-live="polite">
                        {activePlan ? <ApprovalSeal pill>v{activePlan.version_number} live in Today</ApprovalSeal> : <span className="rounded-lg bg-sunken px-2.5 py-1.5 text-xs font-medium text-muted">No approved plan yet</span>}
                        {isDraft ? <><Icon name="arrow" className="h-4 w-4 text-[#94A3B8]" /><AiChip>v{plan.version_number} draft · not visible to patient</AiChip></> : null}
                        {justApproved && !isDraft ? <span className="sr-only">Approved and published</span> : null}
                    </div>
                    {generation?.status === "retry" ? <p className="text-xs text-warn-ink">Automatic retry scheduled{generation.next_attempt_at ? ` for ${formatClinicianDateTime(generation.next_attempt_at)}` : ""}.</p> : null}
                </div>
            </div>

            {/* Context and notices */}
            <div className="space-y-3 px-6 py-4 empty:hidden [&:not(:has(*))]:hidden">
                {isDraft ? <div className="flex flex-wrap items-start gap-x-6 gap-y-2 text-[13px] text-ink-2">
                    <p className="min-w-0 max-w-[90ch] flex-1 basis-[420px] leading-relaxed">{activePlan ? `Approved version ${activePlan.version_number} remains active in Today until this version is approved.` : "No approved care plan is active yet."} Check every patient-facing instruction in English and Spanish against its source before publication.</p>
                    <div className="flex flex-wrap gap-x-5 gap-y-1">
                        <details className="ma-disclosure"><summary className="min-h-8 py-1 font-medium text-primary">Documents linked to proposed items ({sourceDocuments.length})</summary>
                            {sourceDocuments.length ? <ul className="mt-1.5 space-y-1 pl-6 text-ink-2">{sourceDocuments.map(([id, source]) => <li className="flex min-w-0 items-start gap-1.5" key={id}><SourceFileIcon className="mt-px" name={source.file_name} /><span className="min-w-0 break-all">{sourceDocumentLabel(source)}</span></li>)}</ul> : <p className="mt-1 pl-6">No source document is linked to these items.</p>}</details>
                        {activePlan ? <details className="ma-disclosure"><summary className="min-h-8 py-1 font-medium text-primary">View currently approved version {activePlan.version_number}</summary><ul className="mt-1 list-disc space-y-0.5 pl-9 text-ink-2">{activePlan.items.filter((item) => !item.is_removed).map((item) => <li key={item.id}>{englishTitle(item)} · {item.frequency}</li>)}</ul></details> : null}
                    </div>
                </div> : null}
                {plan.status === "approved" && generation && generation.status !== "completed" ? <div className="flex items-start gap-3 rounded-xl border border-primary-line bg-primary-tint px-4 py-3 text-sm text-ink-2">
                    <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-ai-tint text-ai-ink"><Icon name="spark" className="h-3.5 w-3.5" /></span>
                    <div className="min-w-0 flex-1">
                        <p className="font-semibold text-ink">{generation.status === "failed" ? "New-evidence draft failed" : generation.status === "processing" ? "Preparing a new-evidence draft" : "New evidence is queued for a draft"}</p>
                        <p className="mt-0.5">Approved version {plan.version_number} remains active. A replacement is never published without clinician review and approval.</p>
                        {generation.status === "pending" ? <p className="mt-0.5">Generation waits for a five-minute evidence quiet window and the next worker run.</p> : null}
                    </div>
                    {generation.status === "failed" ? <button className="ma-press h-[34px] shrink-0 rounded-[9px] border border-line-strong bg-surface px-3 text-[13px] font-semibold text-ink-2 hover:bg-surface-2" disabled={saving} onClick={() => void retry()} type="button">Retry generation</button> : null}
                </div> : null}
                {isDraft && generationBlocked ? <div role="alert" className="flex items-start gap-3 rounded-xl border border-warn-line bg-warn-soft px-4 py-3 text-sm text-warn-ink">
                    <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
                    <div className="min-w-0 flex-1">
                        <p className="font-semibold">{generation?.status === "failed" ? "Draft generation failed — publication blocked" : "Draft generation is incomplete — publication blocked"}</p>
                        <p className="mt-0.5">The displayed draft may contain only part of the evidence. Generation must complete before publication. The previous approved plan, if any, remains active.</p>
                        {generation?.failure_code === "source_fields_incomplete" ? <p className="mt-0.5">Some source facts lack required wording or exceed the draft field limits. Repeating the same request will not repair this evidence; review the source document and ask your clinic administrator for help.</p> : null}
                    </div>
                    {generation?.status === "failed" ? <button className="ma-press h-[34px] shrink-0 rounded-[9px] border border-line-strong bg-surface px-3 text-[13px] font-semibold text-ink-2 hover:bg-surface-2" disabled={saving} onClick={() => void retry()} type="button">Retry generation</button> : null}
                </div> : null}
                {publishNotice ? <p className="flex items-start gap-2 rounded-xl border border-ok-line bg-ok-soft px-4 py-3 text-sm text-ok-ink" role="status"><Icon name="check" className="mt-0.5 h-4 w-4 shrink-0" />{publishNotice}</p> : null}
                {error ? <p className="flex items-start gap-2 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink" role="alert"><Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />{error}</p> : null}
                {isDraft && importedItems.length ? <div className="flex flex-wrap items-center gap-3 rounded-xl border border-primary-line bg-primary-tint px-4 py-3 text-sm text-ink-2">
                    <div className="min-w-0 flex-1 basis-[420px]">
                        <p className="font-semibold text-ink">{importedItems.length} imported-record proposals need separate reconciliation</p>
                        <p className="mt-0.5">An imported record is historical evidence, not a new instruction. Review it in External records. You can exclude these proposals from this draft without deleting their sources or changing the approved plan.</p>
                    </div>
                    <button className="ma-press h-[34px] rounded-[9px] border border-line-strong bg-surface px-3 text-[13px] font-semibold text-ink-2 hover:bg-surface-2" disabled={saving} onClick={() => removeItems(importedItems.map((item) => item.id))} type="button">Exclude imported proposals from this draft</button>
                </div> : null}
            </div>

            {/* Publishing steps (the existing "Before publishing" requirements) */}
            {isDraft ? <section aria-label="Publication requirements" className="border-y border-line bg-surface-2/70 px-6 py-3">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-2">
                    <ol className="flex flex-wrap items-center gap-x-2 gap-y-2" aria-label="Publishing steps">
                        {steps.map((step, index) => <li key={step.label} className="flex items-center gap-2">
                            {index > 0 ? <span aria-hidden="true" className="hidden h-px w-4 bg-line-strong sm:block xl:w-8 2xl:w-10" /> : null}
                            <span aria-hidden="true" className={`flex h-[22px] w-[22px] items-center justify-center rounded-full font-mono text-[11px] transition-colors duration-[160ms] ${step.state === "done" ? "bg-ok text-white" : step.state === "current" ? "border-2 border-primary text-ink" : step.state === "blocked" ? "border-[1.5px] border-warn text-warn-ink" : "border-[1.5px] border-[#CBD5E1] text-muted"}`}>{step.state === "done" ? <Icon name="check" className="h-3 w-3" strokeWidth={2.6} draw /> : index + 1}</span>
                            <span aria-current={step.state === "current" ? "step" : undefined} className={`whitespace-nowrap text-[13px] ${step.state === "current" ? "" : "sr-only xl:not-sr-only"} ${step.state === "current" ? "font-semibold text-ink" : step.state === "done" ? "text-ok-ink" : step.state === "blocked" ? "text-warn-ink" : "text-muted"}`}>{step.label}</span>
                        </li>)}
                    </ol>
                    <Popover align="end" className="ml-auto" label="Before publishing" trigger={(props) => <button {...props} aria-label="Before publishing" className="ma-press flex h-8 w-8 items-center justify-center rounded-lg text-muted hover:bg-sunken hover:text-ink" type="button"><Icon name="info" className="h-4 w-4" /></button>}>
                        <h3 className="font-semibold text-ink">Before publishing</h3>
                        <p className="mt-1">Review sources and patient wording, resolve blockers, save changes, then preview Today and approve the complete plan.</p>
                        <p className="mt-2 text-xs text-muted">“New evidence” means a new source fact, not a verified new therapy. Reconcile overlapping medication instructions before approval.</p>
                    </Popover>
                </div>
                {(hasUnsavedChanges || unresolved.length || unverified.length || untranslated.length || undecidedMedications.length || overlapping.size || crossBlockedIds.size || !note.trim()) ? <ul className="mt-2.5 grid gap-x-6 gap-y-1 text-[13px] leading-snug text-ink-2 lg:grid-cols-2">
                    {hasUnsavedChanges ? <li className="flex items-start gap-2 text-warn-ink"><Icon name="alert" className="mt-0.5 h-3.5 w-3.5 shrink-0" /><span>Save your edits before approving. New evidence may have changed the draft while you reviewed it.</span></li> : null}
                    {unresolved.length ? <li className="flex items-start gap-2 text-warn-ink"><Icon name="alert" className="mt-0.5 h-3.5 w-3.5 shrink-0" /><span>{unresolved.length} unresolved item{unresolved.length === 1 ? "" : "s"} block whole-plan approval. Supply missing instructions or remove incomplete items. Confirm uncertainty only after reviewing the evidence.</span></li> : null}
                    {untranslated.length ? <li className="flex items-start gap-2 text-warn-ink"><Icon name="alert" className="mt-0.5 h-3.5 w-3.5 shrink-0" /><span>{untranslated.length} item{untranslated.length === 1 ? " needs" : "s need"} wording in both English and Spanish. Draft a translation or write it yourself.</span></li> : null}
                    {unverified.length > untranslated.length ? <li className="flex items-start gap-2"><span aria-hidden="true" className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" /><span>Check the English and Spanish wording of {unverified.length - untranslated.length} item{unverified.length - untranslated.length === 1 ? "" : "s"} before approval. AI translations are drafts until you check them.</span></li> : null}
                    {undecidedMedications.length ? <li className="flex items-start gap-2 text-warn-ink"><Icon name="alert" className="mt-0.5 h-3.5 w-3.5 shrink-0" /><span>Choose whether each medication updates a matching active record or creates a new record. Remove an unchanged proposal rather than publishing a duplicate.</span></li> : null}
                    {overlapping.size ? <li className="flex items-start gap-2 text-warn-ink"><Icon name="alert" className="mt-0.5 h-3.5 w-3.5 shrink-0" /><span>{overlapping.size} items overlap. Compare their sources and keep one reviewed proposal per activity or medication before publication. Different wording is not proof of a different therapy.</span></li> : null}
                    {crossBlockedIds.size ? <li className="flex items-start gap-2 text-risk-ink"><Icon name="alert" className="mt-0.5 h-3.5 w-3.5 shrink-0" /><span>{crossBlockedIds.size} conflict{crossBlockedIds.size === 1 ? "" : "s"} to resolve with other care teams&apos; plans. Change or remove the item, keep both with a reason, ask the other care team, or publish without {crossBlockedIds.size === 1 ? "it" : "them"}.</span></li> : null}
                    {!note.trim() ? <li className="flex items-start gap-2"><span aria-hidden="true" className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#94A3B8]" /><span>Add an approval note describing the basis for your decision.</span></li> : null}
                </ul> : null}
                {cross.state.review ? <InteractionCoverageNote className="mt-2.5" /> : null}
            </section> : null}

            {/* Three panes: items | editor | protected source */}
            <div className="grid min-h-[520px] xl:grid-cols-[300px_minmax(0,1fr)_400px]">
                <nav aria-label="Proposed items" className="border-b border-line p-3 xl:max-h-[calc(100dvh-300px)] xl:overflow-y-auto xl:border-b-0 xl:border-r">
                    <p className="px-2 pb-2 pt-1 font-mono text-[11px] uppercase tracking-[0.06em] text-muted">{retained.length} proposed item{retained.length === 1 ? "" : "s"}</p>
                    <ul className="space-y-1">
                        {visibleItems.map((item) => {
                            const state = itemState(item);
                            const selected = selectedItem?.id === item.id;
                            return <li key={item.id}>
                                <button type="button" onClick={() => setSelectedItemId(item.id)} aria-current={selected ? "true" : undefined}
                                    className={`flex w-full items-start gap-2.5 rounded-[10px] border p-2.5 text-left transition-colors duration-[160ms] ${selected ? "border-[rgba(96,165,250,.35)] bg-[rgba(96,165,250,.1)]" : "border-transparent hover:bg-surface-2"} ${item.is_removed ? "opacity-60" : ""}`}>
                                    <span className="mt-0.5">{statusBox(state)}</span>
                                    <span className="flex min-w-0 flex-col">
                                        <span className={`line-clamp-2 break-words text-sm text-ink ${selected ? "font-semibold" : "font-medium"} ${item.is_removed ? "line-through decoration-[#94A3B8]" : ""}`}>{englishTitle(item)}</span>
                                        <span className={`mt-0.5 flex flex-wrap items-center gap-1.5 text-xs ${state === "blocker" ? "text-warn-ink" : "text-muted"}`}>{itemSub(item)}{isTranslatedFromSpanish(item) ? <span className="rounded bg-ai-tint px-1 py-0.5 text-[10px] font-medium text-ai-ink">Translated from Spanish</span> : null}</span>
                                    </span>
                                </button>
                            </li>;
                        })}
                    </ul>
                    {removedCount > 0 ? <label className="mt-3 flex items-center gap-2 border-t border-line px-2 pt-3 text-xs text-muted"><input checked={showRemoved} className="h-3.5 w-3.5 accent-[var(--color-primary)]" type="checkbox" onChange={(event) => setShowRemoved(event.target.checked)} />Show removed items ({removedCount}) — sources retained</label> : null}
                </nav>

                <div className="min-w-0 px-6 py-5 xl:max-h-[calc(100dvh-300px)] xl:overflow-y-auto">
                    {selectedItem ? renderEditor(selectedItem) : <p className="text-sm text-muted">No proposed items in this version.</p>}
                </div>

                <aside data-source-pane className="min-w-0 border-t border-line bg-sunken p-4 xl:max-h-[calc(100dvh-300px)] xl:overflow-y-auto xl:border-l xl:border-t-0">
                    <div className="mb-3 flex items-start justify-between gap-3">
                        <p className="text-sm font-semibold text-ink">Protected source preview</p>
                        <span className="inline-flex shrink-0 items-center gap-1 text-xs text-muted"><Icon name="shield" className="h-3.5 w-3.5" />Protected preview</span>
                    </div>
                    <p className="mb-3 text-xs leading-relaxed text-muted">Inspecting a source does not approve its upload or publish instructions. Patient uploads are reviewed separately in Documents.</p>
                    {!selectedSourceItem ? <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-line-strong bg-surface/60 px-4 py-10 text-center text-sm text-muted"><Icon name="note" className="h-6 w-6" /><p>Select an item with document evidence to inspect its authorized source beside the draft.</p></div> : null}
                    {selectedSourceItem && !selectedSourceDocumentId ? <p className="text-sm text-muted">This is a clinician-authored entry. Its recorded instruction is shown in the source excerpt; no document preview is available.</p> : null}
                    {sourceLoading ? <div className="space-y-2" role="status"><p className="text-sm text-muted">Loading source preview…</p><div className="ma-skeleton h-72 rounded-[10px]" /></div> : null}
                    {source ? <p className="mb-2 flex items-start gap-1.5 break-all text-[13px] font-semibold text-ink"><SourceFileIcon className="mt-0.5" name={source.file_name} /><span>Selected source: {source.file_name}</span></p> : null}
                    {selectedCitation?.excerpt && source ? <p key={`${selectedSourceItemId}:${selectedSourceDocumentId}`} className="ma-flash mb-3 rounded-md bg-[rgba(250,204,21,.32)] px-2 py-1.5 font-serif text-[13px] leading-relaxed text-ink ring-[1.5px] ring-[rgba(202,138,4,.55)]">“{selectedCitation.excerpt}”{selectedCitation.location?.page ? <span className="ml-1 font-sans text-[11px] text-muted">p.{selectedCitation.location.page}</span> : null}</p> : null}
                    {sourceError ? <div role="alert" className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-risk-line bg-risk-soft p-3 text-sm text-risk-ink"><p>{sourceError}</p><button className="ma-press h-8 rounded-lg border border-risk-line bg-surface px-3 text-xs font-semibold" onClick={() => setSourceRetry((current) => current + 1)} type="button">Retry source preview</button></div> : null}
                    {source ? <div className="ma-3d-tilt rounded-[10px] bg-surface p-3 shadow-[var(--shadow-page)]"><DocumentSourceViewer fileName={source.file_name} initialPage={selectedSourceItem ? distinctDocuments(selectedSourceItem).find((citation) => citation.document_id === selectedSourceDocumentId)?.location?.page ?? 1 : 1} previewMimeType={source.preview_mime_type} previewStatus={source.preview_status} previewUrl={source.preview_url} sourceMimeType={source.mime_type} sourceUrl={source.file_url} /></div> : null}
                </aside>
            </div>
        </div>

        {isDraft ? <div className="grid gap-4 xl:grid-cols-2">
            <CarePlanTodayPreviewPanel key={`${plan.id}:${JSON.stringify(items)}:${saving}:${generationBlocked}`} patientId={patientId} planId={plan.id} disabled={saving || generationBlocked || hasUnsavedChanges || overlapping.size > 0 || unresolved.length > 0 || unverified.length > 0 || undecidedMedications.length > 0} />
            <section className="rounded-2xl border border-line bg-surface p-5 shadow-[var(--shadow-card)]">
                <h3 className="font-semibold text-ink">Proposed publication summary</h3>
                <p className="mt-1 text-sm text-muted">Retained plan instructions are listed below. Use Preview Today to include existing activities and patient reminder settings.</p>
                <details className="ma-disclosure mt-2"><summary className="min-h-9 py-1 text-sm font-medium text-ink-2">Review retained instructions ({items.filter((item) => !item.is_removed).length})</summary><ul className="mt-2 list-disc space-y-1 pl-9 text-sm text-ink-2">{items.filter((item) => !item.is_removed).map((item) => <li key={item.id}>{englishTitle(item)}{englishTitle(item).trim().replace(/\s+/g, " ") === (item.wording?.["en-US"]?.instructions?.trim().replace(/\s+/g, " ") || item.instructions.trim().replace(/\s+/g, " ")) ? "" : ` — ${item.wording?.["en-US"]?.instructions?.trim() || item.instructions}`} · {item.wording?.["en-US"]?.frequency?.trim() || item.frequency}{item.category === "medication" ? ` · ${medicationText(item.medication.decision) || "no medication decision"}` : ""}</li>)}</ul></details>
            </section>
        </div> : null}

        {/* Sticky approval bar: same note, same save and approve gating */}
        {isDraft ? <div className="sticky bottom-0 z-20 -mx-4 border-t border-line-strong bg-white/90 px-4 py-3 backdrop-blur-md sm:-mx-7 sm:px-7">
            <div className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-x-3 gap-y-2 xl:grid-cols-[minmax(170px,220px)_minmax(220px,1fr)_auto_auto]">
                <div className="min-w-0 xl:col-start-1 xl:row-start-1">
                    <p className="font-mono text-xs text-ink-2">{verifiedCount} of {retained.length} verified{blockerCount ? ` · ${blockerCount} blocker${blockerCount === 1 ? "" : "s"}` : ""}</p>
                    {crossBlockedIds.size ? <p className="mt-0.5 text-xs font-semibold text-risk-ink" data-testid="conflict-summary">{crossBlockedIds.size} conflict{crossBlockedIds.size === 1 ? "" : "s"} to resolve</p> : null}
                    <p className="mt-0.5 text-xs leading-snug text-muted">{activePlan ? `v${activePlan.version_number} stays live in Today until you approve.` : "Nothing is visible to the patient until approval."}</p>
                </div>
                <label className="col-span-3 row-start-2 min-w-0 xl:col-span-1 xl:col-start-2 xl:row-start-1">
                    <span className="sr-only">Approval note</span>
                    <textarea rows={1} className="block max-h-28 min-h-[42px] w-full resize-y rounded-[10px] border border-line-strong bg-surface-2 px-3.5 py-2.5 text-sm text-ink outline-none transition placeholder:text-[#94A3B8] focus:border-primary focus:bg-surface focus:ring-4 focus:ring-[rgba(37,99,235,.12)]" placeholder="Record the basis for your approval." value={note} onChange={(event) => setNote(event.target.value)} />
                </label>
                <button className="ma-press inline-flex h-[42px] items-center whitespace-nowrap rounded-[10px] border border-line-strong bg-surface px-4 text-sm font-semibold text-ink-2 hover:bg-surface-2 hover:text-ink disabled:opacity-60" disabled={saving} onClick={() => void save()} type="button">{saving ? "Saving…" : "Save review"}</button>
                <button className="ma-press inline-flex h-[42px] items-center gap-2 whitespace-nowrap rounded-[10px] bg-primary px-[18px] text-sm font-semibold text-white shadow-[0_1px_2px_rgba(37,99,235,.3)] hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-track disabled:text-[#94A3B8] disabled:shadow-none" disabled={!canApprove} onClick={() => void approve()} type="button"><Icon name="check" className="h-4 w-4" strokeWidth={2.4} />Approve and publish plan</button>
                {crossBlockedIds.size ? <button className="ma-press col-span-3 inline-flex h-[38px] items-center justify-center gap-2 whitespace-nowrap rounded-[10px] border border-risk-line bg-surface px-4 text-sm font-semibold text-risk-ink hover:bg-risk-soft disabled:cursor-not-allowed disabled:opacity-50 xl:col-span-4 xl:justify-self-end" disabled={!canApproveIgnoringConflicts} onClick={() => { setPublishMessage(null); setConfirmingWithout(true); }} type="button">Publish without these items</button> : null}
            </div>
            <div aria-live="polite">{publishMessage && !confirmingWithout ? <p className="mt-2 rounded-lg border border-risk-line bg-risk-soft px-3 py-2 text-sm text-risk-ink" role="alert">{publishMessage}</p> : null}</div>
        </div> : null}
        <PublishWithoutDialog busy={saving} error={confirmingWithout ? publishMessage : null} items={withoutItems} onClose={() => { setConfirmingWithout(false); setPublishMessage(null); }} onConfirm={() => void publish(withoutItems.map((item) => item.id))} open={confirmingWithout && isDraft} />
    </section>;
}
