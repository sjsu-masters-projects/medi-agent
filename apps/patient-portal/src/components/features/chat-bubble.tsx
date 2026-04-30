import { HiMiniSpeakerWave } from "react-icons/hi2";
import { ChatRole, getLocaleBadgeLabel, type Locale } from "@/types";

interface ChatBubbleProps {
    role: typeof ChatRole.USER | typeof ChatRole.ASSISTANT;
    content: string;
    timestamp: Date | string;
    language?: Locale;
    isStreaming?: boolean;
    onPlayAudio?: () => void;
}

function formatTimestamp(timestamp: Date | string) {
    const value = timestamp instanceof Date ? timestamp : new Date(timestamp);
    return value.toLocaleTimeString(undefined, {
        hour: "numeric",
        minute: "2-digit",
    });
}

function formatLanguage(language?: Locale): string | null {
    if (!language) {
        return null;
    }

    return getLocaleBadgeLabel(language);
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
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl border border-[#b6d9d2] bg-[#e6f4f1] text-[10px] font-black uppercase tracking-[0.22em] text-[#147465] shadow-[0_10px_24px_rgba(20,116,101,0.10)]">
                    M
                </span>
            ) : null}
            <div className={`max-w-[82%] space-y-1.5 ${isUser ? "items-end text-right" : ""}`}>
                <div
                    className={`rounded-[24px] px-4 py-3.5 text-base leading-7 shadow-[0_18px_40px_rgba(3,8,22,0.16)] ${
                        isUser
                            ? "rounded-br-[10px] border border-[#147465] bg-[#147465] text-white shadow-[0_16px_30px_rgba(20,116,101,0.20)]"
                            : "rounded-bl-[10px] border border-[#eadfd4] bg-white/90 text-[#17233a] shadow-[0_12px_28px_rgba(42,58,84,0.10)]"
                    }`}
                >
                    <div className="space-y-3">
                        <p className="whitespace-pre-wrap">{content}</p>
                        {!isUser && (languageLabel || onPlayAudio || isStreaming) ? (
                            <div className="flex flex-wrap items-center gap-2 text-[11px]">
                                {languageLabel ? (
                                    <span className="rounded-full border border-[#b6d9d2] bg-[#e6f4f1] px-2.5 py-1 text-[#147465]">
                                        {languageLabel}
                                    </span>
                                ) : null}
                                {isStreaming ? (
                                    <span className="rounded-full border border-[#b6d9d2] bg-[#e6f4f1] px-2.5 py-1 text-[#147465]">
                                        Live response
                                    </span>
                                ) : null}
                                {onPlayAudio ? (
                                    <button
                                        className="inline-flex items-center gap-1 rounded-full border border-[#d9cbc0] bg-white/80 px-2.5 py-1 text-[#30415f] transition hover:border-[#b6d9d2] hover:bg-white"
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
                <p className="px-1 text-[11px] font-medium text-[#8090a5]">{formatTimestamp(timestamp)}</p>
            </div>
        </div>
    );
}
