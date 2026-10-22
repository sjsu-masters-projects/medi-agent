"use client";

import { useEffect, useId, useState } from "react";
import { Modal } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { adoptCarePlan, errorCode, fetchUnownedActivities, retireCarePlanItems } from "@/services/care-team-plans";
import type { UnownedPlanActivities } from "@/types";

/**
 * A plan with no owning care team keeps its approved activities in the patient's Today until a
 * clinician adopts it (it becomes theirs) or retires specific items. Nothing is removed
 * automatically. The dialogs here are the only way to do either.
 */

const NOTE_MAX = 2000;

type Activities = UnownedPlanActivities["activities"];

function ownerText(owner: UnownedPlanActivities["previous_owner"] | undefined): string {
    const parts = [owner?.specialty, owner?.clinician_name, owner?.clinic_name].filter((part): part is string => Boolean(part && part.trim()));
    return parts.length ? parts.join(" · ") : "a previous care team";
}

/** Loads the activities of one unowned plan for a dialog. */
function useUnownedActivities(open: boolean, patientId: string, carePlanId: string) {
    const [state, setState] = useState<{ status: "loading" | "ready" | "error"; data: UnownedPlanActivities | null }>({ status: "loading", data: null });
    const [attempt, setAttempt] = useState(0);
    useEffect(() => {
        if (!open) return;
        let active = true;
        void (async () => {
            setState({ status: "loading", data: null });
            try {
                const data = await fetchUnownedActivities(patientId, carePlanId);
                if (active) setState({ status: "ready", data });
            } catch {
                if (active) setState({ status: "error", data: null });
            }
        })();
        return () => { active = false; };
    }, [open, patientId, carePlanId, attempt]);
    return { ...state, retry: () => setAttempt((value) => value + 1) };
}

function ActivityList({ activities }: { activities: Activities }) {
    if (activities.length === 0) return <p className="text-sm text-muted">This plan has no active activities.</p>;
    return <ul aria-label="Activities in this plan" className="max-h-52 space-y-1.5 overflow-y-auto rounded-lg border border-line bg-surface-2 p-2.5">
        {activities.map((activity) => <li className="break-words text-sm text-ink" key={activity.id}>
            <span className="font-semibold">{activity.title}</span>
            {activity.frequency ? <span className="text-ink-2"> · {activity.frequency}</span> : null}
        </li>)}
    </ul>;
}

function NoteField({ id, label, value, onChange, hint }: { id: string; label: string; value: string; onChange: (value: string) => void; hint: string }) {
    return <div>
        <label className="block text-[13px] font-medium text-ink-2" htmlFor={id}>{label}</label>
        <textarea aria-describedby={`${id}-count`} className="mt-1.5 min-h-24 w-full rounded-[10px] border border-line-strong bg-surface px-3.5 py-2.5 text-sm text-ink outline-none transition placeholder:text-[#94A3B8] focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)]" id={id} maxLength={NOTE_MAX} onChange={(event) => onChange(event.target.value)} placeholder={hint} value={value} />
        <p className="mt-1 text-right font-mono text-[11px] text-muted" id={`${id}-count`}>{value.length}/{NOTE_MAX}</p>
    </div>;
}

export function AdoptPlanDialog({ open, patientId, carePlanId, careTeamId, onClose, onDone }: {
    open: boolean; patientId: string; carePlanId: string; careTeamId: string;
    onClose: () => void;
    /** `lost` is true when another clinician adopted the plan first. */
    onDone: (result: { adopted: boolean; lost: boolean }) => void;
}) {
    const noteId = useId();
    const activities = useUnownedActivities(open, patientId, carePlanId);
    const [note, setNote] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [lost, setLost] = useState(false);

    async function adopt() {
        if (!note.trim() || busy) return;
        setBusy(true); setError(null);
        try {
            await adoptCarePlan(carePlanId, { care_team_id: careTeamId, note: note.trim() });
            onDone({ adopted: true, lost: false });
        } catch (cause) {
            if (errorCode(cause) === "PLAN_ALREADY_ADOPTED") { setLost(true); }
            else setError(cause instanceof Error ? cause.message : "Unable to adopt this plan.");
        } finally { setBusy(false); }
    }

    return <Modal onClose={() => { if (busy) return; if (lost) onDone({ adopted: false, lost: true }); else onClose(); }} open={open} title="Adopt this care plan?">
        {lost ? <div className="space-y-4" role="alert">
            <p className="flex items-start gap-2 rounded-xl border border-warn-line bg-warn-soft px-4 py-3 text-sm text-warn-ink"><Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />Another clinician adopted this plan. Nothing was changed by you, and the patient&apos;s activities are unchanged.</p>
            <div className="flex justify-end"><button className="ma-press h-[34px] rounded-[9px] bg-primary px-4 text-[13px] font-semibold text-white hover:bg-primary-hover" onClick={() => onDone({ adopted: false, lost: true })} type="button">Close</button></div>
        </div> : <div className="space-y-4">
            <p className="text-sm text-ink-2">This plan was written by {ownerText(activities.data?.previous_owner)}, who is no longer on the patient&apos;s care team. If you adopt it, <strong className="font-semibold text-ink">it becomes yours</strong>: you review, change and approve it from now on, and the other care teams see you as its owner.</p>
            <p className="text-sm text-ink-2">The patient&apos;s activities stay in Today unchanged. Adopting does not change any medication.</p>
            {activities.status === "loading" ? <p className="text-sm text-muted" role="status">Loading the plan&apos;s activities…</p> : null}
            {activities.status === "error" ? <p className="flex flex-wrap items-center gap-3 text-sm text-risk-ink" role="alert">The activities could not be loaded. <button className="font-semibold text-primary hover:underline" onClick={activities.retry} type="button">Try again</button></p> : null}
            {activities.data ? <ActivityList activities={activities.data.activities} /> : null}
            <NoteField hint="Why you are adopting this plan, for the record." id={noteId} label="Note (required)" onChange={setNote} value={note} />
            {error ? <p className="rounded-lg border border-risk-line bg-risk-soft px-3 py-2 text-sm text-risk-ink" role="alert">{error}</p> : null}
            <div className="flex justify-end gap-2">
                <button className="ma-press h-[34px] rounded-[9px] border border-line-strong bg-surface px-4 text-[13px] font-medium text-ink-2 hover:bg-surface-2" disabled={busy} onClick={onClose} type="button">Cancel</button>
                <button className="ma-press h-[34px] rounded-[9px] bg-primary px-4 text-[13px] font-semibold text-white hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-track disabled:text-[#94A3B8]" disabled={!note.trim() || busy || activities.status === "loading"} onClick={() => void adopt()} type="button">{busy ? "Adopting…" : "Adopt this plan"}</button>
            </div>
        </div>}
    </Modal>;
}

