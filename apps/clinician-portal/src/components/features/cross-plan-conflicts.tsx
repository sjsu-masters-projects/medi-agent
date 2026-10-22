"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { Modal } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { fetchCrossPlanReview } from "@/services/care-team-plans";
import type { ConflictMedication, CrossPlanConflict, CrossPlanConflictKind, CrossPlanResolutionRequest, CrossPlanReview } from "@/types";
import { formatClinicianDate } from "@/utils/dates";

/**
 * Cross-plan safety review (PLAN-002): conflicts between this draft and the patient's other
 * approved plans. Blockers must be resolved, acknowledged with a reason, or published
 * without; warnings never block. Interaction severity is NOT checked and never implied.
 */

export const REASON_MIN = 10;
export const REASON_MAX = 2000;
export const DEFAULT_QUESTION = "Please review this overlap with your plan and tell me how you would like to handle it.";

const KIND_LABELS: Record<CrossPlanConflictKind, string> = {
    duplicate_medication: "Duplicate medicine",
    regimen_difference: "Different dose or schedule",
    stop_continue: "Stop vs continue",
    schedule_overlap: "Schedule overlap",
};

export function conflictKindLabel(kind: CrossPlanConflictKind): string {
    return KIND_LABELS[kind] ?? "Overlap";
}

type OtherPlan = NonNullable<CrossPlanConflict["other_plan"]>;

/** "Orthopaedics · Dr. Lee · Willow Terrace": parts that exist, never a guess. */
export function otherPlanLabel(other: OtherPlan | null): string {
    if (!other) return "Shared medication list";
    const parts = [other.specialty, other.clinician_name, other.clinic_name].filter((part): part is string => Boolean(part && part.trim()));
    return parts.length ? parts.join(" · ") : "Another care team";
}

function approvedOn(other: OtherPlan | null): string | null {
    return other?.approved_at ? `approved ${formatClinicianDate(other.approved_at, { month: "short", day: "numeric" })}` : null;
}

function waitingFor(conflict: CrossPlanConflict): string {
    return conflict.other_plan?.clinician_name ? `Waiting for ${conflict.other_plan.clinician_name}` : "Waiting for the other care team";
}

// ── Loading ───────────────────────────────────────────────────────────────────────────────

export type CrossPlanState =
    | { status: "idle" | "loading"; review: CrossPlanReview | null }
    | { status: "ready"; review: CrossPlanReview }
    | { status: "error"; review: CrossPlanReview | null; message: string };

/** The conflicts of one draft version. `refresh` re-runs the check; stale answers are dropped. */
export function useCrossPlanReview(patientId: string, versionId: string | null, enabled: boolean) {
    const [state, setState] = useState<CrossPlanState>({ status: "idle", review: null });
    const generation = useRef(0);

    const refresh = useCallback(async (): Promise<CrossPlanReview | null> => {
        if (!versionId || !enabled) {
            generation.current += 1;
            setState({ status: "idle", review: null });
            return null;
        }
        const request = ++generation.current;
        setState((current) => ({ status: "loading", review: current.review }));
        try {
            const review = await fetchCrossPlanReview(patientId, versionId);
            if (request !== generation.current) return null;
            setState({ status: "ready", review });
            return review;
        } catch (cause) {
            if (request !== generation.current) return null;
            setState((current) => ({ status: "error", review: current.review, message: cause instanceof Error ? cause.message : "The cross-plan check could not be loaded." }));
            return null;
        }
    }, [patientId, versionId, enabled]);

    useEffect(() => {
        // The check belongs to one saved version: a new version or patient starts clean.
        void refresh();
        return () => { generation.current += 1; };
    }, [refresh]);

    return { state, refresh };
}

/** Blockers that still stop publication. A reply from the other team never clears one. */
export function unresolvedBlockers(review: CrossPlanReview | null): CrossPlanConflict[] {
    return (review?.conflicts ?? []).filter((conflict) => conflict.severity === "blocker" && !conflict.acknowledged);
}

export function warningConflicts(review: CrossPlanReview | null): CrossPlanConflict[] {
    return (review?.conflicts ?? []).filter((conflict) => conflict.severity === "warning");
}

