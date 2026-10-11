"use client";

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
            <div className="flex h-40 items-center justify-center text-sm text-muted">
                No chat transcript available
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

                return (
                    <div
                        className={`flex flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}
                        key={`${msg.created_at}-${idx}`}
                    >
                        {/* Sender label */}
                        <span className="px-1 text-xs text-muted">
                            {isUser ? "Patient" : "Nora · AI care assistant"} · {formatTime(msg.created_at)}
                        </span>

                        {/* Message bubble — DESIGN_SYSTEM.md styles */}
                        <div
                            className={
                                isUser
                                    ? "max-w-[90%] whitespace-pre-wrap break-words rounded-2xl rounded-tr-sm border border-primary-line bg-primary-tint p-3 text-sm text-ai-ink"
                                    : "max-w-[90%] whitespace-pre-wrap break-words rounded-2xl rounded-tl-sm border border-line bg-surface-2 p-3 text-sm text-ink"
                            }
                        >
                            {msg.content}
                        </div>

                        {/* Audio indicator */}
                        {msg.audio_url && (
                            <span className="flex items-center gap-1 text-xs text-muted">
                                🎙 Voice message
                            </span>
                        )}
                    </div>
                );
            })}
        </div>
    );
}
