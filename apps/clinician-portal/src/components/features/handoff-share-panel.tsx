"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge, Button, EmptyState, Modal, Skeleton } from "@/components/ui";
import { errorCode } from "@/services/care-team-plans";
import {
    listHandoffShares,
    listShareCandidates,
    revokeHandoffShare,
    shareHandoffSummary,
    type HandoffRecipient,
    type HandoffShare,
} from "@/services/handoff-summaries";

const day = (value: string) => value.slice(0, 10);

/**
 * Side panel on the approved review page: pick a named colleague, see who already has this
 * version and take access back. Only people the server allows are offered; the server decides
 * again when the share is made.
 */
export function HandoffSharePanel({
    onChanged,
    onClose,
    open,
    summaryId,
    version,
}: {
    onChanged: () => void;
    onClose: () => void;
    open: boolean;
    summaryId: string;
    version: number;
}) {
    const [query, setQuery] = useState("");
    const [clinic, setClinic] = useState<string | null>(null);
    const [candidates, setCandidates] = useState<HandoffRecipient[] | null>(null);
    const [shares, setShares] = useState<HandoffShare[] | null>(null);
    const [failed, setFailed] = useState(false);
    const [busy, setBusy] = useState<string | null>(null);
    const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);

    const load = useCallback(async (search: string) => {
        setFailed(false);
        try {
            const [people, current] = await Promise.all([listShareCandidates(summaryId, search), listHandoffShares(summaryId)]);
            setCandidates(people);
            setShares(current);
        } catch {
            setFailed(true);
        }
    }, [summaryId]);

    useEffect(() => {
        if (!open) return;
        const timer = setTimeout(() => void load(query), query ? 250 : 0);
        return () => clearTimeout(timer);
    }, [load, open, query]);

    const active = useMemo(() => (shares ?? []).filter((share) => !share.revoked_at && share.version === version), [shares, version]);
    const activeIds = useMemo(() => new Set(active.map((share) => share.recipient_id)), [active]);
    const clinics = useMemo(() => {
        const seen = new Map<string, string>();
        (candidates ?? []).forEach((person) => person.clinics.forEach((entry) => seen.set(entry.id, entry.name)));
        return [...seen.entries()];
    }, [candidates]);
    const shown = (candidates ?? []).filter((person) => !clinic || person.clinics.some((entry) => entry.id === clinic));

    async function grant(person: HandoffRecipient) {
        setBusy(person.clinician_id);
        setMessage(null);
        try {
            await shareHandoffSummary(summaryId, version, person.clinician_id);
            setMessage({ tone: "ok", text: `Shared version ${version} with Dr. ${person.first_name} ${person.last_name}. They have been notified.` });
            await load(query);
            onChanged();
        } catch (failure) {
            const code = errorCode(failure);
            setMessage({
                tone: "error",
                text: code === "HANDOFF_NOT_APPROVED"
                    ? "Only the approved version can be shared. Reload and approve the current version first."
                    : code === "HANDOFF_RECIPIENT_NOT_ALLOWED"
                        ? "That clinician can no longer receive this summary."
                        : "That did not complete. Nothing was shared. Try again.",
            });
        } finally {
            setBusy(null);
        }
    }

    async function revoke(share: HandoffShare) {
        setBusy(share.id);
        setMessage(null);
        try {
            await revokeHandoffShare(share.id);
            setMessage({ tone: "ok", text: `Access removed for ${share.recipient_name ?? "this clinician"}.` });
            await load(query);
            onChanged();
        } catch {
            setMessage({ tone: "error", text: "Access was not changed. Try again." });
        } finally {
            setBusy(null);
        }
    }

    return (
        <Modal onClose={onClose} open={open} placement="side" title="Share this summary">
            <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-4">
                <p className="text-sm text-ink-2">
                    Version {version} is approved. A colleague you share it with sees only this version, read-only. Sharing does not give them the patient&apos;s record, and you can take access back at any time.
                </p>
                {message ? <p className={`rounded-xl border px-3 py-2 text-sm ${message.tone === "ok" ? "border-ok-line bg-ok-soft text-ok-ink" : "border-risk-line bg-risk-soft text-risk-ink"}`} role={message.tone === "ok" ? "status" : "alert"}>{message.text}</p> : null}

                <section aria-labelledby="share-current">
                    <h3 className="text-[13px] font-semibold text-ink" id="share-current">Shared with</h3>
                    {shares === null && !failed ? <Skeleton className="mt-2 h-12 w-full" /> : null}
                    {shares && active.length === 0 ? <p className="mt-1 text-sm text-muted">Nobody has this version yet.</p> : null}
                    <ul className="mt-2 space-y-2">
                        {active.map((share) => (
                            <li className="flex items-center justify-between gap-3 rounded-xl border border-line bg-surface-2 px-3 py-2" key={share.id}>
                                <span className="min-w-0">
                                    <span className="block [overflow-wrap:anywhere] text-sm font-semibold text-ink">{share.recipient_name}</span>
                                    <span className="block text-xs text-muted">{share.recipient_specialty ? `${share.recipient_specialty} · ` : ""}shared {day(share.shared_at)}</span>
                                </span>
                                <Button aria-label={`Revoke access for ${share.recipient_name}`} disabled={busy !== null} onClick={() => void revoke(share)} size="sm" variant="danger">Revoke</Button>
                            </li>
                        ))}
                    </ul>
                </section>

                <section aria-labelledby="share-pick">
                    <h3 className="text-[13px] font-semibold text-ink" id="share-pick">Choose a colleague</h3>
                    <label className="mt-2 block">
                        <span className="sr-only">Search colleagues</span>
                        <input className="h-10 w-full rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink" maxLength={100} onChange={(event) => setQuery(event.target.value)} placeholder="Search by name, specialty or clinic" type="search" value={query} />
                    </label>
                    {clinics.length > 1 ? (
                        <div aria-label="Filter by clinic" className="mt-2 flex flex-wrap gap-1.5" role="group">
                            <button aria-pressed={clinic === null} className={`min-h-8 rounded-full border px-3 text-xs font-medium ${clinic === null ? "border-primary bg-primary-soft text-primary" : "border-line bg-surface text-ink-2"}`} onClick={() => setClinic(null)} type="button">All clinics</button>
                            {clinics.map(([id, name]) => (
                                <button aria-pressed={clinic === id} className={`min-h-8 rounded-full border px-3 text-xs font-medium [overflow-wrap:anywhere] ${clinic === id ? "border-primary bg-primary-soft text-primary" : "border-line bg-surface text-ink-2"}`} key={id} onClick={() => setClinic(id)} type="button">{name}</button>
                            ))}
                        </div>
                    ) : null}
                    {failed ? <p className="mt-3 text-sm text-risk-ink" role="alert">Colleagues could not be loaded. <button className="font-semibold underline" onClick={() => void load(query)} type="button">Try again</button></p> : null}
                    {candidates === null && !failed ? <Skeleton className="mt-3 h-16 w-full" /> : null}
                    {candidates && shown.length === 0 ? <div className="mt-3"><EmptyState description="Only clinicians linked to this patient, or in your clinic, can receive a summary." title="No matching colleagues" /></div> : null}
                    <ul className="mt-3 space-y-2">
                        {shown.map((person) => (
                            <li className="flex items-center justify-between gap-3 rounded-xl border border-line bg-surface px-3 py-2.5" key={person.clinician_id}>
                                <span className="min-w-0">
                                    <span className="block [overflow-wrap:anywhere] text-sm font-semibold text-ink">Dr. {person.first_name} {person.last_name}</span>
                                    <span className="block [overflow-wrap:anywhere] text-xs text-muted">{person.specialty} · {person.clinics.map((entry) => entry.name).join(", ")}</span>
                                    <span className="block text-xs text-muted">{person.bases.includes("care_team") ? "Treats this patient" : "Member of your clinic"}</span>
                                </span>
                                {activeIds.has(person.clinician_id)
                                    ? <Badge variant="success">Shared</Badge>
                                    : <Button aria-label={`Share with Dr. ${person.first_name} ${person.last_name}`} disabled={busy !== null} onClick={() => void grant(person)} size="sm" variant="primary">{busy === person.clinician_id ? "Sharing…" : "Share"}</Button>}
                            </li>
                        ))}
                    </ul>
                </section>
            </div>
        </Modal>
    );
}