export function RetireItemsDialog({ open, patientId, carePlanId, careTeamId, onClose, onDone }: {
    open: boolean; patientId: string; carePlanId: string; careTeamId: string;
    onClose: () => void; onDone: () => void;
}) {
    const reasonId = useId();
    const activities = useUnownedActivities(open, patientId, carePlanId);
    const [selected, setSelected] = useState<string[]>([]);
    const [reason, setReason] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const list = activities.data?.activities ?? [];

    async function retire() {
        if (!reason.trim() || selected.length === 0 || busy) return;
        setBusy(true); setError(null);
        try {
            await retireCarePlanItems(carePlanId, { care_team_id: careTeamId, item_ids: selected, reason: reason.trim() });
            onDone();
        } catch (cause) {
            setError(cause instanceof Error ? cause.message : "Unable to retire these items.");
        } finally { setBusy(false); }
    }

    return <Modal onClose={() => { if (!busy) onClose(); }} open={open} title="Retire plan items">
        <div className="space-y-4">
            <p className="text-sm text-ink-2">Choose the items to retire from this plan. Retired items no longer appear in the patient&apos;s approved care plan. Your reason is recorded. Nothing else in the plan changes.</p>
            {activities.status === "loading" ? <p className="text-sm text-muted" role="status">Loading the plan&apos;s activities…</p> : null}
            {activities.status === "error" ? <p className="flex flex-wrap items-center gap-3 text-sm text-risk-ink" role="alert">The activities could not be loaded. <button className="font-semibold text-primary hover:underline" onClick={activities.retry} type="button">Try again</button></p> : null}
            {activities.data ? <fieldset className="space-y-1.5">
                <legend className="mb-1 text-[13px] font-semibold text-ink">Items to retire ({selected.length} selected)</legend>
                {list.length === 0 ? <p className="text-sm text-muted">This plan has no active activities.</p> : null}
                {list.map((activity) => <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-line-strong bg-surface px-3 py-2.5 hover:border-primary-line" key={activity.id}>
                    <input checked={selected.includes(activity.id)} className="mt-1 h-4 w-4 shrink-0 accent-[var(--color-primary)]" onChange={(event) => setSelected((current) => event.target.checked ? [...current, activity.id] : current.filter((id) => id !== activity.id))} type="checkbox" />
                    <span className="min-w-0 break-words text-sm"><span className="font-semibold text-ink">{activity.title}</span>{activity.frequency ? <span className="text-ink-2"> · {activity.frequency}</span> : null}{activity.instructions ? <span className="block text-xs text-ink-2">{activity.instructions}</span> : null}</span>
                </label>)}
            </fieldset> : null}
            <NoteField hint="Why these items are being retired." id={reasonId} label="Reason (required)" onChange={setReason} value={reason} />
            {error ? <p className="rounded-lg border border-risk-line bg-risk-soft px-3 py-2 text-sm text-risk-ink" role="alert">{error}</p> : null}
            <div className="flex justify-end gap-2">
                <button className="ma-press h-[34px] rounded-[9px] border border-line-strong bg-surface px-4 text-[13px] font-medium text-ink-2 hover:bg-surface-2" disabled={busy} onClick={onClose} type="button">Cancel</button>
                <button className="ma-press h-[34px] rounded-[9px] bg-risk px-4 text-[13px] font-semibold text-white hover:bg-risk-strong disabled:cursor-not-allowed disabled:bg-track disabled:text-[#94A3B8]" disabled={!reason.trim() || selected.length === 0 || busy} onClick={() => void retire()} type="button">{busy ? "Retiring…" : `Retire ${selected.length || ""} item${selected.length === 1 ? "" : "s"}`.replace("  ", " ")}</button>
            </div>
        </div>
    </Modal>;
}
