"use client";

import { useRef, useState, type RefObject } from "react";
import type { ChatTurnApi } from "@/services/chat-api";
import type { Locale } from "@/types";

interface TurnRequest {
    type: "user_message";
    client_message_id: string;
    content: string;
    language: Locale;
    document_id: string | null;
    audio_url: string | null;
}

export interface RecoverableTurn extends Omit<ChatTurnApi, "status"> {
    status: ChatTurnApi["status"] | "unknown";
}

/** Requests stay in memory, never in browser storage. Saved requests recover from the server. */
export function useChatTurnRecovery(scope: string, socket: RefObject<WebSocket | null>) {
    const requests = useRef(new Map<string, TurnRequest>());
    const blocked = useRef(new Set<string>());
    const latest = useRef(new Map<string, RecoverableTurn[]>());
    const [byScope, setByScope] = useState<Record<string, RecoverableTurn[]>>({});
    const turns = byScope[scope] ?? [];

    function write(next: RecoverableTurn[]) {
        latest.current.set(scope, next);
        if (next.some((turn) => turn.status === "processing" || turn.status === "unknown")) blocked.current.add(scope);
        else blocked.current.delete(scope);
        setByScope((current) => ({ ...current, [scope]: next }));
    }

    function accept(rows: ChatTurnApi[], snapshot = false) {
        for (const row of rows) {
            if (row.user_message) requests.current.set(`${scope}:${row.client_message_id}`, {
                type: "user_message", client_message_id: row.client_message_id,
                content: row.user_message.content, language: row.user_message.language,
                document_id: row.document_id, audio_url: row.user_message.audio_url ?? null,
            });
            if (row.status === "completed") requests.current.delete(`${scope}:${row.client_message_id}`);
        }
        // A request without an acknowledgement may still be reaching the server.
        // Never drop it merely because one recovery snapshot does not contain it yet.
        const current = latest.current.get(scope) ?? [];
        const retained = snapshot ? current.filter((turn) => turn.status === "unknown") : current;
        const merged = new Map(retained.map((turn) => [turn.client_message_id, turn]));
        rows.forEach((row) => row.status === "completed"
            ? merged.delete(row.client_message_id) : merged.set(row.client_message_id, row));
        write([...merged.values()]);
    }

    function send(content: string, language: Locale, documentId: string | null, audioUrl?: string): boolean {
        if (blocked.current.has(scope) || socket.current?.readyState !== WebSocket.OPEN) return false;
        const request: TurnRequest = { type: "user_message", client_message_id: crypto.randomUUID(),
            content, language, document_id: documentId, audio_url: audioUrl ?? null };
        requests.current.set(`${scope}:${request.client_message_id}`, request);
        write([...(latest.current.get(scope) ?? []), { client_message_id: request.client_message_id, status: "unknown",
            retryable: true, attempt: 0, document_id: documentId }]);
        try { socket.current.send(JSON.stringify(request)); } catch { /* Preserve the exact retry identity. */ }
        return true;
    }

    function retry(id: string): boolean {
        const turns = latest.current.get(scope) ?? [];
        const turn = turns.find((item) => item.client_message_id === id);
        const request = requests.current.get(`${scope}:${id}`);
        if (!turn?.retryable || !request || turns.some((item) => item.status === "processing" || (item.status === "unknown" && item.client_message_id !== id))
            || socket.current?.readyState !== WebSocket.OPEN) return false;
        write(turns.map((item) => item.client_message_id === id ? { ...item, status: "unknown" } : item));
        try { socket.current.send(JSON.stringify(request)); } catch { /* Recover or retry the same request. */ }
        return true;
    }

    function dismiss(id: string) {
        const turns = latest.current.get(scope) ?? [];
        const turn = turns.find((item) => item.client_message_id === id);
        if (!turn || !["failed", "interrupted"].includes(turn.status)
            || socket.current?.readyState !== WebSocket.OPEN) return;
        socket.current.send(JSON.stringify({ type: "dismiss_turn", client_message_id: id }));
    }

    function reject(id: string): string | undefined {
        const request = requests.current.get(`${scope}:${id}`);
        requests.current.delete(`${scope}:${id}`);
        // A rejected claim performed no work. The server snapshot retains any older
        // saved attempt, while an unsaved request returns to the editable composer.
        write((latest.current.get(scope) ?? []).filter((turn) => turn.client_message_id !== id));
        return request?.content;
    }

    return { turns, accept, send, retry, dismiss, reject,
        turnBusy: turns.some((turn) => turn.status === "processing" || turn.status === "unknown") };
}
