"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { ClinicChip } from "@/components/features/clinic-chip";
import { InstructionLines } from "@/components/features/cross-plan-conflicts";
import { AdoptPlanDialog, RetireItemsDialog } from "@/components/features/unowned-plan-dialogs";
import { Icon } from "@/components/ui/icons";
import { errorCode, replyToReviewItem, resolveConflictReply, takeRecord } from "@/services/care-team-plans";
import type { ClinicReviewItem, ConflictMedication, PlanReviewItem, ReviewItemKind } from "@/types";
import { formatClinicianDateTime } from "@/utils/dates";

const KIND_TITLES: Record<ReviewItemKind, string> = {
    cross_plan_conflict: "Another care team asks about a conflict",
    conflict_acknowledged: "A care team kept both instructions, with a reason",
    conflict_published_without: "A care team published without a conflicting item",
    conflict_reply: "The other care team replied",
    unowned_plan: "A care plan has no care team",
    unassigned_legacy_plan: "A legacy care plan could not be assigned",
    unowned_clinical_record: "A clinical record has no care team",
};

export function reviewKindTitle(kind: ReviewItemKind): string {
    return KIND_TITLES[kind] ?? "Care plan review";
}

const GROUPS: Array<{ id: string; title: string; kinds: ReviewItemKind[] }> = [
    { id: "conflicts", title: "Conflicts with other care teams", kinds: ["cross_plan_conflict", "conflict_reply"] },
    { id: "decisions", title: "Decisions you were told about", kinds: ["conflict_acknowledged", "conflict_published_without"] },
    { id: "unowned", title: "Plans that need an owner", kinds: ["unowned_plan", "unassigned_legacy_plan", "unowned_clinical_record"] },
];

const REPLY_MAX = 2000;

function text(value: unknown): string | null {
    return typeof value === "string" && value.trim() ? value.trim() : null;
}

function medication(value: unknown): ConflictMedication {
    return value && typeof value === "object" ? (value as ConflictMedication) : {};
}

/** "Orthopaedics · Dr. Lee · Willow Terrace" from the `from` owner snapshot, when it has names. */
function fromLabel(summary: Record<string, unknown>): string | null {
    const from = summary.from;
    if (!from || typeof from !== "object") return null;
    const owner = from as Record<string, unknown>;
    const parts = [text(owner.specialty), text(owner.clinician_name), text(owner.clinic_name)].filter((part): part is string => part !== null);
    return parts.length ? parts.join(" · ") : null;
}

type Outcome = { kind: "replied" | "adopted" | "lost" | "retired" | "taken"; message: string };

