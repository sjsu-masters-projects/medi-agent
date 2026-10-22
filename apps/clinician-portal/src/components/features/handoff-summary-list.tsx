"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CareTeamSelect, useCareTeamChoice } from "@/components/features/care-team-select";
import { Badge, Button, EmptyState, ErrorState, Skeleton } from "@/components/ui";
import {
    createHandoffSummary,
    listHandoffSummaries,
    type HandoffHeader,
    type HandoffPurpose,
} from "@/services/handoff-summaries";

const PURPOSES: Array<{ value: HandoffPurpose; label: string }> = [
    { value: "colleague", label: "A colleague" },
    { value: "care_team", label: "Another care team" },
    { value: "transition", label: "A transition of care" },
];

function when(value: string): string {
    return value.slice(0, 10);
}

/** My handoff summaries for one patient, and the form that starts a new draft. */
export function HandoffSummaryList({ patientId }: { patientId: string }) {
    const router = useRouter();
    const careTeam = useCareTeamChoice(patientId);
    const [items, setItems] = useState<HandoffHeader[] | null>(null);
    const [failed, setFailed] = useState(false);
    const [purpose, setPurpose] = useState<HandoffPurpose>("colleague");
    const [recipient, setRecipient] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        setFailed(false);
        try {
            setItems(await listHandoffSummaries(patientId));
        } catch {
            setFailed(true);
        }
    }, [patientId]);

    useEffect(() => {
        void load();
    }, [load]);

    async function create() {
        if (careTeam.missing) {
            setError("Choose which care team this summary belongs to.");
            return;
        }
        setBusy(true);
        setError(null);
        try {
            const created = await createHandoffSummary(patientId, {
                purpose,
                recipient_label: recipient.trim() || undefined,
                care_team_id: careTeam.careTeamId,
            });
            router.push(`/patients/${encodeURIComponent(patientId)}/handoff/${encodeURIComponent(created.id)}`);
        } catch (failure) {
            if (!careTeam.handleError(failure)) {
                setError("The summary could not be built. Nothing was saved. Try again.");
            } else {
                setError("Choose which care team this summary belongs to.");
            }
        } finally {
            setBusy(false);
        }
    }

    return (
        <div className="space-y-5">
            <section aria-labelledby="new-handoff" className="rounded-2xl border border-line bg-surface p-5 shadow-[var(--shadow-card)]">
                <h2 className="text-[15px] font-semibold text-ink" id="new-handoff">Start a handoff summary</h2>
                <p className="mt-1 text-sm text-muted">
                    The draft is assembled from records you can see. You review, edit and approve it before it can be exported.
                </p>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <label className="block">
                        <span className="mb-1.5 block text-[13px] font-medium text-ink-2">Handoff for</span>
                        <select className="h-10 w-full rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink" onChange={(event) => setPurpose(event.target.value as HandoffPurpose)} value={purpose}>
                            {PURPOSES.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                        </select>
                    </label>
                    <label className="block">
                        <span className="mb-1.5 block text-[13px] font-medium text-ink-2">Recipient (optional)</span>
                        <input className="h-10 w-full rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink" maxLength={200} onChange={(event) => setRecipient(event.target.value)} placeholder="Name or team" value={recipient} />
                    </label>
                </div>
                <CareTeamSelect className="mt-3" onChange={careTeam.setValue} options={careTeam.options} required={careTeam.required} showRequired={Boolean(error)} value={careTeam.value} />
                {error ? <p className="mt-3 text-sm font-medium text-risk-ink" role="alert">{error}</p> : null}
                <Button className="mt-4" disabled={busy} onClick={() => void create()}>{busy ? "Building draft…" : "Create draft"}</Button>
            </section>

            <section aria-labelledby="my-handoffs" className="space-y-3">
                <h2 className="text-[15px] font-semibold text-ink" id="my-handoffs">Your handoff summaries</h2>
                {failed ? <ErrorState description="Your summaries could not be loaded." onRetry={() => void load()} title="Unable to load summaries" /> : null}
                {!failed && items === null ? <div aria-label="Loading summaries" role="status"><Skeleton className="h-16 w-full" /></div> : null}
                {items && items.length === 0 ? <EmptyState description="Start one above when you hand this patient to someone." title="No handoff summaries yet" /> : null}
                {items && items.length > 0 ? (
                    <ul className="space-y-2">
                        {items.map((item) => (
                            <li key={item.id}>
                                <Link className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-surface px-4 py-3 hover:bg-surface-2" href={`/patients/${encodeURIComponent(patientId)}/handoff/${encodeURIComponent(item.id)}`}>
                                    <span className="min-w-0">
                                        <span className="block [overflow-wrap:anywhere] text-sm font-semibold text-ink">{item.title}</span>
                                        <span className="block text-xs text-muted">Version {item.current_version} · updated {when(item.updated_at)}{item.recipient_label ? ` · for ${item.recipient_label}` : ""}</span>
                                    </span>
                                    <Badge variant={item.status === "approved" ? "success" : "neutral"}>{item.status === "approved" ? "Approved" : "Draft"}</Badge>
                                </Link>
                            </li>
                        ))}
                    </ul>
                ) : null}
            </section>
        </div>
    );
}
