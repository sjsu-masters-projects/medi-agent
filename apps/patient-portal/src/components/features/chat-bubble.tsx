import { HiMiniSpeakerWave } from "react-icons/hi2";
import { ChatRole, Language } from "@/types";

interface ChatBubbleProps {
    role: typeof ChatRole.USER | typeof ChatRole.ASSISTANT;
    content: string;
    timestamp: Date | string;
    language?: Language;
    isStreaming?: boolean;
    onPlayAudio?: () => void;
}

function formatTimestamp(timestamp: Date | string) {
    const value = timestamp instanceof Date ? timestamp : new Date(timestamp);
    return value.toLocaleTimeString("en-US", {
        hour: "numeric",
        minute: "2-digit",
    });
}

function formatLanguage(language?: Language): string | null {
    if (!language) {
        return null;
    }

    return language === Language.ES ? "ES" : "EN";
}

export function ChatBubble({
    content,
    isStreaming = false,
    language,
    onPlayAudio,
    role,
    timestamp,
}: ChatBubbleProps) {
    const isUser = role === ChatRole.USER;
    const languageLabel = formatLanguage(language);

    return (
        <div className={`flex items-end gap-3 ${isUser ? "justify-end" : ""}`}>
            {!isUser ? (
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-[#D9E4F2] bg-white text-[10px] font-semibold uppercase tracking-[0.22em] text-[#36506F] shadow-[0_10px_24px_rgba(31,54,88,0.10)]">
                    AI
                </span>
            ) : null}
            <div className={`max-w-[82%] space-y-1.5 ${isUser ? "items-end text-right" : ""}`}>
                <div
                    className={`rounded-[24px] px-4 py-3.5 text-sm leading-6 shadow-[0_18px_40px_rgba(3,8,22,0.28)] ${
                        isUser
                            ? "rounded-br-[10px] border border-[#1B95E0] bg-[#1B95E0] text-white shadow-[0_16px_30px_rgba(27,149,224,0.20)]"
                            : "rounded-bl-[10px] border border-[#E6DDF8] bg-[#F5EEFF] text-[#26324B] shadow-[0_12px_28px_rgba(129,105,174,0.12)]"
                    }`}
                >
                    <div className="space-y-3">
                        <p className="whitespace-pre-wrap">{content}</p>
                        {!isUser && (languageLabel || onPlayAudio || isStreaming) ? (
                            <div className="flex flex-wrap items-center gap-2 text-[11px]">
                                {languageLabel ? (
                                    <span className="rounded-full border border-[#D8CCF5] bg-white/70 px-2.5 py-1 text-[#5C4C85]">
                                        {languageLabel}
                                    </span>
                                ) : null}
                                {isStreaming ? (
                                    <span className="rounded-full border border-[#96D4F4] bg-[#EAF7FF] px-2.5 py-1 text-[#1679BE]">
                                        Live response
                                    </span>
                                ) : null}
                                {onPlayAudio ? (
                                    <button
                                        className="inline-flex items-center gap-1 rounded-full border border-[#E2D7FA] bg-white/80 px-2.5 py-1 text-[#485775] transition hover:border-[#D1C3F2] hover:bg-white"
                                        onClick={onPlayAudio}
                                        type="button"
                                    >
                                        <HiMiniSpeakerWave className="h-3.5 w-3.5" />
                                        Listen
                                    </button>
                                ) : null}
                            </div>
                        ) : null}
                    </div>
                </div>
                <p className="px-1 text-[10px] text-[#8EA0BA]">{formatTimestamp(timestamp)}</p>
            </div>
        </div>
    );
}
