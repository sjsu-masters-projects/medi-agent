"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, Card, Skeleton } from "@/components/ui";
import { Icon, type IconName } from "@/components/ui/icons";
import { fetchAllSentMessages } from "@/services/clinicians";
import type { ClinicianMessageInboxItem } from "@/services/clinicians";

function channelLabel(channel: string): string {
    return channel === "email" ? "Email" : "In-app";
}

function channelVariant(channel: string): "info" | "neutral" {
    return channel === "email" ? "info" : "neutral";
}

function formatPatientName(msg: ClinicianMessageInboxItem): string {
    const first = msg.patientFirstName ?? "";
    const last = msg.patientLastName ?? "";
    const full = `${first} ${last}`.trim();
    return full || "Unknown patient";
}

function StatTile({ icon, label, value }: { icon: IconName; label: string; value: number }) {
    return (
        <Card className="flex items-center gap-3" padding="md">
            <span aria-hidden="true" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-sunken text-ink-2">
                <Icon name={icon} className="h-4 w-4" />
            </span>
            <div>
                <p className="text-[13px] text-muted">{label}</p>
                <p className="font-mono text-[28px] font-medium leading-tight text-ink">{value}</p>
            </div>
        </Card>
    );
}

export function OperationalAlerts() {
    const [messages, setMessages] = useState<ClinicianMessageInboxItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const loadMessages = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const result = await fetchAllSentMessages();
            setMessages(result);
        } catch (loadError) {
            setError(
                loadError instanceof Error
                    ? loadError.message
                    : "Unable to load messages.",
            );
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        void loadMessages();
    }, [loadMessages]);

    return (
        <div className="space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h2 className="text-[17px] font-semibold text-ink">
                        Legacy sent-message archive
                    </h2>
                    <p className="mt-1 text-sm text-muted">
                        Earlier operational records and human messages, retained as history rather than active work.
                    </p>
                </div>
                <button
                    disabled={loading}
                    className="ma-press inline-flex h-[34px] items-center gap-2 rounded-[9px] border border-line-strong bg-surface px-4 text-[13px] font-medium text-ink-2 hover:bg-surface-2 hover:text-ink disabled:cursor-not-allowed disabled:text-[#94A3B8]"
                    onClick={() => void loadMessages()}
                    type="button"
                >
                    <Icon aria-hidden="true" name="refresh" className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                    {loading ? "Refreshing…" : "Refresh"}
                </button>
            </div>

            <section className="grid gap-4 md:grid-cols-3">
                <StatTile icon="send" label="Total sent" value={messages.length} />
                <StatTile icon="chat" label="In-app" value={messages.filter((m) => m.channel === "in_app").length} />
                <StatTile icon="inbox" label="Email" value={messages.filter((m) => m.channel === "email").length} />
            </section>

            {error && (
                <div
                    className="flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink"
                    role="alert"
                >
                    <Icon aria-hidden="true" name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
                    <span>{error}</span>
                </div>
            )}

            <Card className="overflow-hidden" padding="none">
                <div className="flex items-center gap-3 border-b border-line px-5 py-4">
                    <span aria-hidden="true" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-sunken text-ink-2">
                        <Icon name="history" className="h-4 w-4" />
                    </span>
                    <div className="min-w-0">
                        <h2 className="text-[15px] font-semibold text-ink">Earlier sent records</h2>
                        <p className="mt-0.5 text-[13px] text-muted">
                            Ordered by most recent. Historical urgency labels do not create new clinical alerts or current review tasks.
                        </p>
                    </div>
                </div>

                {loading ? (
                    <div className="space-y-4 px-[22px] py-5">
                        {Array.from({ length: 3 }).map((_, index) => (
                            <Skeleton className="h-24 w-full" key={index} />
                        ))}
                    </div>
                ) : error && messages.length === 0 ? (
                    <p className="px-[22px] py-10 text-sm text-ink-2">Sent-message history is unavailable. Refresh to check for earlier records.</p>
                ) : messages.length === 0 ? (
                    <div className="flex flex-col items-center justify-center gap-3 px-6 py-12 text-center">
                        <span aria-hidden="true" className="flex h-12 w-12 items-center justify-center rounded-2xl bg-sunken text-muted">
                            <Icon name="chat" className="h-5 w-5" />
                        </span>
                        <div>
                            <p className="text-[15px] font-semibold text-ink">
                                No legacy sent records
                            </p>
                            <p className="mt-1 text-sm text-muted">
                                Earlier operational records and human messages appear here when available.
                            </p>
                        </div>
                    </div>
                ) : (
                    <div className="divide-y divide-line">
                        {messages.map((msg) => (
                            <div className="px-[22px] py-4 transition-colors hover:bg-[rgba(100,116,139,.05)]" key={msg.id}>
                                <div className="space-y-2">
                                    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
                                        <div className="flex min-w-0 flex-wrap items-center gap-2.5">
                                            <p className="text-[15px] font-semibold text-ink">
                                                {formatPatientName(msg)}
                                            </p>
                                            <Badge variant={channelVariant(msg.channel)}>
                                                {channelLabel(msg.channel)}
                                            </Badge>
                                        </div>
                                        <p className="font-mono text-xs text-muted">
                                            {new Date(msg.createdAt).toLocaleString()}
                                        </p>
                                    </div>
                                    {msg.subject && (
                                        <p className="text-sm font-medium text-ink-2">
                                            {msg.subject}
                                        </p>
                                    )}
                                    <p className="max-w-[80ch] break-words text-sm text-ink-2">
                                        {msg.body.length > 200
                                            ? `${msg.body.slice(0, 200)}…`
                                            : msg.body}
                                    </p>
                                    {msg.body.length > 200 ? <details className="ma-disclosure max-w-[80ch] text-sm text-ink-2"><summary className="min-h-9 cursor-pointer py-1.5 text-[13px] font-medium text-primary">Read full record</summary><p className="whitespace-pre-wrap break-words pt-1">{msg.body}</p></details> : null}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </Card>
        </div>
    );
}
