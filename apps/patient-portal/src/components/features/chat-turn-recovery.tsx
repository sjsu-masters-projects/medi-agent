import { isTurnInProgress, type RecoverableTurn } from "@/hooks/use-chat-turn-recovery";
import type { Locale } from "@/types";
import { getChatRecoveryCopy } from "@/content/chat-copy";

/**
 * Failed and interrupted replies, rendered inline at the bottom of the thread. A turn in progress
 * (queued, processing or not yet acknowledged) is never shown here: the thread shows the typing
 * bubble or the streaming draft for it, the same in every tab. "Interrupted" is shown only for a
 * turn the server saved as failed or interrupted, never because a socket closed.
 */
export function ChatTurnRecovery({ turns, locale, connected, onRetry, onDismiss }: {
    turns: RecoverableTurn[]; locale: Locale; connected: boolean;
    onRetry: (id: string) => void; onDismiss: (id: string) => void;
}) {
    const copy = getChatRecoveryCopy(locale);
    const busy = turns.some((turn) => isTurnInProgress(turn.status));
    return <div className="space-y-2 empty:hidden" aria-live="polite">
        {turns.filter((turn) => !isTurnInProgress(turn.status)).map((turn) => {
          const retryBlocked = busy;
          const reason = !connected ? copy.reconnectBeforeRetry : retryBlocked ? copy.waitBeforeRetry : null;
          const reasonId = `retry-reason-${turn.client_message_id}`;
          return <section key={turn.client_message_id} className="rounded-2xl border border-line-strong bg-surface p-3.5 text-sm">
            {turn.safety_guidance && <p role="alert" className="mb-3 whitespace-pre-wrap rounded-xl bg-danger-tint p-3 font-medium text-danger-ink">{turn.safety_guidance}</p>}
            <p className="font-semibold">{copy.interrupted}</p>
            {turn.user_message && <p className="mt-1 line-clamp-2 break-words text-ink-2">{turn.user_message.content}</p>}
            <p className="mt-1 text-ink-2">{turn.failure_code === "action_uncertain"
                ? copy.uncertain
                : turn.failure_code === "reply_unavailable"
                    ? copy.replyUnavailable
                    : turn.retryable
                        ? copy.safeRetry : copy.noRetry}</p>
            {turn.retryable && reason && <p id={reasonId} className="mt-2 text-ink-2">{reason}</p>}
            <div className="mt-2 flex flex-wrap gap-2">
                {turn.retryable && <button type="button" className="ma-press min-h-11 rounded-xl bg-brand-tint px-3 font-semibold text-brand-ink disabled:opacity-50" aria-describedby={reason ? reasonId : undefined} disabled={!connected || retryBlocked} onClick={() => onRetry(turn.client_message_id)}>{copy.retry}</button>}
                {["failed", "interrupted"].includes(turn.status) && <button type="button" className="ma-press min-h-11 rounded-xl px-3 font-medium text-ink-2 disabled:opacity-50" disabled={!connected} onClick={() => onDismiss(turn.client_message_id)}>{copy.leaveUnfinished}</button>}
            </div>
        </section>; })}
    </div>;
}
