"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSelector } from "react-redux";
import { Modal } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { getCareTeamCopy, ownerLabel } from "@/content/care-team-copy";
import { api } from "@/services/api";
import type { RootState } from "@/store/store";
import type { Locale, PatientCondition } from "@/types";

function isCondition(value: unknown): value is PatientCondition {
    const row = value as Partial<PatientCondition> | null;
    return Boolean(row) && typeof row?.id === "string" && typeof row?.name === "string" && typeof row?.is_sensitive === "boolean";
}

/**
 * Conditions the patient can keep private: "Keep private" switch per condition, a confirm
 * step, an optimistic change that rolls back when the save fails. Medications and
 * allergies are never listed here because they are always shared for safety.
 */
export function ConditionsPrivacy({ locale }: { locale: Locale }) {
    const copy = getCareTeamCopy(locale);
    const accessToken = useSelector((state: RootState) => state.auth.accessToken);
    const [conditions, setConditions] = useState<PatientCondition[] | null>(null);
    const [failed, setFailed] = useState(false);
    const [pending, setPending] = useState<PatientCondition | null>(null);
    const [saving, setSaving] = useState<Set<string>>(new Set());
    const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
    const mounted = useRef(true);
    useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

    const load = useCallback(async () => {
        if (!accessToken) return;
        setFailed(false);
        try {
            const result = await api.get<unknown>("/api/v1/care-team/patient/conditions", { token: accessToken });
            if (!mounted.current) return;
            setConditions(Array.isArray(result) ? result.filter(isCondition) : []);
        } catch {
            if (mounted.current) setFailed(true);
        }
    }, [accessToken]);
    useEffect(() => { void load(); }, [load]);

    async function apply(condition: PatientCondition) {
        const next = !condition.is_sensitive;
        setPending(null);
        setMessage(null);
        setSaving((current) => new Set(current).add(condition.id));
        setConditions((current) => current?.map((row) => (row.id === condition.id ? { ...row, is_sensitive: next } : row)) ?? current);
        try {
            await api.put(`/api/v1/care-team/patient/conditions/${encodeURIComponent(condition.id)}/sensitivity`, { is_sensitive: next }, { token: accessToken ?? undefined });
            if (mounted.current) setMessage({ kind: "ok", text: copy.privacySaved(condition.name, next) });
        } catch {
            if (!mounted.current) return;
            // Roll back to what the server still has.
            setConditions((current) => current?.map((row) => (row.id === condition.id ? { ...row, is_sensitive: condition.is_sensitive } : row)) ?? current);
            setMessage({ kind: "error", text: copy.privacyError });
        } finally {
            if (mounted.current) setSaving((current) => { const rest = new Set(current); rest.delete(condition.id); return rest; });
        }
    }

    if (failed && !conditions) {
        return <section aria-label={copy.conditionsTitle} className="mx-4 mt-5 flex flex-wrap items-center gap-3 rounded-[22px] bg-surface p-4">
            <p role="alert" className="min-w-0 flex-1 text-sm text-danger-ink">{copy.conditionsLoadError}</p>
            <button type="button" onClick={() => void load()} className="ma-press min-h-11 rounded-[14px] bg-surface-2 px-4 text-sm font-semibold text-ink-2 hover:bg-line-strong">{copy.conditionsRetry}</button>
        </section>;
    }
    if (!conditions || conditions.length === 0) return null;

    return <section aria-labelledby="conditions-privacy-title" className="pt-1">
        <h2 id="conditions-privacy-title" className="px-[22px] pt-5 pb-1 font-mono text-xs uppercase tracking-[0.08em] text-muted">{copy.conditionsTitle}</h2>
        <p className="px-[22px] pb-2 text-[13px] leading-snug text-muted">{copy.conditionsIntro}</p>
        <ul className="mx-4 overflow-hidden rounded-[22px] bg-surface [&>li+li]:border-t [&>li+li]:border-line">
            {conditions.map((condition) => {
                const busy = saving.has(condition.id);
                const owner = ownerLabel({ specialty: condition.recorded_by?.specialty ?? null, clinician_name: condition.recorded_by?.clinician_name ?? null, clinic_name: condition.recorded_by?.clinic_name ?? null });
                return <li key={condition.id} className="flex items-start gap-3 px-[14px] py-3">
                    <div className="min-w-0 flex-1 space-y-0.5">
                        <p className="break-words text-[15px] font-semibold leading-snug text-ink [overflow-wrap:anywhere]">{condition.name}</p>
                        {owner ? <p className="break-words text-[13px] text-muted [overflow-wrap:anywhere]">{copy.recordedBy(owner)}</p> : null}
                        <p className="break-words text-[13px] leading-snug text-muted">{copy.keepPrivateHelp}</p>
                    </div>
                    <div className="flex shrink-0 flex-col items-center gap-1 pt-0.5">
                        <button type="button" role="switch" aria-checked={condition.is_sensitive} aria-label={copy.keepPrivateFor(condition.name)} disabled={busy} onClick={() => setPending(condition)}
                            className={`ma-press relative flex h-11 w-[60px] items-center rounded-full px-1 disabled:opacity-60`}>
                            <span aria-hidden="true" className={`flex h-[30px] w-[52px] items-center rounded-full p-[3px] transition-colors motion-reduce:transition-none ${condition.is_sensitive ? "bg-brand" : "bg-muted"}`}>
                                <span className={`flex h-6 w-6 items-center justify-center rounded-full bg-white shadow transition-transform motion-reduce:transition-none ${condition.is_sensitive ? "translate-x-[22px]" : "translate-x-0"}`}>
                                    {condition.is_sensitive ? <Icon name="lock" className="h-3.5 w-3.5 text-brand" /> : null}
                                </span>
                            </span>
                        </button>
                        <span aria-hidden="true" className="text-[11px] font-semibold text-muted">{copy.keepPrivate}</span>
                    </div>
                </li>;
            })}
        </ul>
        <div aria-live="polite" className="px-4">
            {message ? <p role={message.kind === "error" ? "alert" : "status"} className={`mt-2 rounded-2xl p-3 text-sm ${message.kind === "error" ? "bg-danger-tint text-danger-ink" : "bg-brand-tint text-brand-ink"}`}>{message.text}</p> : null}
        </div>
        <Modal open={Boolean(pending)} onClose={() => setPending(null)} closeLabel={copy.close} title={pending?.is_sensitive ? copy.sharedConfirmTitle : copy.privateConfirmTitle}>
            {pending ? <div className="space-y-4">
                <p className="break-words text-[15px] font-semibold text-ink [overflow-wrap:anywhere]">{pending.name}</p>
                <p className="text-[15px] leading-relaxed text-ink-2">{pending.is_sensitive ? copy.sharedConfirmBody : copy.privateConfirmBody}</p>
                <div className="flex flex-col gap-2 sm:flex-row-reverse">
                    <button type="button" onClick={() => void apply(pending)} className="ma-press min-h-[52px] w-full rounded-2xl bg-brand px-4 py-3 text-base font-semibold text-white hover:bg-brand-hover">{copy.confirm}</button>
                    <button type="button" onClick={() => setPending(null)} className="ma-press min-h-[52px] w-full rounded-2xl bg-surface-2 px-4 py-3 text-base font-semibold text-ink-2 hover:bg-line-strong">{copy.cancel}</button>
                </div>
            </div> : null}
        </Modal>
    </section>;
}