export function PlanReviewItemRow({ item, patientLabel, clinicName, highlighted, onChanged }: {
    item: PlanReviewItem; patientLabel?: string | null; clinicName?: string | null; highlighted?: boolean; onChanged: () => void;
}) {
    const replyId = useId();
    const row = useRef<HTMLLIElement>(null);
    const [reply, setReply] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [outcome, setOutcome] = useState<Outcome | null>(null);
    const [dialog, setDialog] = useState<"adopt" | "retire" | null>(null);

    useEffect(() => {
        if (!highlighted) return;
        row.current?.scrollIntoView?.({ block: "center" });
        row.current?.focus({ preventScroll: true });
    }, [highlighted]);

    const conflictKind = item.kind === "cross_plan_conflict" || item.kind === "conflict_acknowledged" || item.kind === "conflict_published_without" || item.kind === "conflict_reply";
    const fromAsker = item.kind === "conflict_reply";
    const from = fromLabel(item.summary);
    const needsReply = item.kind === "cross_plan_conflict";
    const canAnswer = needsReply || item.kind === "conflict_acknowledged" || item.kind === "conflict_published_without";
    const unowned = item.kind === "unowned_plan" || item.kind === "unassigned_legacy_plan";
    const record = item.kind === "unowned_clinical_record" ? (text(item.summary.record) === "medwatch_draft" ? "medwatch_draft" : text(item.summary.record) === "adr_assessment" ? "adr_assessment" : null) : null;
    const recordId = text(item.summary.record_id);
    const recordLabel = record === "medwatch_draft" ? "MedWatch draft" : "ADR review";
    const planHref = `/patients/${encodeURIComponent(item.patient_id)}?tab=care-plan`;

    async function take() {
        if (!record || !recordId || busy) return;
        setBusy(true); setError(null);
        try {
            await takeRecord(record, recordId, item.target_care_team_id);
            setOutcome({ kind: "taken", message: `You took this ${recordLabel}. It now belongs to your care team.` });
        } catch (cause) {
            if (errorCode(cause) === "RECORD_ALREADY_TAKEN") setOutcome({ kind: "lost", message: "Another care team took this record." });
            else setError(cause instanceof Error ? cause.message : "Unable to take this record.");
        } finally { setBusy(false); }
    }

    const [keepBothOpen, setKeepBothOpen] = useState(false);
    const [keepReason, setKeepReason] = useState("");

    async function resolveReply(action: "accept" | "keep_both") {
        if (busy || (action === "keep_both" && !keepReason.trim())) return;
        setBusy(true); setError(null);
        try {
            const result = await resolveConflictReply(item.id, action, action === "keep_both" ? keepReason.trim() : undefined);
            setOutcome({ kind: "replied", message: action === "keep_both"
                ? "Both instructions are kept with your reason. Your draft can be published."
                : result.still_blocking
                    ? "Reply accepted. The conflict still blocks your draft: keep both with a reason, or adjust your plan."
                    : "Reply accepted. The conflict no longer blocks your draft." });
        } catch (cause) {
            setError(errorCode(cause) === "CONFLICT_CHANGED" ? "This conflict has changed since the reply. Reload and review it again." : cause instanceof Error ? cause.message : "Unable to resolve this reply.");
        } finally { setBusy(false); }
    }

    async function answer() {
        if (busy || (needsReply && !reply.trim())) return;
        setBusy(true); setError(null);
        try {
            await replyToReviewItem(item.id, reply.trim() || undefined);
            setOutcome({ kind: "replied", message: needsReply ? "Reply sent. It informs the other care team; their publication stays blocked until they resolve the conflict." : "Marked as seen." });
        } catch (cause) {
            setError(cause instanceof Error ? cause.message : "Unable to send your reply.");
        } finally { setBusy(false); }
    }

    return <li aria-label={reviewKindTitle(item.kind)} className={`border-b border-line px-[22px] py-4 outline-none last:border-b-0 ${highlighted ? "bg-primary-tint ring-2 ring-inset ring-primary-line" : ""}`} id={`review-item-${item.id}`} ref={row} tabIndex={-1}>
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
            <div className="min-w-0">
                <h3 className="break-words text-sm font-semibold text-ink">{reviewKindTitle(item.kind)}</h3>
                <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
                    {patientLabel ? <span className="font-medium text-ink-2">{patientLabel}</span> : null}
                    <ClinicChip name={clinicName} />
                    <time dateTime={item.created_at}>{formatClinicianDateTime(item.created_at)}</time>
                </p>
            </div>
            <Link className="text-[13px] font-medium text-primary hover:underline" href={planHref}>{conflictKind ? "Open care plan" : "Open patient care plan"}</Link>
        </div>

        {conflictKind ? <div className="mt-3 space-y-3">
            {from ? <p className="text-[13px] text-ink-2">{fromAsker ? "Replied by" : "From"} <span className="font-semibold text-ink">{from}</span></p> : null}
            {item.request_note ? <p className="whitespace-pre-wrap break-words rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm text-ink-2"><span className="font-semibold text-ink">{fromAsker ? "Their reply: " : "Their message: "}</span>{item.request_note}</p> : null}
            <div className="grid gap-3 md:grid-cols-2">
                <section aria-label={fromAsker ? "Your draft" : "Their draft"} className="rounded-xl border border-line-strong bg-surface p-3.5">
                    <h4 className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.06em] text-muted">{fromAsker ? "Your draft" : "Their draft"}</h4>
                    <InstructionLines medication={medication(item.summary.ours)} />
                </section>
                <section aria-label={fromAsker ? "Their plan" : "Your plan"} className="rounded-xl border border-line-strong bg-surface p-3.5">
                    <h4 className="mb-1.5 font-mono text-[11px] uppercase tracking-[0.06em] text-muted">{fromAsker ? "Their plan" : "Your plan"}</h4>
                    <InstructionLines medication={medication(item.summary.theirs)} />
                </section>
            </div>
            {item.reply_note ? <p className="text-sm text-ink-2"><span className="font-semibold text-ink">Reply: </span>{item.reply_note}</p> : null}
        </div> : (
            item.kind === "unowned_clinical_record"
            ? <p className="mt-2 max-w-[80ch] text-sm text-ink-2">An older {recordLabel} for this patient has no care team, so no clinician can see it yet. If you take it, it becomes your care team&apos;s record and the other care teams stop seeing it.</p>
            : <p className="mt-2 max-w-[80ch] text-sm text-ink-2">{item.kind === "unowned_plan"
                ? "The care team that wrote this plan has ended. The patient's approved activities and reminders continue unchanged. Adopt the plan to make it yours, or retire specific items. Nothing is removed automatically."
                : "This plan could not be matched to one care team without guessing. The patient's approved activities and reminders continue unchanged. Adopt the plan to make it yours, or retire specific items."}</p>
        )}

        {outcome ? <div aria-live="polite" className="mt-3 flex flex-wrap items-center gap-3">
            <p className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-sm ${outcome.kind === "lost" ? "border-warn-line bg-warn-soft text-warn-ink" : "border-ok-line bg-ok-soft text-ok-ink"}`} role="status">
                <Icon name={outcome.kind === "lost" ? "alert" : "check"} className="mt-0.5 h-4 w-4 shrink-0" />{outcome.message}
            </p>
            <button className="ma-press h-8 rounded-lg border border-line-strong bg-surface px-3 text-[13px] font-medium text-ink-2 hover:bg-surface-2" onClick={onChanged} type="button">Done</button>
        </div> : <div className="mt-3 space-y-3">
            {canAnswer ? <div>
                <label className="block text-[13px] font-medium text-ink-2" htmlFor={replyId}>{needsReply ? "Your reply (required)" : "Note (optional)"}</label>
                <textarea aria-describedby={`${replyId}-count`} className="mt-1 min-h-20 w-full rounded-[10px] border border-line-strong bg-surface px-3 py-2 text-sm text-ink outline-none transition focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)]" id={replyId} maxLength={REPLY_MAX} onChange={(event) => setReply(event.target.value)} value={reply} />
                <p className="mt-1 text-right font-mono text-[11px] text-muted" id={`${replyId}-count`}>{reply.length}/{REPLY_MAX}</p>
            </div> : null}
            {error ? <p className="rounded-lg border border-risk-line bg-risk-soft px-3 py-2 text-sm text-risk-ink" role="alert">{error}</p> : null}
            <div className="flex flex-wrap items-center gap-2">
                {canAnswer ? <button className="ma-press inline-flex h-8 items-center rounded-lg bg-primary px-3 text-[13px] font-semibold text-white hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-track disabled:text-[#94A3B8]" disabled={busy || (needsReply && !reply.trim())} onClick={() => void answer()} type="button">{busy ? "Saving…" : needsReply ? "Send reply" : "Mark as seen"}</button> : null}
                {needsReply ? <Link className="ma-press inline-flex h-8 items-center rounded-lg border border-line-strong bg-surface px-3 text-[13px] font-medium text-ink-2 hover:bg-surface-2" href={planHref}>Adjust my plan</Link> : null}
                {fromAsker ? <>
                    <button className="ma-press inline-flex h-8 items-center rounded-lg bg-primary px-3 text-[13px] font-semibold text-white hover:bg-primary-hover disabled:opacity-60" disabled={busy} onClick={() => void resolveReply("accept")} type="button">{busy && !keepBothOpen ? "Saving…" : "Accept their answer"}</button>
                    <button aria-expanded={keepBothOpen} className="ma-press inline-flex h-8 items-center rounded-lg border border-line-strong bg-surface px-3 text-[13px] font-medium text-ink-2 hover:bg-surface-2" onClick={() => setKeepBothOpen((open) => !open)} type="button">Keep both instructions</button>
                    <Link className="ma-press inline-flex h-8 items-center rounded-lg border border-line-strong bg-surface px-3 text-[13px] font-medium text-ink-2 hover:bg-surface-2" href={planHref}>Adjust my plan</Link>
                </> : null}
                {record && recordId ? <button className="ma-press inline-flex h-8 items-center rounded-lg bg-primary px-3 text-[13px] font-semibold text-white hover:bg-primary-hover disabled:opacity-60" disabled={busy} onClick={() => void take()} type="button">{busy ? "Taking…" : `Take this ${recordLabel}`}</button> : null}
                {unowned && item.care_plan_id ? <>
                    <button className="ma-press inline-flex h-8 items-center rounded-lg bg-primary px-3 text-[13px] font-semibold text-white hover:bg-primary-hover" onClick={() => setDialog("adopt")} type="button">Adopt this plan</button>
                    <button className="ma-press inline-flex h-8 items-center rounded-lg border border-line-strong bg-surface px-3 text-[13px] font-medium text-ink-2 hover:bg-surface-2" onClick={() => setDialog("retire")} type="button">Retire items</button>
                </> : null}
            </div>
            {fromAsker && keepBothOpen ? <div>
                <label className="block text-[13px] font-medium text-ink-2" htmlFor={`${replyId}-keep`}>Reason for keeping both (required)</label>
                <textarea className="mt-1 min-h-20 w-full rounded-[10px] border border-line-strong bg-surface px-3 py-2 text-sm text-ink outline-none transition focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)]" id={`${replyId}-keep`} maxLength={REPLY_MAX} onChange={(event) => setKeepReason(event.target.value)} value={keepReason} />
                <button className="ma-press mt-2 inline-flex h-8 items-center rounded-lg bg-primary px-3 text-[13px] font-semibold text-white hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-track disabled:text-[#94A3B8]" disabled={busy || !keepReason.trim()} onClick={() => void resolveReply("keep_both")} type="button">{busy ? "Saving…" : "Keep both with this reason"}</button>
            </div> : null}
            {fromAsker ? <p className="text-xs text-muted">Accepting only closes this reply; your draft stays blocked until the conflict is resolved.</p> : null}
            {needsReply ? <p className="text-xs text-muted">Your reply informs the other care team. It does not release their publication block.</p> : null}
        </div>}

        {unowned && item.care_plan_id ? <>
            <AdoptPlanDialog carePlanId={item.care_plan_id} careTeamId={item.target_care_team_id} onClose={() => setDialog(null)}
                onDone={({ adopted, lost }) => { setDialog(null); setOutcome(adopted ? { kind: "adopted", message: "You adopted this plan. It is yours to review and approve." } : lost ? { kind: "lost", message: "Another clinician adopted this plan." } : null); }}
                open={dialog === "adopt"} patientId={item.patient_id} />
            <RetireItemsDialog carePlanId={item.care_plan_id} careTeamId={item.target_care_team_id} onClose={() => setDialog(null)}
                onDone={() => { setDialog(null); setOutcome({ kind: "retired", message: "The selected items were retired from this plan." }); }}
                open={dialog === "retire"} patientId={item.patient_id} />
        </> : null}
    </li>;
}

const CLINIC_KIND_TEXT: Partial<Record<ReviewItemKind, string>> = {
    unowned_plan: "A care plan at this clinic has no care team and needs an owner.",
    unassigned_legacy_plan: "A legacy care plan at this clinic could not be assigned to a care team.",
};

export function ClinicReviewItemRow({ item, clinicName, highlighted }: { item: ClinicReviewItem; clinicName?: string | null; highlighted?: boolean }) {
    const row = useRef<HTMLLIElement>(null);
    useEffect(() => {
        if (!highlighted) return;
        row.current?.scrollIntoView?.({ block: "center" });
        row.current?.focus({ preventScroll: true });
    }, [highlighted]);
    return <li className={`flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-[22px] py-3 outline-none last:border-b-0 ${highlighted ? "bg-primary-tint ring-2 ring-inset ring-primary-line" : ""}`} id={`review-item-${item.id}`} ref={row} tabIndex={-1}>
        <span className="min-w-0 flex-1 basis-64 text-sm text-ink-2">{CLINIC_KIND_TEXT[item.kind] ?? "A care plan at this clinic needs review."}</span>
        <ClinicChip name={clinicName} />
        <time className="text-xs text-muted" dateTime={item.created_at}>{formatClinicianDateTime(item.created_at)}</time>
    </li>;
}

/** The open review items grouped by what the clinician has to do. */
export function PlanReviewItemsList({ items, showClinic = false, highlightId, onChanged }: {
    items: PlanReviewItem[];
    /** Name the clinic on each row (multi-clinic clinicians). The name and clinic come from the item. */
    showClinic?: boolean;
    highlightId?: string | null;
    onChanged: () => void;
}) {
    return <div className="space-y-5">
        {GROUPS.map((group) => {
            const rows = items.filter((item) => group.kinds.includes(item.kind));
            if (rows.length === 0) return null;
            return <section aria-labelledby={`review-group-${group.id}`} className="overflow-hidden rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]" key={group.id}>
                <div className="flex items-center justify-between gap-3 border-b border-line px-[22px] py-3.5">
                    <h2 className="text-[15px] font-semibold text-ink" id={`review-group-${group.id}`}>{group.title}</h2>
                    <span className="rounded-[7px] bg-sunken px-2 py-1 font-mono text-xs font-medium text-ink-2">{rows.length}</span>
                </div>
                <ul>
                    {rows.map((item) => {
                        return <PlanReviewItemRow clinicName={showClinic ? (item.clinic_name ?? null) : null} highlighted={highlightId === item.id} item={item} key={item.id} onChanged={onChanged} patientLabel={item.patient_name ?? null} />;
                    })}
                </ul>
            </section>;
        })}
    </div>;
}

