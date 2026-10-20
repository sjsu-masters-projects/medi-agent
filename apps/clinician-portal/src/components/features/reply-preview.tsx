"use client";

import { useCallback, useRef, useState } from "react";
import { Icon } from "@/components/ui/icons";
import { TranslationInfo } from "@/components/ui/translation-note";
import type { ConfirmedTranslation, ConversationPreviewResult } from "@/types/care-conversations";

/**
 * LOC-003 decision 3: the clinician confirms the Spanish a patient will receive, before
 * sending, by reading an English back-translation of it.
 *
 * A clinician writes English. The patient reads their own language. Sending without showing
 * what the patient will actually read means nobody ever checked it. So:
 *
 * - the preview shows the patient-facing wording and an English back-translation of exactly
 *   that wording, plus the guard result;
 * - the clinician ticks a box to confirm, and the confirmed wording is what gets stored, so
 *   the patient reads the text that was approved rather than a fresh translation;
 * - a translation that failed its guard is never offered for confirmation. The reply goes in
 *   English instead, and the clinician is told why.
 *
 * Nothing here blocks typing. The preview is requested when the clinician asks for it, and a
 * patient who reads English needs none of it.
 */

export type PreviewState =
    | { kind: "idle" }
    | { kind: "loading" }
    | { kind: "error" }
    | { kind: "ready"; result: ConversationPreviewResult; body: string };

/** The confirmed wording to send, or null when there is nothing to confirm or it is unconfirmed. */
export function confirmedTranslationFor(
    state: PreviewState,
    body: string,
    confirmed: boolean,
): ConfirmedTranslation | null {
    if (state.kind !== "ready" || !confirmed) return null;
    const { result } = state;
    // Only wording that is current, needed and passed its guard may be sent as confirmed.
    if (state.body !== body.trim() || !result.needed || !result.translation) return null;
    if (result.guard_passed !== true) return null;
    return { text: result.translation, locale: result.target_locale, model_id: result.model_id };
}

/** Why sending is still blocked, or null when it is not. */
export function sendBlocker(
    state: PreviewState,
    body: string,
    confirmed: boolean,
): string | null {
    const text = body.trim();
    if (!text) return null;
    if (state.kind === "idle") return "Preview what the patient will receive before sending.";
    if (state.kind === "loading") return "Preparing the patient's wording…";
    // A failed preview must not lock the clinician out of messaging. Decision 3's rule for an
    // unavailable translation is to deliver the English with a note, not to refuse the reply.
    if (state.kind === "error") return null;
    if (state.body !== text) return "Your message changed. Preview it again.";
    if (!state.result.needed) return null; // the patient reads the language you wrote in
    if (state.result.guard_passed !== true) return null; // sent in English instead, on purpose
    if (!confirmed) return "Confirm the wording the patient will receive.";
    return null;
}

const LOCALE_NAME: Record<string, string> = {
    "en-US": "English (US)",
    "es-MX": "Español (México)",
};

