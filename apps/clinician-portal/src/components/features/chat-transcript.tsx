"use client";

import { AiChip } from "@/components/ui/ai-chip";
import { Icon } from "@/components/ui/icons";
import { ChatRole } from "@/types";

interface TranscriptMessage {
    role: typeof ChatRole[keyof typeof ChatRole];
    content: string;
    created_at: string;
    audio_url?: string;
}

interface ChatTranscriptProps {
    messages: TranscriptMessage[];
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

export function ChatTranscript({ messages }: ChatTranscriptProps) {
    messages = messages.filter((message) => message.role !== ChatRole.CLINICIAN);
    if (messages.length === 0) {
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
            {messages.map((msg, idx) => {
                const isUser = msg.role === ChatRole.USER;
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
