"use client";

import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store/store";
import { Icon } from "@/components/ui/icons";
import {
    fetchChatConversations,
    todayConversationId,
    type ChatConversationSummary,
} from "@/services/chat-api";

const COPY = {
    "en-US": {
        heading: "Past conversations with Nora",
        today: "Today",
        untitled: "Conversation",
        loadError: "Past conversations could not be loaded.",
        dayTitle: "Conversation from",
        todayTitle: "Today's conversation",
        unfinished: "Reply unfinished",
        replying: "Nora is replying…",
    },
    "es-MX": {
        heading: "Conversaciones anteriores con Nora",
        today: "Hoy",
        untitled: "Conversación",
        loadError: "No se pudieron cargar las conversaciones anteriores.",
        dayTitle: "Conversación del",
        todayTitle: "Conversación de hoy",
        // Draft wording pending LOC-001 bilingual review.
        unfinished: "Respuesta incompleta",
        replying: "Nora está respondiendo…",
    },
} as const;

const SHOWN = 8;

/** Earlier conversations with Nora; choosing one reopens it with its messages. */
export function NoraConversations({
    locale,
    activeSessionId,
    onOpen,
}: {
    locale: string;
    activeSessionId: string;
    onOpen: (sessionId: string) => void;
}) {
    const { accessToken, user } = useSelector((state: RootState) => state.auth);
    const copy = COPY[locale === "es-MX" ? "es-MX" : "en-US"];
    const [conversations, setConversations] = useState<ChatConversationSummary[] | null>(null);
    const [failed, setFailed] = useState(false);

    useEffect(() => {
        if (!accessToken || !user) return;
        let current = true;
        fetchChatConversations(user.id, accessToken)
            .then((rows) => { if (current) { setConversations(rows); setFailed(false); } })
            .catch(() => { if (current) setFailed(true); });
        return () => { current = false; };
    }, [accessToken, user, activeSessionId]);

    const today = todayConversationId();
    const formatter = new Intl.DateTimeFormat(locale, { month: "short", day: "numeric" });
    const rows = (conversations ?? []).slice(0, SHOWN);
    if (failed) return <p className="px-1 text-sm text-muted" role="status">{copy.loadError}</p>;
    if (rows.length === 0) return null;

    return <section className="overflow-hidden rounded-[22px] bg-surface" aria-labelledby="nora-conversations-heading">
        <h2 id="nora-conversations-heading" className="px-[14px] pt-3 pb-1 text-[13px] font-semibold text-muted">{copy.heading}</h2>
        <ul>
            {rows.map((row) => {
                const isToday = row.sessionId === today;
                const when = isToday ? copy.today : formatter.format(new Date(row.updatedAt));
                const title = row.title.trim()
                    || (isToday ? copy.todayTitle
                        : row.sessionId.startsWith("day-") ? `${copy.dayTitle} ${when}` : copy.untitled);
                return <li key={row.sessionId}>
                    <button type="button" onClick={() => onOpen(row.sessionId)}
                        aria-current={row.sessionId === activeSessionId ? "true" : undefined}
                        className="ma-press flex min-h-14 w-full items-center gap-3 px-[14px] py-2.5 text-left hover:bg-[#FBF7F0]">
                        <span aria-hidden="true" className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[13px] bg-surface-2 text-ink-2"><Icon name="chat" className="h-5 w-5" /></span>
                        <span className="min-w-0 flex-1">
                            <span className="block truncate text-[15px] font-medium text-ink">{title}</span>
                            <span className="block text-xs text-muted">{when}</span>
                        </span>
                        {row.needsAttention ? <span className="shrink-0 rounded-full bg-surface-2 px-2.5 py-1 text-xs font-semibold text-ink-2">{row.replyInProgress ? copy.replying : copy.unfinished}</span> : null}
                        <Icon name="chevron" className="h-4 w-4 shrink-0 text-muted" />
                    </button>
                </li>;
            })}
        </ul>
    </section>;
}
