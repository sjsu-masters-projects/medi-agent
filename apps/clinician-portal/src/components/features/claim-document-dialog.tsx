"use client";

import { useEffect, useId, useState } from "react";
import { Modal } from "@/components/ui";
import { claimDocument, errorCode, fetchCareTeamOptions } from "@/services/care-team-plans";
import type { ClinicianCareTeamOption } from "@/types";

/** Label of the unrouted state, shown on every row and card that can be claimed. */
export const UNROUTED_LABEL = "Patient uploaded · not routed to a care team";

export function UnroutedBadge() {
    return <span className="inline-flex max-w-full items-center rounded-md bg-warn-tint px-2 py-0.5 text-[11px] font-semibold text-warn-ink">{UNROUTED_LABEL}</span>;
}

/**
 * Claiming an unrouted ("Not sure") patient upload makes it yours: you review it and it leaves
 * every other care team's queue. The claim is audited. Another team may claim it first: that
 * race ends with `onAlreadyClaimed`, and nothing is recorded for the loser.
 */
export function ClaimDocumentDialog({ open, patientId, documentId, fileName, claimableCareTeamIds, onClose, onClaimed, onAlreadyClaimed }: {
    open: boolean; patientId: string; documentId: string; fileName: string;
    /** The care teams of mine that may claim it; empty means load them. */
    claimableCareTeamIds: string[];
    onClose: () => void; onClaimed: () => void; onAlreadyClaimed: () => void;
}) {
    const selectId = useId();
    const [options, setOptions] = useState<ClinicianCareTeamOption[] | null>(null);
    const [loadFailed, setLoadFailed] = useState(false);
    const [careTeamId, setCareTeamId] = useState(claimableCareTeamIds.length === 1 ? claimableCareTeamIds[0] : "");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const known = claimableCareTeamIds.length === 1;

    useEffect(() => {
        if (!open || known) return;
        let active = true;
        void (async () => {
            try {
                const list = await fetchCareTeamOptions(patientId);
                if (!active) return;
                const usable = claimableCareTeamIds.length ? list.filter((option) => claimableCareTeamIds.includes(option.care_team_id)) : list;
                setOptions(usable);
                if (usable.length === 1) setCareTeamId(usable[0].care_team_id);
            } catch {
                if (active) setLoadFailed(true);
            }
        })();
        return () => { active = false; };
    }, [open, known, patientId, claimableCareTeamIds]);

    async function claim() {
        if (!careTeamId || busy) return;
        setBusy(true); setError(null);
        try {
            await claimDocument(documentId, careTeamId);
            onClaimed();
        } catch (cause) {
            if (errorCode(cause) === "DOCUMENT_ALREADY_CLAIMED") onAlreadyClaimed();
            else setError(cause instanceof Error ? cause.message : "Unable to claim this document.");
        } finally { setBusy(false); }
    }

    const choose = !known && options && options.length >= 2;
    return <Modal onClose={() => { if (!busy) onClose(); }} open={open} title="Claim this document?">
        <div className="space-y-4">
            <p className="break-words text-sm font-semibold text-ink">{fileName}</p>
            <p className="text-sm text-ink-2">The patient was not sure which care team this is for. If you claim it, <strong className="font-semibold text-ink">it becomes yours</strong>: you review it, and it leaves the other care teams&apos; queues. The claim is recorded.</p>
            {!known && !options && !loadFailed ? <p className="text-sm text-muted" role="status">Loading your care teams…</p> : null}
            {loadFailed ? <p className="text-sm text-risk-ink" role="alert">Your care teams could not be loaded. Close this and try again.</p> : null}
            {choose ? <div className="rounded-xl border border-line bg-surface-2 px-4 py-3">
                <label className="block">
                    <span className="mb-1.5 block text-[13px] font-medium text-ink-2">Claim for which care team? (required)</span>
                    <select className="h-10 w-full max-w-sm rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink" id={selectId} onChange={(event) => setCareTeamId(event.target.value)} value={careTeamId}>
                        {careTeamId ? null : <option disabled value="">Choose a care team</option>}
                        {options.map((option) => <option key={option.care_team_id} value={option.care_team_id}>{option.clinic_name ?? "Care team"}</option>)}
                    </select>
                </label>
            </div> : null}
            {error ? <p className="rounded-lg border border-risk-line bg-risk-soft px-3 py-2 text-sm text-risk-ink" role="alert">{error}</p> : null}
            <div className="flex justify-end gap-2">
                <button className="ma-press h-[34px] rounded-[9px] border border-line-strong bg-surface px-4 text-[13px] font-medium text-ink-2 hover:bg-surface-2" disabled={busy} onClick={onClose} type="button">Cancel</button>
                <button className="ma-press h-[34px] rounded-[9px] bg-primary px-4 text-[13px] font-semibold text-white hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-track disabled:text-[#94A3B8]" disabled={!careTeamId || busy} onClick={() => void claim()} type="button">{busy ? "Claiming…" : "Claim document"}</button>
            </div>
        </div>
    </Modal>;
}
