"use client";

import { useEffect, useRef } from "react";
import { fetchTurnEvents } from "@/services/chat-api";

export const DRAFT_POLL_MS = 1000;
/** A socket that delivered a chunk this recently is the source of the draft; the poll stays quiet. */
export const SOCKET_FRESH_MS = 3000;
const NO_DEADLINE_CAP_MS = 180_000;
const DEADLINE_GRACE_MS = 5000;
const TERMINAL = new Set(["completed", "failed", "interrupted"]);

interface Options {
    /** Server id of the turn in progress; no poll without it. */
    turnId: string | null;
    deadlineAt?: string | null;
    token: string | null;
    /** When the live socket last delivered a draft event (ms epoch), or 0. */
    lastSocketDraftAt: () => number;
    onDraft: (content: string) => void;
    /** The turn ended (or the endpoint cannot serve it): ask the server for the saved truth once. */
    onSettled: () => void;
}

/**
 * Shows a running turn's draft in a tab the live socket is not feeding. It reads the durable event
 * log with `GET /chat/turns/{id}/events?after_seq=` about once a second, only while the tab is
 * visible, and stops on a terminal status, an unusable endpoint or the turn deadline. The log is
 * the same source every API instance relays from, so this works across instances and after a
 * reload. Draft checkpoints hold the whole text so far; they are pruned only at completion.
 */
export function useTurnDraftPoll({ turnId, deadlineAt, token, lastSocketDraftAt, onDraft, onSettled }: Options) {
    const latest = useRef({ token, lastSocketDraftAt, onDraft, onSettled });
    useEffect(() => { latest.current = { token, lastSocketDraftAt, onDraft, onSettled }; });
    useEffect(() => {
        if (!turnId) return;
        const parsed = deadlineAt ? Date.parse(deadlineAt) : NaN;
        const stopAt = (Number.isFinite(parsed) ? parsed + DEADLINE_GRACE_MS : Date.now() + NO_DEADLINE_CAP_MS);
        let afterSeq = 0;
        let busy = false;
        let stopped = false;
        let failures = 0;
        const stop = () => { stopped = true; window.clearInterval(timer); };
        const tick = async () => {
            if (stopped || busy) return;
            if (Date.now() > stopAt) { stop(); return; }
            const { token: current, lastSocketDraftAt: socketAt } = latest.current;
            if (document.visibilityState !== "visible" || !current) return;
            if (Date.now() - socketAt() < SOCKET_FRESH_MS) return;
            busy = true;
            try {
                const result = await fetchTurnEvents(turnId, afterSeq, current);
                if (stopped) return;
                failures = 0;
                afterSeq = Math.max(afterSeq, result.next_seq);
                const draft = [...result.events].reverse().find((event) => event.type === "draft");
                if (draft?.payload?.content && Date.now() - latest.current.lastSocketDraftAt() >= SOCKET_FRESH_MS) {
                    latest.current.onDraft(draft.payload.content);
                }
                if (TERMINAL.has(result.turn.status) || result.events.some((event) => TERMINAL.has(event.type))) {
                    stop(); latest.current.onSettled();
                }
            } catch {
                // A blip is retried on the next tick; a turn this endpoint cannot serve (not found,
                // worker mode off) fails repeatedly. Then stop: the recover poll over the socket
                // still settles the turn.
                failures += 1;
                if (failures >= 3) { stop(); latest.current.onSettled(); }
            } finally {
                busy = false;
            }
        };
        const timer = window.setInterval(() => { void tick(); }, DRAFT_POLL_MS);
        return () => { stopped = true; window.clearInterval(timer); };
    }, [turnId, deadlineAt]);
}
