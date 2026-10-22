import type { ReactNode } from "react";
import { Icon } from "@/components/ui/icons";
import { ProcessingDots } from "@/components/ui/motion";
import { ChatRole, DEFAULT_LOCALE, getLocaleLabel, type ChatAttachment, type ChatDocumentResultsAttachment, type Locale } from "@/types";
import { CARE_ASSISTANT_NAME, getChatControlsCopy } from "@/content/chat-copy";
import { chatDisplayTime } from "./chat-presentation";
import { ChatResultsCard } from "./chat-results-card";

interface ChatBubbleProps {
    /** Server-built cards shown under a Nora reply's text. */
    attachments?: ChatAttachment[];
    clinicianLabel?: string;
    role: typeof ChatRole.USER | typeof ChatRole.ASSISTANT | typeof ChatRole.CLINICIAN;
    content: string;
    timestamp: Date | string;
    language?: Locale;
    locale?: Locale;
    isStreaming?: boolean;
    onPlayAudio?: () => void;
    /** A user message not yet confirmed by the server, or rejected (text kept). */
    delivery?: "pending" | "failed";
    onRetrySend?: () => void;
    onRemoveUnsent?: () => void;
    /** A conversational offer shown inside Nora's reply, under its text. */
    offer?: ReactNode;
}

export function ChatBubble({
    attachments, clinicianLabel = "Care team messages", content, isStreaming = false,
    delivery, language, locale = DEFAULT_LOCALE, offer, onPlayAudio, onRemoveUnsent, onRetrySend, role, timestamp,
}: ChatBubbleProps) {
    const isUser = role === ChatRole.USER;
    const isClinician = role === ChatRole.CLINICIAN;
    const copy = getChatControlsCopy(locale);
    const time = timestamp instanceof Date ? timestamp : new Date(timestamp);
    const validTime = !Number.isNaN(time.getTime());
    const languageLabel = language ? copy.original + ": " + getLocaleLabel(language) : copy.originalUnknown;
    const timeNode = validTime ? <time dateTime={time.toISOString()}>{chatDisplayTime(time, locale)}</time> : null;

    if (isUser) {
        return <div className="ma-bubble flex flex-col items-end gap-1" data-delivery={delivery}>
            <div className={`max-w-[82%] rounded-[20px_20px_6px_20px] px-3.5 py-[11px] text-[15px] leading-[1.45] text-white ${delivery === "pending" ? "bg-brand/70" : delivery === "failed" ? "bg-brand/60 ring-2 ring-danger-ink" : "bg-brand"}`}>
                <p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]" lang={language}>{content}</p>
            </div>
            {delivery === "pending" && <p role="status" className="px-1 text-right text-[11px] text-muted">{copy.sending}</p>}
            {delivery === "failed" && <div role="alert" className="flex flex-wrap items-center justify-end gap-2 px-1 text-xs text-danger-ink">
                <span className="font-semibold">{copy.notSent}</span>
                <button type="button" className="ma-press min-h-11 rounded-xl bg-brand-tint px-3 font-semibold text-brand-ink" onClick={onRetrySend}>{copy.retrySend}</button>
                <button type="button" className="ma-press min-h-11 rounded-xl px-3 font-medium text-ink-2" onClick={onRemoveUnsent}>{copy.removeUnsent}</button>
            </div>}
            {!delivery && <p className="max-w-[90%] px-1 text-right font-mono text-[11px] text-muted first-letter:uppercase">
                {timeNode ? <>{timeNode} · </> : null}<span>{languageLabel}</span>
            </p>}
        </div>;
    }

    const cards = !isClinician
        ? attachments?.filter((attachment): attachment is ChatDocumentResultsAttachment => attachment.type === "document_results")
        : undefined;
    const hasCards = Boolean(cards?.length);
    return <div className="ma-bubble flex flex-col items-start gap-1">
        {isClinician && <p className="px-1 text-xs font-semibold text-note-ink">{clinicianLabel}</p>}
        <div className={`${hasCards ? "w-full min-w-0 " : ""}max-w-[88%] rounded-[20px_20px_20px_6px] px-[15px] py-[13px] text-[15px] leading-[1.5] text-ink ${isClinician ? "bg-note-tint/70" : "bg-surface shadow-[0_1px_0_rgba(16,32,43,.04)]"}`}>
            <p className="whitespace-pre-wrap break-words [overflow-wrap:anywhere]" lang={language}>{content}</p>
            {offer}
            {cards?.map((attachment, index) => <ChatResultsCard key={`${attachment.documentId}-${index}`}
                attachment={attachment} language={language} locale={locale} />)}
            <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-2.5 text-xs text-muted">
                {isStreaming
                    ? <span role="status" className="inline-flex items-center gap-2 text-brand-ink">{copy.live}<ProcessingDots className="bg-brand" /></span>
                    : <span className="min-w-0">{languageLabel}</span>}
                {onPlayAudio && <button className="ma-press relative before:absolute before:-inset-x-1 before:-inset-y-[7px] before:content-[''] inline-flex min-h-[30px] items-center gap-1.5 rounded-full bg-surface-2 px-3 py-1 text-[13px] font-medium text-ink-2 hover:bg-line-strong" onClick={onPlayAudio} type="button">
                    <Icon name="speaker" className="h-4 w-4" />{copy.listen}
                </button>}
            </div>
        </div>
        <p className="px-1 font-mono text-[11px] text-muted first-letter:uppercase">
            {isClinician ? null : <>{CARE_ASSISTANT_NAME}{timeNode ? " · " : ""}</>}{timeNode}
            {isStreaming ? <span className="sr-only"> · {languageLabel}</span> : null}
        </p>
    </div>;
}