// ── Always-visible coverage line ─────────────────────────────────────────────────────────

/** Interaction severity is never assessed here; say so wherever the check's result is shown. */
export function InteractionCoverageNote({ className = "" }: { className?: string }) {
    return <p className={`flex items-start gap-1.5 text-xs text-muted ${className}`} data-testid="interaction-coverage">
        <Icon name="info" className="mt-px h-3.5 w-3.5 shrink-0" />
        <span><strong className="font-semibold text-ink-2">Interaction severity is not checked.</strong> Other care teams&apos; medicines are compared for duplicates, differing doses and stop-versus-continue only.</span>
    </p>;
}

// ── Comparison ───────────────────────────────────────────────────────────────────────────

export function InstructionLines({ medication }: { medication: ConflictMedication }) {
    const lines = [
        medication.name,
        [medication.dosage, medication.frequency, medication.route].filter(Boolean).join(" · "),
        medication.instructions,
    ].filter((line): line is string => Boolean(line && line.trim()));
    if (lines.length === 0) {
        return <p className="text-sm text-muted">{medication.category ? `Another activity in the category “${medication.category}”.` : "No instruction detail is shared for this item."}</p>;
    }
    return <div className="space-y-0.5 break-words text-sm text-ink">
        {lines.map((line, index) => <p className={index === 0 ? "font-semibold" : "text-ink-2"} key={index}>{line}</p>)}
    </div>;
}

export function ConflictComparison({ conflict }: { conflict: CrossPlanConflict }) {
    const date = approvedOn(conflict.other_plan);
    const sharedList = conflict.shared_list_entry_id || conflict.theirs.shared_list;
    return <div className="space-y-3">
        <dl className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2">
            <div className="flex items-center gap-1.5"><dt className="text-muted">Kind</dt><dd className="rounded-md bg-risk-tint px-1.5 py-0.5 font-semibold text-risk-ink">{conflictKindLabel(conflict.kind)}</dd></div>
            {sharedList ? <div className="flex items-center gap-1.5"><dt className="text-muted">Overlaps on</dt><dd className="font-medium">the shared medication list{conflict.theirs.name ? `: ${conflict.theirs.name}` : ""}</dd></div> : null}
        </dl>
        {/* Two columns when the pane is wide enough to read them, stacked in the narrow review pane and on phones. */}
        <div className="@container"><div className="grid gap-3 @xl:grid-cols-2">
            <section aria-label="This draft" className="rounded-xl border border-line-strong bg-surface p-3.5">
                <h4 className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.06em] text-muted">This draft</h4>
                <InstructionLines medication={conflict.ours} />
            </section>
            <section aria-label={`${otherPlanLabel(conflict.other_plan)}${date ? ` · ${date}` : ""}`} className="rounded-xl border border-line-strong bg-surface p-3.5">
                <h4 className="mb-1.5 break-words text-[12px] font-semibold text-ink-2">{otherPlanLabel(conflict.other_plan)}{date ? <span className="font-normal text-muted"> · {date}</span> : null}</h4>
                <InstructionLines medication={conflict.theirs} />
            </section>
        </div></div>
    </div>;
}

// ── Item-level blockers and warnings ─────────────────────────────────────────────────────

type Choice = "change" | "remove" | "keep_both" | "ask_other_team";

const CHOICES: Array<{ id: Choice; title: string; detail: string }> = [
    { id: "change", title: "Change this item", detail: "Edit the dose, schedule or wording below, then save your review. The check runs again." },
    { id: "remove", title: "Remove it", detail: "Take this item out of your plan, then save your review. The check runs again." },
    { id: "keep_both", title: "Keep both, with a reason", detail: "Both instructions stay. Your reason is recorded and shown to the other care team." },
    { id: "ask_other_team", title: "Ask the other care team", detail: "Send them a question. This item stays blocked until they reply or you resolve it another way." },
];

export type ResolveOutcome = { ok: true } | { ok: false; message: string; stale?: boolean };

function CharacterCount({ id, length, min }: { id: string; length: number; min: number }) {
    const short = length > 0 && length < min;
    return <p id={id} className={`mt-1 text-right font-mono text-[11px] ${short ? "text-risk-ink" : "text-muted"}`}>{length}/{REASON_MAX}{min > 1 ? ` · at least ${min} characters` : ""}</p>;
}

