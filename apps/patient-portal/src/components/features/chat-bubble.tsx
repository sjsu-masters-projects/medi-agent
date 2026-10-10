import { HiMiniSpeakerWave, HiOutlineUser } from "react-icons/hi2";
import { ChatRole, DEFAULT_LOCALE, getLocaleLabel, type Locale } from "@/types";
import { CARE_ASSISTANT_NAME, getChatControlsCopy } from "@/content/chat-copy";

interface ChatBubbleProps {
    clinicianLabel?: string;
    role: typeof ChatRole.USER | typeof ChatRole.ASSISTANT | typeof ChatRole.CLINICIAN;
    content: string;
    timestamp: Date | string;
    language?: Locale;
    locale?: Locale;
    isStreaming?: boolean;
    onPlayAudio?: () => void;
}

export function ChatBubble({
    clinicianLabel = "Care team messages", content, isStreaming = false,
    language, locale = DEFAULT_LOCALE, onPlayAudio, role, timestamp,
}: ChatBubbleProps) {
    const isUser = role === ChatRole.USER;
    const isClinician = role === ChatRole.CLINICIAN;
    const copy = getChatControlsCopy(locale);
    const time = timestamp instanceof Date ? timestamp : new Date(timestamp);
    return <div className={"flex items-end gap-2 " + (isUser ? "justify-end" : "")}>
        {!isUser && <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-blue-100 text-blue-800" aria-hidden>
            {isClinician ? <HiOutlineUser className="h-5 w-5" /> : CARE_ASSISTANT_NAME.charAt(0)}
        </span>}
        <div className="min-w-0 max-w-[88%] space-y-1.5 sm:max-w-[80%]">
            {isClinician && <p className="text-xs font-semibold text-blue-800">{clinicianLabel}</p>}
            <div className={"space-y-3 rounded-2xl border p-3 text-sm leading-6 " + (isUser ? "rounded-tr-sm border-blue-100 bg-blue-50 text-blue-900" : "rounded-tl-sm border-gray-200 bg-white text-gray-800")}>
                <p className="whitespace-pre-wrap break-words" lang={language}>{content}</p>
                <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500">
                    <span>{language ? copy.original + ": " + getLocaleLabel(language) : copy.originalUnknown}</span>
                    {isStreaming && <span role="status">{copy.live}</span>}
                    {onPlayAudio && <button className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700 focus-visible:outline-2 focus-visible:outline-blue-600" onClick={onPlayAudio} type="button">
                        <HiMiniSpeakerWave aria-hidden className="h-4 w-4" />{copy.listen}
                    </button>}
                </div>
            </div>
            {!Number.isNaN(time.getTime()) && <time className="block text-xs text-gray-500" dateTime={time.toISOString()}>
                {time.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" })}
            </time>}
        </div>
    </div>;
}
