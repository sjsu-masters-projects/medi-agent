import type { RefObject } from "react";
import { getVoiceModeCopy } from "@/content/chat-copy";
import { Icon } from "@/components/ui/icons";
import { ListenBars, ProcessingDots } from "@/components/ui/motion";
import type { VoiceModeSnapshot } from "@/services/live-voice";
import type { Locale } from "@/types";

/** The partial transcript keeps its end: the newest words matter, so older ones are cut. */
export function tailTranscript(text: string, max = 140): string {
    const clean = text.trim();
    return clean.length > max ? `…${clean.slice(clean.length - max).trimStart()}` : clean;
}

/**
 * Hands-free conversation panel. It replaces the composer while voice mode is on, so the
 * thread above keeps showing the transcript as it becomes messages. The state is carried by
 * text and icon, with motion as an extra: reduced-motion users lose nothing.
 */
export function VoiceModePanel({ snapshot, locale, remainingSeconds, ringRef, onTogglePause, onEnd, onRetry, onUseText }: {
    snapshot: VoiceModeSnapshot;
    locale: Locale;
    remainingSeconds: number | null;
    ringRef: RefObject<HTMLDivElement | null>;
    onTogglePause: () => void;
    onEnd: () => void;
    onRetry: () => void;
    onUseText: () => void;
}) {
    const copy = getVoiceModeCopy(locale);
    const { state, paused, error, notice, guidance, partial } = snapshot;

    if (state === "error" && error) {
        return <section aria-label={copy.panel} className="shrink-0 -mx-4 mt-auto bg-background/95 px-4 pt-3 pb-[calc(env(safe-area-inset-bottom)+12px)] backdrop-blur-md">
            <div role="alert" className="rounded-2xl bg-danger-tint p-3.5 text-sm text-danger-ink">
                <p className="break-words">{copy.errors[error]}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                    <button type="button" className="ma-press min-h-11 rounded-xl bg-surface px-4 font-semibold text-ink" onClick={onRetry}>{copy.tryAgain}</button>
                    <button type="button" className="ma-press min-h-11 rounded-xl px-4 font-semibold text-danger-ink hover:bg-surface/60" onClick={onUseText}>{copy.useText}</button>
                </div>
            </div>
        </section>;
    }

    const statusKey = paused ? "paused" : state === "ended" ? "connecting" : state === "error" ? "connecting" : state;
    const status = copy.status[statusKey];
    const live = statusKey === "listening" || statusKey === "hearing";
    const minutes = remainingSeconds === null ? 0 : Math.floor(remainingSeconds / 60);
    const seconds = remainingSeconds === null ? 0 : remainingSeconds % 60;

    return <section aria-label={copy.panel} data-voice-state={statusKey} className="shrink-0 -mx-4 mt-auto space-y-3 bg-background/95 px-4 pt-3 pb-[calc(env(safe-area-inset-bottom)+12px)] backdrop-blur-md">
        {guidance && <p role="alert" className="whitespace-pre-wrap break-words rounded-2xl border border-danger-ink/20 bg-danger-tint p-3.5 text-sm font-medium text-danger-ink">{guidance}</p>}
        {notice && <p role="status" className="break-words rounded-2xl bg-surface px-3.5 py-2.5 text-[13px] text-ink-2">{copy.notices[notice === "interrupted_by_limit" ? "reply_failed" : notice]}</p>}
        <div className="flex flex-col items-center gap-2">
            <div className="relative h-24 w-24" aria-hidden="true">
                <div ref={ringRef} className={`ma-voice-ring absolute inset-0 rounded-full ${live ? "bg-brand/20" : statusKey === "speaking" ? "bg-gold/25" : "bg-line-strong/60"}`} />
                <div className={`absolute inset-3 flex items-center justify-center rounded-full text-white ${statusKey === "paused" ? "bg-surface-2 text-ink-2" : statusKey === "speaking" ? "bg-brand-deep text-gold" : "bg-brand"}`}>
                    {statusKey === "thinking" ? <ProcessingDots className="bg-white" />
                        : statusKey === "speaking" ? <span className="scale-150"><ListenBars /></span>
                            : <Icon name="mic" className="h-8 w-8" />}
                </div>
            </div>
            <p aria-live="polite" className="max-w-full break-words text-center text-[15px] font-medium text-ink">{status}</p>
            {partial && statusKey !== "paused" && <p aria-label={copy.heard} className="line-clamp-2 max-w-full break-words text-center text-sm italic text-muted">{tailTranscript(partial)}</p>}
            {remainingSeconds !== null && <p className="text-xs text-muted">{copy.remaining(minutes, seconds)}</p>}
        </div>
        <div className="flex gap-2">
            <button type="button" aria-pressed={paused} className="ma-press min-h-11 flex-1 rounded-xl bg-surface px-3 text-sm font-semibold text-ink-2 hover:bg-surface-2" onClick={onTogglePause}>{paused ? copy.resume : copy.pause}</button>
            <button type="button" className="ma-press min-h-11 flex-1 rounded-xl border border-danger-ink/30 bg-danger-tint px-3 text-sm font-semibold text-danger-ink hover:bg-danger-tint/70" onClick={onEnd}>{copy.end}</button>
        </div>
    </section>;
}
