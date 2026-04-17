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
    if (messages.length === 0) {
        return (
            <div className="flex h-40 items-center justify-center text-sm text-gray-400">
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
                        <span className="px-1 text-xs text-gray-400">
                            {isUser ? "Patient" : "AI Assistant"} · {formatTime(msg.created_at)}
                        </span>

                        {/* Message bubble — DESIGN_SYSTEM.md styles */}
                        <div
                            className={
                                isUser
                                    ? "rounded-2xl rounded-tr-sm border border-blue-100 bg-blue-50 p-3 text-sm text-blue-900"
                                    : "rounded-2xl rounded-tl-sm border border-gray-200 bg-gray-50 p-3 text-sm text-gray-800"
                            }
                            style={{ maxWidth: "80%" }}
                        >
                            {msg.content}
                        </div>

                        {/* Audio indicator */}
                        {msg.audio_url && (
                            <span className="flex items-center gap-1 text-xs text-gray-400">
                                🎙 Voice message
                            </span>
                        )}
                    </div>
                );
            })}
        </div>
    );
}
