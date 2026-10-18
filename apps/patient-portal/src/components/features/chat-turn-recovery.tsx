import type { RecoverableTurn } from "@/hooks/use-chat-turn-recovery";
import type { Locale } from "@/types";

export function ChatTurnRecovery({ turns, locale, connected, onRetry, onDismiss }: {
    turns: RecoverableTurn[]; locale: Locale; connected: boolean;
    onRetry: (id: string) => void; onDismiss: (id: string) => void;
}) {
    const spanish = locale === "es-MX";
    const processing = turns.some((turn) => turn.status === "processing");
    return <div className="space-y-2" aria-live="polite">
        {turns.map((turn) => <section key={turn.client_message_id} className="rounded-2xl border border-line-strong bg-surface p-3.5 text-sm">
            <p className="font-semibold">{turn.status === "processing"
                ? spanish ? "Nora está preparando tu respuesta" : "Nora is preparing your reply"
                : turn.status === "unknown"
                    ? spanish ? "Comprobando el estado de tu mensaje" : "Checking your message status"
                    : spanish ? "La respuesta quedó incompleta" : "The reply was interrupted"}</p>
            {turn.user_message && <p className="mt-1 line-clamp-2 break-words text-ink-2">{turn.user_message.content}</p>}
            <p className="mt-1 text-ink-2">{turn.failure_code === "action_uncertain"
                ? spanish ? "Es posible que se haya registrado una acción. No la repetiremos automáticamente. Si necesitas ayuda, contacta a tu equipo de atención." : "An action may already have been recorded. We will not repeat it automatically. Contact your care team if you need help."
                : turn.status === "processing"
                    ? spanish ? "Puedes volver a esta conversación. La respuesta se mostrará cuando esté guardada." : "You can return to this conversation. The reply will appear when it is saved."
                    : turn.retryable
                        ? spanish ? "Puedes reintentar el mismo mensaje sin enviarlo dos veces." : "You can retry the same message without sending it twice."
                        : spanish ? "No volveremos a ejecutar este mensaje. Puedes continuar con una pregunta nueva." : "We will not rerun this message. You can continue with a new question."}</p>
            <div className="mt-2 flex flex-wrap gap-2">
                {turn.retryable && <button type="button" className="ma-press min-h-11 rounded-xl bg-brand-tint px-3 font-semibold text-brand-ink disabled:opacity-50" disabled={!connected || processing || turns.some((other) => other.status === "unknown" && other.client_message_id !== turn.client_message_id)} onClick={() => onRetry(turn.client_message_id)}>{spanish ? "Reintentar mensaje" : "Retry message"}</button>}
                {["failed", "interrupted"].includes(turn.status) && <button type="button" className="ma-press min-h-11 rounded-xl px-3 font-medium text-ink-2 disabled:opacity-50" disabled={!connected} onClick={() => onDismiss(turn.client_message_id)}>{spanish ? "Dejar esta respuesta incompleta" : "Leave this reply unfinished"}</button>}
            </div>
        </section>)}
    </div>;
}
