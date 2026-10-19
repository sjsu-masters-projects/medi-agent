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

export type TurnStatus = RecoverableTurn["status"];

const KNOWN_STATUSES: readonly TurnStatus[] = ["queued", "processing", "unknown", "completed", "failed", "interrupted"];

/** Any status this portal does not recognise is "unknown": in progress, never interrupted. */
export function normalizeTurnStatus(status: unknown): TurnStatus {
    return KNOWN_STATUSES.includes(status as TurnStatus) ? status as TurnStatus : "unknown";
}

/** Queued, processing and unknown are busy: send is disabled, there is no retry, and exactly
 *  one progress indicator is shown. Failed and interrupted need the patient's attention. */
export function isTurnInProgress(status: TurnStatus): boolean {
    return status === "queued" || status === "processing" || status === "unknown";
}

export function isTurnUnfinished(status: TurnStatus): boolean {
    return status === "failed" || status === "interrupted";
}

/** Requests stay in memory, never in browser storage. Saved requests recover from the server. */
export function useChatTurnRecovery(scope: string, socket: RefObject<WebSocket | null>) {
    const requests = useRef(new Map<string, TurnRequest>());
    const blocked = useRef(new Set<string>());
    const sentHere = useRef(new Set<string>());
    const latest = useRef(new Map<string, RecoverableTurn[]>());
    const [byScope, setByScope] = useState<Record<string, RecoverableTurn[]>>({});
    const turns = byScope[scope] ?? [];

    function write(next: RecoverableTurn[]) {
        latest.current.set(scope, next);
        if (next.some((turn) => isTurnInProgress(turn.status))) blocked.current.add(scope);
        else blocked.current.delete(scope);
        setByScope((current) => ({ ...current, [scope]: next }));
    }

    function accept(incoming: ChatTurnApi[], snapshot = false) {
        const rows = incoming.map((row) => ({ ...row, status: normalizeTurnStatus(row.status) })) as RecoverableTurn[];
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

    function send(content: string, language: Locale, documentId: string | null, audioUrl?: string, clientMessageId?: string): boolean {
        if (blocked.current.has(scope) || socket.current?.readyState !== WebSocket.OPEN) return false;
        const request: TurnRequest = { type: "user_message", client_message_id: clientMessageId ?? crypto.randomUUID(),
            content, language, document_id: documentId, audio_url: audioUrl ?? null };
        requests.current.set(`${scope}:${request.client_message_id}`, request);
        sentHere.current.add(`${scope}:${request.client_message_id}`);
        write([...(latest.current.get(scope) ?? []), { client_message_id: request.client_message_id, status: "unknown",
            retryable: true, attempt: 0, document_id: documentId }]);
        try { socket.current.send(JSON.stringify(request)); } catch { /* Preserve the exact retry identity. */ }
        return true;
    }

    function retry(id: string): boolean {
        const turns = latest.current.get(scope) ?? [];
        const turn = turns.find((item) => item.client_message_id === id);
        const request = requests.current.get(`${scope}:${id}`);
        if (!turn?.retryable || !request || turns.some((item) => isTurnInProgress(item.status) && item.client_message_id !== id)
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

    /** This tab sent the turn, so it follows the reply with the typing indicator and draft. */
    const isOwnTurn = (id: string) => sentHere.current.has(`${scope}:${id}`);

    return { turns, accept, isOwnTurn, send, retry, dismiss, reject,
        turnBusy: turns.some((turn) => isTurnInProgress(turn.status)) };
}
