"use client";

import { useCallback, useEffect, useState } from "react";
import {
    HiOutlineArrowPath,
    HiOutlineChatBubbleLeftRight,
    HiOutlineEnvelope,
    HiOutlinePaperAirplane,
} from "react-icons/hi2";
import { Badge, Card, Skeleton } from "@/components/ui";
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
        <div className="mx-auto max-w-7xl space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h2 className="text-lg font-semibold text-ink">
                        Operational alerts
                    </h2>
                    <p className="mt-1 text-sm text-muted">
                        Legacy operational notifications, separate from patient conversations.
                    </p>
                </div>
                <button
                    disabled={loading}
                    className="flex items-center gap-2 rounded-lg border border-line px-4 py-2 text-sm font-medium text-ink-2 hover:bg-surface-2"
                    onClick={() => void loadMessages()}
                    type="button"
                >
                    <HiOutlineArrowPath aria-hidden="true" className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                    {loading ? "Refreshing…" : "Refresh"}
                </button>
            </div>

            <section className="grid gap-4 md:grid-cols-3">
                <Card className="flex items-center gap-3 px-5 py-4" padding="sm">
                    <div className="rounded-full bg-ai-tint p-3 text-primary">
                        <HiOutlinePaperAirplane className="h-5 w-5" />
                    </div>
                    <div>
                        <p className="text-sm text-muted">Total sent</p>
                        <p className="text-2xl font-bold text-ink">{messages.length}</p>
                    </div>
                </Card>
                <Card className="flex items-center gap-3 px-5 py-4" padding="sm">
                    <div className="rounded-full bg-ok-tint p-3 text-ok-ink">
                        <HiOutlineChatBubbleLeftRight className="h-5 w-5" />
                    </div>
                    <div>
                        <p className="text-sm text-muted">In-app</p>
                        <p className="text-2xl font-bold text-ink">
                            {messages.filter((m) => m.channel === "in_app").length}
                        </p>
                    </div>
                </Card>
                <Card className="flex items-center gap-3 px-5 py-4" padding="sm">
                    <div className="rounded-full bg-warn-tint p-3 text-warn-ink">
                        <HiOutlineEnvelope className="h-5 w-5" />
                    </div>
                    <div>
                        <p className="text-sm text-muted">Email</p>
                        <p className="text-2xl font-bold text-ink">
                            {messages.filter((m) => m.channel === "email").length}
                        </p>
                    </div>
                </Card>
            </section>

            {error && (
                <div
                    className="rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink"
                    role="alert"
                >
                    {error}
                </div>
            )}

            <Card className="overflow-hidden px-0 py-0" padding="sm">
                <div className="border-b border-line px-6 py-5">
                    <h2 className="text-lg font-semibold text-ink">Operational alert history</h2>
                    <p className="text-sm text-muted">
                        Ordered by most recent. These notifications are not conversation replies.
                    </p>
                </div>

                {loading ? (
                    <div className="space-y-4 px-6 py-6">
                        {Array.from({ length: 3 }).map((_, index) => (
                            <Skeleton className="h-24 w-full" key={index} />
                        ))}
                    </div>
                ) : error && messages.length === 0 ? (
                    <p className="px-6 py-10 text-sm text-ink-2">Alert history is unavailable. Refresh to check for notifications.</p>
                ) : messages.length === 0 ? (
                    <div className="flex h-48 flex-col items-center justify-center gap-3 px-6 py-10 text-center text-muted">
                        <HiOutlineChatBubbleLeftRight className="h-10 w-10 text-slate-300" />
                        <div>
                            <p className="text-base font-semibold text-ink">
                                No operational alerts yet
                            </p>
                            <p className="text-sm">
                                Operational notification history appears here.
                            </p>
                        </div>
                    </div>
                ) : (
                    <div className="divide-y divide-line">
                        {messages.map((msg) => (
                            <div className="px-6 py-5" key={msg.id}>
                                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                                    <div className="space-y-2">
                                        <div className="flex items-center gap-3">
                                            <p className="text-base font-semibold text-ink">
                                                {formatPatientName(msg)}
                                            </p>
                                            <Badge variant={channelVariant(msg.channel)}>
                                                {channelLabel(msg.channel)}
                                            </Badge>
                                        </div>
                                        {msg.subject && (
                                            <p className="text-sm font-medium text-ink-2">
                                                {msg.subject}
                                            </p>
                                        )}
                                        <p className="max-w-3xl break-words text-sm text-ink-2">
                                            {msg.body.length > 200
                                                ? `${msg.body.slice(0, 200)}…`
                                                : msg.body}
                                        </p>
                                        {msg.body.length > 200 ? <details className="max-w-3xl text-sm text-ink-2"><summary className="cursor-pointer py-2 font-medium">Read full alert</summary><p className="whitespace-pre-wrap break-words">{msg.body}</p></details> : null}
                                        <p className="text-xs text-muted">
                                            {new Date(msg.createdAt).toLocaleString()}
                                        </p>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </Card>
        </div>
    );
}