export function ReplyPreview({
    body,
    state,
    confirmed,
    onPreview,
    onConfirm,
    disabled = false,
}: {
    body: string;
    state: PreviewState;
    confirmed: boolean;
    onPreview: () => void;
    onConfirm: (value: boolean) => void;
    disabled?: boolean;
}) {
    const text = body.trim();
    if (!text) return null;

    const stale = state.kind === "ready" && state.body !== text;
    const result = state.kind === "ready" ? state.result : null;
    const language = LOCALE_NAME[result?.target_locale ?? ""] ?? result?.target_locale ?? "";

    return (
        <section
            aria-label="What the patient will receive"
            className="space-y-2 rounded-xl border border-line bg-surface-2 p-3"
        >
            <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="flex items-center gap-1.5 text-[13px] font-semibold text-ink">
                    <Icon aria-hidden="true" className="h-3.5 w-3.5 text-muted" name="globe" />
                    What the patient will receive
                </p>
                <button
                    className="ma-press h-7 rounded-md px-2 text-[11px] font-semibold text-primary hover:bg-primary-tint disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={disabled || state.kind === "loading"}
                    onClick={onPreview}
                    type="button"
                >
                    {state.kind === "idle" ? "Preview" : "Check again"}
                </button>
            </div>

            <div aria-live="polite" className="space-y-2" role="status">
                {state.kind === "loading" ? (
                    <p className="text-xs text-muted">Preparing the patient&apos;s wording…</p>
                ) : null}
                {state.kind === "error" ? (
                    <p className="flex flex-wrap items-center gap-2 text-xs text-warn-ink">
                        Could not prepare the patient&apos;s wording. You can still send this in
                        English, and the patient is told a translation was unavailable.
                        <button
                            className="font-semibold underline underline-offset-2"
                            onClick={onPreview}
                            type="button"
                        >
                            Retry
                        </button>
                    </p>
                ) : null}
                {stale ? (
                    <p className="text-[11px] font-medium text-warn-ink">
                        Your message changed since this preview. Check it again.
                    </p>
                ) : null}

                {/* Nothing to translate: the patient reads the language you wrote in. */}
                {result && !result.needed && !stale ? (
                    <p className="text-xs text-ink-2">
                        This patient reads {language}, so your message is sent as written.
                    </p>
                ) : null}

                {/* The guard rejected the translation: the reply goes in English, and we say so. */}
                {result?.needed && result.guard_passed === false && !stale ? (
                    <p className="flex items-start gap-2 rounded-lg border border-warn-line bg-warn-soft px-3 py-2 text-xs text-warn-ink">
                        <Icon aria-hidden="true" className="mt-px h-3.5 w-3.5 shrink-0" name="alert" />
                        <span>
                            The automatic translation changed a number, a negation or a medication
                            name, so it will not be used. Your message is delivered in English with
                            a short note that a translation was unavailable.
                        </span>
                    </p>
                ) : null}

                {/* The model failed outright: no preview, and the reply goes in English. */}
                {result?.needed && result.guard_passed === null && !result.translation && !stale ? (
                    <p className="flex items-start gap-2 rounded-lg border border-warn-line bg-warn-soft px-3 py-2 text-xs text-warn-ink">
                        <Icon aria-hidden="true" className="mt-px h-3.5 w-3.5 shrink-0" name="alert" />
                        <span>
                            A translation is unavailable right now. You can send this in English, or
                            check again in a moment.
                        </span>
                    </p>
                ) : null}

                {result?.needed && result.translation && result.guard_passed === true && !stale ? (
                    <>
                        <div className="rounded-lg border border-line bg-surface p-3">
                            <p className="flex flex-wrap items-center gap-1.5 text-[11px] font-semibold text-muted">
                                {language}
                                <TranslationInfo
                                    detail={
                                        <p>
                                            Compare the back-translation below with what you wrote.
                                            If they say the same thing, the wording is faithful.
                                        </p>
                                    }
                                    modelId={result.model_id}
                                />
                            </p>
                            <p
                                className="mt-1 whitespace-pre-wrap break-words text-sm text-ink"
                                lang={result.target_locale}
                            >
                                {result.translation}
                            </p>
                        </div>

                        {result.back_translation ? (
                            <div className="rounded-lg border border-line bg-surface p-3">
                                <p className="flex items-center gap-1.5 text-[11px] font-semibold text-muted">
                                    <Icon aria-hidden="true" className="h-3 w-3 text-ai-ink" name="spark" />
                                    English back-translation
                                </p>
                                <p
                                    className="mt-1 whitespace-pre-wrap break-words text-sm text-ink-2"
                                    lang="en-US"
                                >
                                    {result.back_translation}
                                </p>
                            </div>
                        ) : (
                            <p className="text-[11px] text-warn-ink">
                                The back-translation is unavailable, so you cannot check this wording
                                yet. Check again before confirming.
                            </p>
                        )}

                        <p className="text-[11px]">
                            <span className="text-ok-ink">✓ Numbers and medication names match</span>
                        </p>

                        <label
                            className={`flex items-start gap-2.5 rounded-lg border p-2.5 text-xs leading-relaxed ${
                                !result.back_translation
                                    ? "cursor-not-allowed border-line bg-surface-2 text-muted"
                                    : confirmed
                                      ? "border-ok-line bg-ok-soft text-ok-ink"
                                      : "border-line-strong bg-surface text-ink-2 hover:border-primary-line"
                            }`}
                        >
                            <input
                                checked={confirmed}
                                className="mt-0.5 h-4 w-4 shrink-0 accent-[var(--color-ok)]"
                                disabled={disabled || !result.back_translation}
                                onChange={(event) => onConfirm(event.target.checked)}
                                type="checkbox"
                            />
                            <span>
                                I checked the back-translation against what I wrote and confirm this
                                is what the patient should receive.
                            </span>
                        </label>
                    </>
                ) : null}
            </div>
        </section>
    );
}

/**
 * Hold a preview for one draft, and forget it when the draft changes.
 *
 * A slower, older response is ignored, so a quick edit followed by a second preview cannot
 * leave the first one's wording on screen as if it described the new text.
 */
export function useReplyPreview(
    request: (body: string) => Promise<ConversationPreviewResult>,
    body: string,
) {
    const [state, setState] = useState<PreviewState>({ kind: "idle" });
    // The draft the confirmation covers, rather than a bare flag. Editing the message then
    // changes `confirmed` to false on its own, with nothing to keep in step.
    const [confirmedBody, setConfirmedBody] = useState<string | null>(null);
    const latest = useRef(0);

    const text = body.trim();
    const confirmed = confirmedBody !== null && confirmedBody === text;

    const setConfirmed = useCallback(
        (value: boolean) => setConfirmedBody(value ? text : null),
        [text],
    );

    const preview = useCallback(async () => {
        const current = body.trim();
        if (!current) return;
        const attempt = ++latest.current;
        setConfirmedBody(null);
        setState({ kind: "loading" });
        try {
            const result = await request(current);
            if (attempt === latest.current) setState({ kind: "ready", result, body: current });
        } catch {
            if (attempt === latest.current) setState({ kind: "error" });
        }
    }, [body, request]);

    const reset = useCallback(() => {
        latest.current += 1;
        setState({ kind: "idle" });
        setConfirmedBody(null);
    }, []);

    return { state, confirmed, setConfirmed, preview, reset };
}