function BlockerCard({ conflict, busy, unsaved, otherChanged, onChangeItem, onRemoveItem, onResolve }: {
    conflict: CrossPlanConflict; busy: boolean; unsaved: boolean; otherChanged: boolean;
    onChangeItem: () => void; onRemoveItem: () => void;
    onResolve: (conflict: CrossPlanConflict, body: CrossPlanResolutionRequest) => Promise<ResolveOutcome>;
}) {
    const panelId = useId();
    const resolved = conflict.acknowledged;
    const waiting = conflict.asked_other_team && !resolved;
    const [open, setOpen] = useState(!resolved && !waiting);
    const [choice, setChoice] = useState<Choice | null>(null);
    const [reason, setReason] = useState("");
    const [question, setQuestion] = useState(DEFAULT_QUESTION);
    const [message, setMessage] = useState<string | null>(null);
    const [sending, setSending] = useState(false);
    const reasonId = useId();
    const questionId = useId();
    const trimmedReason = reason.trim();
    const trimmedQuestion = question.trim();
    const canSubmit = choice === "change" || choice === "remove" ||
        (choice === "keep_both" && trimmedReason.length >= REASON_MIN && trimmedReason.length <= REASON_MAX) ||
        (choice === "ask_other_team" && trimmedQuestion.length >= 1 && trimmedQuestion.length <= REASON_MAX);

    async function apply() {
        if (!choice || !canSubmit || sending) return;
        setMessage(null);
        if (choice === "change") { onChangeItem(); return; }
        if (choice === "remove") { onRemoveItem(); return; }
        setSending(true);
        const outcome = await onResolve(conflict, choice === "keep_both"
            ? { resolution: "keep_both", reason: trimmedReason }
            : { resolution: "ask_other_team", reason: trimmedQuestion });
        setSending(false);
        if (outcome.ok) { setChoice(null); setReason(""); setOpen(choice !== "keep_both"); }
        else setMessage(outcome.message);
    }

    return <section aria-label="Conflict with another care team's plan" className={`rounded-xl border-2 ${resolved ? "border-ok-line bg-ok-soft" : "border-risk bg-risk-soft"}`}>
        <h4 className="m-0">
            <button aria-controls={panelId} aria-expanded={open} className="flex w-full items-start gap-2.5 rounded-xl px-3.5 py-3 text-left" onClick={() => setOpen((value) => !value)} type="button">
                <Icon name={resolved ? "check" : "alert"} className={`mt-0.5 h-4 w-4 shrink-0 ${resolved ? "text-ok-ink" : "text-risk-ink"}`} />
                <span className="min-w-0 flex-1">
                    <span className={`block text-sm font-semibold ${resolved ? "text-ok-ink" : "text-risk-ink"}`}>Conflicts with another care team&apos;s plan</span>
                    <span className="mt-0.5 block break-words text-[13px] text-ink-2">{conflictKindLabel(conflict.kind)} · {otherPlanLabel(conflict.other_plan)}</span>
                    {resolved ? <span className="mt-1 block text-xs font-medium text-ok-ink">Kept both. Your reason is recorded.</span> : null}
                    {waiting ? <span className="mt-1 block text-xs font-semibold text-warn-ink" data-testid="waiting-state">{waitingFor(conflict)}</span> : null}
                </span>
                <Icon name="chevron" className={`mt-1 h-4 w-4 shrink-0 text-muted transition-transform ${open ? "rotate-90" : ""}`} />
            </button>
        </h4>
        <div className="space-y-4 px-3.5 pb-3.5" hidden={!open} id={panelId}>
            <ConflictComparison conflict={conflict} />
            {resolved && conflict.acknowledged_reason ? <p className="rounded-lg border border-ok-line bg-surface px-3 py-2 text-sm text-ink-2"><span className="font-semibold text-ink">Your reason: </span>{conflict.acknowledged_reason}</p> : null}
            {otherChanged ? <p className="rounded-lg border border-warn-line bg-warn-soft px-3 py-2 text-sm text-warn-ink" role="status">The instructions changed since you last acknowledged this overlap, so that reason no longer applies. Add a reason for the current instructions, or change or remove the item.</p> : null}
            {unsaved ? <p className="text-xs text-warn-ink">You have unsaved edits. Save your review to run this check again.</p> : null}
            {resolved ? null : <fieldset className="space-y-2" disabled={busy || sending}>
                <legend className="mb-1 text-[13px] font-semibold text-ink">How do you want to resolve this?</legend>
                <div className="space-y-2" role="radiogroup" aria-label="Resolution">
                    {CHOICES.map((option) => <label className={`flex cursor-pointer items-start gap-3 rounded-lg border bg-surface px-3 py-2.5 ${choice === option.id ? "border-primary ring-2 ring-[rgba(37,99,235,.15)]" : "border-line-strong hover:border-primary-line"}`} key={option.id}>
                        <input checked={choice === option.id} className="mt-1 h-4 w-4 shrink-0 accent-[var(--color-primary)]" name={`resolution-${conflict.fingerprint}`} onChange={() => { setChoice(option.id); setMessage(null); }} type="radio" value={option.id} />
                        <span className="min-w-0">
                            <span className="block text-sm font-semibold text-ink">{option.title}</span>
                            <span className="block text-xs text-ink-2">{option.detail}</span>
                        </span>
                    </label>)}
                </div>
                {choice === "keep_both" ? <div>
                    <label className="block text-[13px] font-medium text-ink-2" htmlFor={reasonId}>Reason for keeping both (required)</label>
                    <textarea aria-describedby={`${reasonId}-count`} className="mt-1 min-h-24 w-full rounded-[10px] border border-line-strong bg-surface px-3 py-2 text-sm text-ink outline-none transition focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)]" id={reasonId} maxLength={REASON_MAX} onChange={(event) => setReason(event.target.value)} placeholder="For example: both prescribers agreed on this combination on 10/12." value={reason} />
                    <CharacterCount id={`${reasonId}-count`} length={reason.length} min={REASON_MIN} />
                </div> : null}
                {choice === "ask_other_team" ? <div>
                    <label className="block text-[13px] font-medium text-ink-2" htmlFor={questionId}>Message to the other care team</label>
                    <textarea aria-describedby={`${questionId}-count`} className="mt-1 min-h-20 w-full rounded-[10px] border border-line-strong bg-surface px-3 py-2 text-sm text-ink outline-none transition focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)]" id={questionId} maxLength={REASON_MAX} onChange={(event) => setQuestion(event.target.value)} value={question} />
                    <CharacterCount id={`${questionId}-count`} length={question.length} min={1} />
                </div> : null}
                <div className="flex flex-wrap items-center gap-3 pt-1">
                    <button className="ma-press inline-flex h-[34px] items-center rounded-[9px] bg-primary px-4 text-[13px] font-semibold text-white hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-track disabled:text-[#94A3B8]" disabled={!canSubmit || sending || busy} onClick={() => void apply()} type="button">
                        {sending ? "Saving…" : choice === "keep_both" ? "Keep both" : choice === "ask_other_team" ? "Send to the other care team" : choice === "remove" ? "Remove this item" : choice === "change" ? "Edit this item" : "Choose how to resolve"}
                    </button>
                </div>
            </fieldset>}
            <div aria-live="polite">{message ? <p className="rounded-lg border border-risk-line bg-surface px-3 py-2 text-sm text-risk-ink" role="alert">{message}</p> : null}</div>
        </div>
    </section>;
}

