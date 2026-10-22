"use client";

import { useEffect, useRef, useState } from "react";
import { requestPendingTranslations } from "../../../../../packages/shared/src/utils/care-conversations";
import { AiChip } from "@/components/ui/ai-chip";
import { Icon } from "@/components/ui/icons";
import { TranslationBadge } from "@/components/ui/translation-note";
import { translateTranscriptMessage, type TranscriptTranslationResult } from "@/services/clinicians";
import { ChatRole } from "@/types";

/**
 * The patient-Nora transcript, as the clinician reads it.
 *
 * LOC-003: a patient writing Spanish is read by a clinician who may read none, so a Spanish
 * turn carries an English translation beneath it, labelled, with the model's caveat. The
 * patient's own words stay above as the record — safety checks and escalation read only
 * those, never a translation.
 *
 * Reading never waits for a model. The server attaches translations it already stored and
 * marks the rest `translation_pending`; this component then asks for those, three at a time,
 * after the transcript is already on screen.
 */

interface TranscriptMessage {
    role: typeof ChatRole[keyof typeof ChatRole];
    content: string;
    created_at: string;
    audio_url?: string;
    /** Present once the deep dive has an id for the turn; needed to ask for a translation. */
    id?: string;
    /** LOC-003: stored English translation of a Spanish turn. */
    translation?: string | null;
    translation_locale?: string | null;
    translation_guard_passed?: boolean | null;
    translation_pending?: boolean;
    translation_model_id?: string | null;
}

interface ChatTranscriptProps {
    messages: TranscriptMessage[];
    /** Needed to request a pending translation; without it the originals stand alone. */
    patientId?: string;
}

function formatTime(isoString: string): string {
    const date = new Date(isoString);
    return date.toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
    });
}

/** Fold a translation result into a turn; no translation just clears the pending marker. */
function applyResult(
    message: TranscriptMessage,
    result: TranscriptTranslationResult | null,
): TranscriptMessage {
    if (!result?.translation) return { ...message, translation_pending: false };
    return {
        ...message,
        translation: result.translation,
        translation_locale: result.translation_locale,
        translation_guard_passed: result.translation_guard_passed,
        translation_model_id: result.translation_model_id,
        translation_pending: false,
    };
}

export function ChatTranscript({ messages, patientId }: ChatTranscriptProps) {
    const visible = messages.filter((message) => message.role !== ChatRole.CLINICIAN);
    const [turns, setTurns] = useState<TranscriptMessage[]>(visible);
    const requested = useRef(new Set<string>());
    const alive = useRef(true);

    // The transcript is a prop, so a reload or a tab switch replaces it wholesale.
    const identity = visible.map((message) => `${message.id ?? ""}:${message.created_at}`).join("|");
    useEffect(() => {
        setTurns(visible);
        // `identity` stands for the transcript this effect resets to.
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [identity]);

    useEffect(() => {
        alive.current = true;
        return () => {
            alive.current = false;
        };
    }, []);

    /* LOC-003: ask for the turns the read marked pending, at most three at a time, after the
       originals are already rendered. A failure leaves the original alone. */
    useEffect(() => {
        if (!patientId) return;
        const pending = turns.filter(
            (message): message is TranscriptMessage & { id: string } =>
                Boolean(message.translation_pending && message.id && !requested.current.has(message.id)),
        );
        if (!pending.length) return;
        void requestPendingTranslations<TranscriptTranslationResult, TranscriptMessage & { id: string }>(
            pending,
            requested.current,
            (messageId) => translateTranscriptMessage(patientId, messageId),
            (messageId, result) =>
                setTurns((current) =>
                    current.map((message) => (message.id === messageId ? applyResult(message, result) : message)),
                ),
            () => alive.current,
        );
    }, [turns, patientId]);

    if (turns.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center gap-3 px-6 py-10 text-center">
                <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-sunken text-muted">
                    <Icon name="chat" className="h-6 w-6" />
                </span>
                <p className="text-sm text-muted">No chat transcript available</p>
            </div>
        );
    }

    return (
        <div
            aria-label="Chat transcript"
            className="flex max-h-[480px] flex-col gap-3 overflow-y-auto px-1 py-2"
        >
            {turns.map((msg, idx) => {
                const isUser = msg.role === ChatRole.USER;
                // A clinician reads English: only a translation into English is ever shown,
                // and only when its guard passed.
                const showTranslation =
                    Boolean(msg.translation) &&
                    msg.translation_locale === "en-US" &&
                    msg.translation_guard_passed !== false;
                const time = (
                    <time dateTime={msg.created_at} className="font-mono text-[11px] text-muted">
                        {formatTime(msg.created_at)}
                    </time>
                );

                return (
                    <div
                        className={`flex max-w-[78%] flex-col gap-1 ${isUser ? "items-end self-end" : "items-start self-start"}`}
                        key={`${msg.created_at}-${idx}`}
                    >
                        {/* Sender label; Nora's turns always carry the AI chip */}
                        {isUser ? (
                            <span className="flex items-center gap-1.5 px-1 text-[11px] text-muted">
                                <span>Patient</span>
                                <span aria-hidden="true">·</span>
                                {time}
                            </span>
                        ) : (
                            <span className="flex flex-wrap items-center gap-1.5 px-1">
                                <AiChip className="px-2 py-0.5 text-[11px]">Nora · AI care assistant</AiChip>
                                {time}
                            </span>
                        )}

                        <div
                            className={
                                isUser
                                    ? "whitespace-pre-wrap break-words rounded-[18px_18px_6px_18px] bg-primary px-3.5 py-2.5 text-sm text-white"
                                    : "whitespace-pre-wrap break-words rounded-[18px_18px_18px_6px] bg-surface-2 px-3.5 py-2.5 text-sm text-ink"
                            }
                        >
                            {msg.content}
                        </div>

                        {/* LOC-003: the English translation sits under the original, never over it. */}
                        {msg.translation_pending ? (
                            <p className="px-1 text-[11px] text-muted" role="status">
                                Translating…
                            </p>
                        ) : null}
                        {msg.translation && msg.translation_guard_passed === false ? (
                            <p className="px-1 text-[11px] text-muted">
                                Automatic translation unavailable for this message.
                            </p>
                        ) : null}
                        {showTranslation ? (
                            <div
                                className={`mt-0.5 rounded-lg border border-line bg-surface px-3 py-2 text-xs text-ink-2 ${isUser ? "self-end" : "self-start"}`}
                            >
                                <TranslationBadge modelId={msg.translation_model_id} />
                                <p className="mt-1 whitespace-pre-wrap break-words" lang="en-US">
                                    {msg.translation}
                                </p>
                            </div>
                        ) : null}

                        {msg.audio_url && (
                            <span className="flex items-center gap-1 px-1 text-xs text-muted">
                                <Icon name="mic" className="h-3.5 w-3.5" />
                                Voice message
                            </span>
                        )}
                    </div>
                );
            })}
        </div>
    );
}
