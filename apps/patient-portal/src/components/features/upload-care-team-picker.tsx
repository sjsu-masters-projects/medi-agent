"use client";

import { useState } from "react";
import { Modal } from "@/components/ui";
import { getCareTeamCopy, ownerLabel } from "@/content/care-team-copy";
import type { DocumentRoutingChoice } from "@/services/care-team-routing";
import type { Locale, UploadCareTeamOption } from "@/types";

/**
 * "Which care team is this for?" Radio cards, one per care team plus "Not sure". Required
 * before an upload; a single care team is preselected and shown read-only.
 */
export function UploadCareTeamPicker({ open, locale, fileName, options, busy, onCancel, onConfirm }: {
    open: boolean; locale: Locale; fileName: string; options: UploadCareTeamOption[]; busy: boolean;
    onCancel: () => void; onConfirm: (choice: DocumentRoutingChoice) => void;
}) {
    const copy = getCareTeamCopy(locale);
    const single = options.length === 1;
    const [selected, setSelected] = useState<string | null>(null);
    const [missing, setMissing] = useState(false);
    const value = single ? options[0].care_team_id : selected;

    function confirm() {
        if (!value) { setMissing(true); return; }
        onConfirm(value === "not_sure" ? { not_sure: true } : { care_team_id: value });
    }

    return <Modal open={open} onClose={() => { if (!busy) onCancel(); }} title={copy.uploadTitle} closeLabel={copy.close}>
        <div className="space-y-4">
            <p className="break-words text-[15px] leading-relaxed text-ink-2">{single ? copy.uploadSingleHint : copy.uploadHelp}</p>
            <p className="break-words text-[13px] text-muted [overflow-wrap:anywhere]">{copy.uploadFile(fileName)}</p>
            <fieldset className="space-y-2" aria-describedby={missing ? "upload-care-team-required" : undefined}>
                <legend className="sr-only">{copy.uploadTitle}</legend>
                {options.map((option) => <label key={option.care_team_id} className={`flex min-h-11 cursor-pointer items-start gap-3 rounded-2xl border p-3.5 ${value === option.care_team_id ? "border-brand bg-brand-tint/50" : "border-line-strong bg-surface"}`}>
                    <input type="radio" name="upload-care-team" className="mt-1 h-5 w-5 shrink-0 accent-[var(--color-brand)]" checked={value === option.care_team_id} disabled={single || busy} readOnly={single}
                        onChange={() => { setSelected(option.care_team_id); setMissing(false); }} />
                    <span className="min-w-0 break-words text-[15px] font-semibold leading-snug text-ink [overflow-wrap:anywhere]">{ownerLabel(option)}</span>
                </label>)}
                {!single ? <label className={`flex min-h-11 cursor-pointer items-start gap-3 rounded-2xl border p-3.5 ${value === "not_sure" ? "border-brand bg-brand-tint/50" : "border-line-strong bg-surface"}`}>
                    <input type="radio" name="upload-care-team" className="mt-1 h-5 w-5 shrink-0 accent-[var(--color-brand)]" checked={value === "not_sure"} disabled={busy}
                        onChange={() => { setSelected("not_sure"); setMissing(false); }} />
                    <span className="min-w-0">
                        <span className="block text-[15px] font-semibold leading-snug text-ink">{copy.uploadNotSure}</span>
                        <span className="block break-words text-[13px] leading-snug text-muted">{copy.uploadNotSureHint}</span>
                    </span>
                </label> : null}
            </fieldset>
            {missing ? <p id="upload-care-team-required" role="alert" className="rounded-2xl bg-danger-tint p-3 text-sm text-danger-ink">{copy.uploadRequired}</p> : null}
            <div className="flex flex-col gap-2 sm:flex-row-reverse">
                <button type="button" disabled={busy} onClick={confirm} className="ma-press min-h-[52px] w-full rounded-2xl bg-brand px-4 py-3 text-base font-semibold text-white hover:bg-brand-hover disabled:opacity-50">{copy.uploadConfirm}</button>
                <button type="button" disabled={busy} onClick={onCancel} className="ma-press min-h-[52px] w-full rounded-2xl bg-surface-2 px-4 py-3 text-base font-semibold text-ink-2 hover:bg-line-strong disabled:opacity-50">{copy.uploadCancel}</button>
            </div>
        </div>
    </Modal>;
}