function WarningNote({ conflicts }: { conflicts: CrossPlanConflict[] }) {
    if (conflicts.length === 0) return null;
    return <details className="ma-disclosure rounded-xl border border-warn-line bg-warn-soft">
        <summary className="min-h-10 px-3.5 py-2 text-[13px] font-medium text-warn-ink">Overlaps with other care teams&apos; activities ({conflicts.length}). These do not block publishing.</summary>
        <ul className="space-y-2 border-t border-warn-line px-3.5 pb-3 pt-2.5 text-sm text-ink-2">
            {conflicts.map((conflict) => <li key={conflict.fingerprint}>
                <span className="font-semibold text-ink">{conflictKindLabel(conflict.kind)}</span> with {otherPlanLabel(conflict.other_plan)}
                {conflict.theirs.category ? ` (${conflict.theirs.category})` : ""}. Check that the schedules fit together.
            </li>)}
        </ul>
    </details>;
}

/** Everything the cross-plan check says about one item: blockers, warnings and the coverage line. */
export function ItemCrossPlanSection({ review, status, itemId, unsaved, busy, acknowledged, onChangeItem, onRemoveItem, onResolve, onRetry }: {
    review: CrossPlanReview | null; status: CrossPlanState["status"]; itemId: string; unsaved: boolean; busy: boolean;
    /** Fingerprints this clinician acknowledged on this item during this session, to detect a stale reason. */
    acknowledged: ReadonlySet<string>;
    onChangeItem: () => void; onRemoveItem: () => void;
    onResolve: (conflict: CrossPlanConflict, body: CrossPlanResolutionRequest) => Promise<ResolveOutcome>;
    onRetry: () => void;
}) {
    if (!review) {
        return status === "error"
            ? <p className="flex flex-wrap items-center gap-2 text-xs text-warn-ink" role="status">The cross-plan check could not be loaded. Publishing is still checked by the server. <button className="font-semibold text-primary underline-offset-2 hover:underline" onClick={onRetry} type="button">Retry cross-plan check</button></p>
            : null;
    }
    const mine = review.conflicts.filter((conflict) => conflict.draft_item_id === itemId);
    const blockers = mine.filter((conflict) => conflict.severity === "blocker");
    const warnings = mine.filter((conflict) => conflict.severity === "warning");
    return <div className="space-y-3" data-testid="cross-plan-section">
        {blockers.map((conflict) => <BlockerCard
            busy={busy} conflict={conflict} key={conflict.fingerprint} onChangeItem={onChangeItem} onRemoveItem={onRemoveItem} onResolve={onResolve}
            otherChanged={!conflict.acknowledged && acknowledged.size > 0 && !acknowledged.has(conflict.fingerprint)}
            unsaved={unsaved} />)}
        <WarningNote conflicts={warnings} />
        <InteractionCoverageNote />
    </div>;
}

