import { Icon } from "@/components/ui/icons";
import { ChatRole, DEFAULT_LOCALE, getLocaleLabel, type Locale } from "@/types";
import { getChatControlsCopy } from "@/content/chat-copy";
import { chatDisplayTime } from "./chat-presentation";

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
        {!isUser && <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${isClinician ? "bg-note-tint text-note-ink" : "bg-brand-deep text-gold"}`} aria-hidden>
            <Icon name={isClinician ? "user" : "spark"} className="h-5 w-5" />
        </span>}
        <div className={`min-w-0 space-y-1.5 ${isUser ? "max-w-[82%]" : "max-w-[88%]"}`}>
            {isClinician && <p className="text-xs font-semibold text-ink-2">{clinicianLabel}</p>}
            <div className={"space-y-3 px-3.5 py-3 text-[15px] leading-relaxed " + (isUser ? "rounded-[20px_20px_6px_20px] bg-brand text-white" : "rounded-[20px_20px_20px_6px] bg-surface text-ink")}>
                <p className="whitespace-pre-wrap break-words" lang={language}>{content}</p>
                {(isStreaming || onPlayAudio) && <div className={`flex flex-wrap items-center gap-2 text-xs ${isUser ? "text-white" : "text-muted"}`}>
                    {isStreaming && <span role="status">{copy.live}</span>}
                    {onPlayAudio && <button className="inline-flex min-h-11 items-center gap-2 rounded-full bg-surface-2 px-3 py-2 text-[13px] font-medium text-ink-2" onClick={onPlayAudio} type="button">
                        <Icon name="speaker" className="h-4 w-4" />{copy.listen}
                    </button>}
                </div>}
            </div>
            <p className="px-1 font-mono text-xs text-muted">
                {!Number.isNaN(time.getTime()) && <><time dateTime={time.toISOString()}>{chatDisplayTime(time, locale)}</time> · </>}
                <span>{language ? copy.original + ": " + getLocaleLabel(language) : copy.originalUnknown}</span>
            </p>
        </div>
    </div>;
}
