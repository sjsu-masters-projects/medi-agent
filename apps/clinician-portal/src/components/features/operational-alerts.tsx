"use client";

import { useCallback, useEffect, useState } from "react";
import { Skeleton } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { fetchAllSentMessages } from "@/services/clinicians";
import type { ClinicianMessageInboxItem } from "@/services/clinicians";

const ESCALATION_SUBJECT = "Urgent patient chat escalation";
const ESCALATION_PREFIX = "Chat escalation flagged (";

function patientName(msg: ClinicianMessageInboxItem): string {
    return `${msg.patientFirstName ?? ""} ${msg.patientLastName ?? ""}`.trim() || "Unknown patient";
}

/** Saved system escalation notices carry internal identifiers; show only what they were. */
function escalationUrgency(msg: ClinicianMessageInboxItem): string | null {
    if (msg.subject !== ESCALATION_SUBJECT || !msg.body.startsWith(ESCALATION_PREFIX)) return null;
    const label = msg.body.slice(ESCALATION_PREFIX.length).split(/[/)]/)[0]?.trim();
    return label || "flagged";
}

function shortDate(iso: string): { short: string; full: string } {
    const when = new Date(iso);
    return {
        short: when.toLocaleDateString("en-US", { month: "short", day: "numeric" }),
        full: when.toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" }),
    };
}

/**
 * One-way messages and system escalation notices saved before two-way conversations.
 * History only: nothing here is active work, and old urgency labels create no alerts.
 */
export function EarlierMessages() {
    const [messages, setMessages] = useState<ClinicianMessageInboxItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const load = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            setMessages(await fetchAllSentMessages());
        } catch (loadError) {
            setError(loadError instanceof Error ? loadError.message : "Unable to load messages.");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => { void load(); }, [load]);

    return (
        <details className="ma-disclosure overflow-hidden rounded-2xl border border-line bg-surface">
            <summary className="flex min-h-12 cursor-pointer items-center gap-3 px-4 py-3">
                <span aria-hidden="true" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-sunken text-ink-2">
                    <Icon name="history" className="h-4 w-4" />
                </span>
                <span className="min-w-0 flex-1">
                    <span className="block text-sm font-semibold text-ink">
                        Earlier messages{loading ? "" : ` (${messages.length})`}
                    </span>
                    <span className="block text-xs text-muted">Sent before conversations. History only, not active work.</span>
                    {error && <span role="alert" className="mt-0.5 block text-xs text-risk-ink">{error}</span>}
                </span>
                <Icon aria-hidden="true" name="chevronDown" className="h-4 w-4 shrink-0 text-muted" />
            </summary>
            <div className="border-t border-line">
                <div className="flex justify-end px-4 pt-2">
                    <button
                        type="button"
                        aria-label="Refresh earlier messages"
                        title="Refresh"
                        disabled={loading}
                        onClick={() => void load()}
                        className="ma-press flex h-8 w-8 items-center justify-center rounded-lg text-ink-2 hover:bg-surface-2 disabled:opacity-50"
                    >
                        <Icon aria-hidden="true" name="refresh" className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                    </button>
                </div>
                {loading ? (
                    <div className="space-y-3 px-4 pb-4">
                        {Array.from({ length: 2 }).map((_, index) => <Skeleton className="h-12 w-full" key={index} />)}
                    </div>
                ) : messages.length === 0 && !error ? (
                    <p className="px-4 pb-4 text-sm text-muted">No earlier messages.</p>
                ) : (
                    <ul className="divide-y divide-line">
                        {messages.map((msg) => {
                            const urgency = escalationUrgency(msg);
                            const date = shortDate(msg.createdAt);
                            return (
                                <li key={msg.id} className="flex gap-3 px-4 py-3">
                                    <span aria-hidden="true" className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${urgency ? "bg-risk-tint text-risk-ink" : "bg-surface-2 text-ink-2"}`}>
                                        <Icon name={urgency ? "shield" : msg.channel === "email" ? "inbox" : "chat"} className="h-4 w-4" />
                                    </span>
                                    <div className="min-w-0 flex-1 [overflow-wrap:anywhere]">
                                        <div className="flex items-start gap-2">
                                            <p className="min-w-0 flex-1 text-sm font-semibold text-ink">{patientName(msg)}</p>
                                            <time dateTime={msg.createdAt} title={date.full} aria-label={date.full} className="shrink-0 font-mono text-xs text-muted">{date.short}</time>
                                        </div>
                                        {urgency ? (
                                            <p className="text-[13px] text-ink-2">Chat escalation · {urgency} <span className="text-muted">(automatic notice, not a review task)</span></p>
                                        ) : (
                                            <>
                                                {msg.subject && <p className="text-[13px] font-medium text-ink-2">{msg.subject}</p>}
                                                <p className="line-clamp-2 whitespace-pre-wrap text-[13px] text-ink-2">{msg.body}</p>
                                                {msg.channel === "email" && <p className="text-xs text-muted">Sent by email</p>}
                                            </>
                                        )}
                                    </div>
                                </li>
                            );
                        })}
                    </ul>
                )}
            </div>
        </details>
    );
}