// ── Publish without ──────────────────────────────────────────────────────────────────────

export function PublishWithoutDialog({ open, items, busy, error, onClose, onConfirm }: {
    open: boolean; items: Array<{ id: string; title: string; reason: string }>; busy: boolean; error: string | null;
    onClose: () => void; onConfirm: () => void;
}) {
    return <Modal onClose={() => { if (!busy) onClose(); }} open={open} title="Publish without these items?">
        <div className="space-y-4">
            <p className="text-sm text-ink-2">The rest of the plan will be published now. {items.length === 1 ? "This item stays" : "These items stay"} in your next draft as pending, unchanged for the patient, until the conflict is resolved.</p>
            <ul aria-label="Items that will not be published" className="space-y-2">
                {items.map((item) => <li className="rounded-lg border border-risk-line bg-risk-soft px-3 py-2 text-sm" key={item.id}>
                    <span className="block break-words font-semibold text-ink">{item.title}</span>
                    <span className="block text-xs text-risk-ink">{item.reason}</span>
                </li>)}
            </ul>
            <p className="text-xs text-muted">The other care teams are told. Interaction severity is not checked.</p>
            {error ? <p className="rounded-lg border border-risk-line bg-risk-soft px-3 py-2 text-sm text-risk-ink" role="alert">{error}</p> : null}
            <div className="flex justify-end gap-2">
                <button className="ma-press h-[34px] rounded-[9px] border border-line-strong bg-surface px-4 text-[13px] font-medium text-ink-2 hover:bg-surface-2" disabled={busy} onClick={onClose} type="button">Cancel</button>
                <button className="ma-press h-[34px] rounded-[9px] bg-primary px-4 text-[13px] font-semibold text-white hover:bg-primary-hover disabled:bg-track disabled:text-[#94A3B8]" disabled={busy} onClick={onConfirm} type="button">{busy ? "Publishing…" : "Publish without these items"}</button>
            </div>
        </div>
    </Modal>;
}
