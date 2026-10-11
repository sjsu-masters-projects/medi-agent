"use client";

import { useEffect, useRef, useState } from "react";
import { HiStop } from "react-icons/hi2";
import { CARE_ASSISTANT_NAME, getPatientChatCopy, getChatControlsCopy } from "@/content/chat-copy";
import { CareConversations } from "@/components/features/care-conversations";
import { ChatBubble } from "@/components/features";
import { Icon } from "@/components/ui/icons";
import { ChatTextarea, chatButton } from "@/components/features/chat-presentation";
import { usePatientChatSession } from "@/hooks/use-patient-chat-session";
import { usePatientProfile } from "@/hooks/use-patient-profile";
import { usePatientShell } from "@/contexts/patient-shell-context";
import { ChatRole, DEFAULT_LOCALE } from "@/types";

export default function ChatPage() {
    const profile = usePatientProfile();
    const { conversationOpen, setConversationOpen } = usePatientShell();
    const locale = profile?.preferredLanguage ?? DEFAULT_LOCALE;
    const copy = getPatientChatCopy(locale);
    const controls = getChatControlsCopy(locale);
    const [conversation, setConversation] = useState<"assistant" | "care-team">("assistant");
    const [careTeamOpened, setCareTeamOpened] = useState(false);
    const [inbox, setInbox] = useState(() => !conversationOpen && (typeof window === "undefined" || !new URLSearchParams(window.location.search).has("document")));
    const [showHistory, setShowHistory] = useState(false);
    const [humanThreadId, setHumanThreadId] = useState<string | null>(null);
    const bottomRef = useRef<HTMLDivElement | null>(null);
    const headingRef = useRef<HTMLHeadingElement | null>(null);
    const noraOpenRef = useRef<HTMLButtonElement | null>(null);
    const previousInbox = useRef(inbox);
    const { assistantDraft, assistantDraftStartedAt, canPlayAssistantAudio, connectionStatus,
        dismissDocumentContext, dismissSafetyNotice, documentContext, error, handleHandsFreeToggle,
        handleMicClick, handlePlayAssistantMessage, handleSend, handsFreeMode, input,
        isTyping, loading, messages, safetyNotice, setInput, voiceError, voiceStatus } = usePatientChatSession(locale);
    const historicalMessages = messages.filter((message) => message.role === ChatRole.CLINICIAN);
    const visibleMessages = messages.filter((message) => message.role !== ChatRole.CLINICIAN)
        .map((message) => message.id === "welcome-message"
            ? { ...message, content: copy.welcomeMessage, language: locale, audioUrl: undefined }
            : message);
    const voiceBusy = ["listening", "processing", "playing"].includes(voiceStatus);
    const button = chatButton;
    const back = locale === "es-MX" ? "Volver a mensajes" : "Back to messages";
    const threadOpen = (!inbox && conversation === "assistant") || Boolean(humanThreadId);

    useEffect(() => {
        setConversationOpen(threadOpen);
        return () => setConversationOpen(false);
    }, [threadOpen, setConversationOpen]);

    useEffect(() => {
        if (previousInbox.current !== inbox) {
            if (inbox) noraOpenRef.current?.focus();
            else headingRef.current?.focus();
        }
        previousInbox.current = inbox;
    }, [inbox]);

    useEffect(() => {
        if (!inbox) bottomRef.current?.scrollIntoView({ behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "nearest" });
    }, [assistantDraft, isTyping, messages, conversation, inbox]);

    return <div className={`flex w-full flex-col gap-4 px-4 py-4 text-ink ${threadOpen ? "min-h-dvh" : "min-h-[calc(100dvh-110px)]"}`} lang={locale}>
        <header hidden={Boolean(humanThreadId)} className="flex items-center gap-2.5 border-b border-line-strong pb-3">
            {!inbox && <button type="button" className={button + " flex min-w-11 items-center justify-center px-0"} aria-label={back} disabled={voiceBusy} onClick={() => { setInbox(true); setCareTeamOpened(true); }}><Icon name="back" /></button>}
            {!inbox && conversation === "assistant" && <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-deep text-gold"><Icon name="spark" /></span>}
            <div className="min-w-0 flex-1">
            <h1 ref={headingRef} tabIndex={-1} className={inbox ? "break-words px-1.5 pt-2 text-[32px] font-semibold tracking-[-0.02em]" : "break-words text-lg font-semibold"}>{inbox ? "Chat" : conversation === "assistant" ? CARE_ASSISTANT_NAME : copy.careTeamLabel}</h1>
            {!inbox && conversation === "assistant" && <>
                <p className="mt-1 text-xs text-muted">{copy.assistantDescription}</p>
                <p className="mt-1 text-xs text-muted" role="status">{controls.connection[connectionStatus]}</p>
            </>}
            </div>
            {!inbox && <button type="button" aria-label={conversation === "assistant" ? copy.careTeamLabel : `${CARE_ASSISTANT_NAME} · ${copy.assistantDescription}`} aria-pressed={false} disabled={voiceBusy}
                className={button + " flex min-w-11 items-center justify-center px-2"}
                onClick={() => { setCareTeamOpened(true); setConversation(conversation === "assistant" ? "care-team" : "assistant"); }}>
                <Icon name={conversation === "assistant" ? "users" : "spark"} />
            </button>}
            {!inbox && conversation === "assistant" && <button className={button + " flex min-w-11 items-center justify-center px-2"} aria-label={handsFreeMode ? controls.handsFreeOn : controls.handsFreeOff} aria-pressed={handsFreeMode} onClick={handleHandsFreeToggle} type="button"><Icon name="speaker" /></button>}
        </header>
        {inbox ? <section hidden={Boolean(humanThreadId)} className="relative flex flex-col gap-3 overflow-hidden rounded-[28px] bg-brand-deep p-5 text-[#F2F7F5] shadow-[0_18px_36px_-16px_rgba(15,61,55,.6)]">
            <span aria-hidden="true" className="pointer-events-none absolute -right-[60px] -top-[60px] h-[200px] w-[200px] rounded-full bg-[radial-gradient(circle,rgba(245,196,106,.28),transparent_70%)]" />
            <div className="relative flex items-center gap-3">
                <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-white/20 bg-white/10 text-gold"><Icon name="spark" /></span>
                <div className="min-w-0 flex-1 break-words"><h2 className="text-[19px] font-semibold">{CARE_ASSISTANT_NAME} <span className="ml-1 rounded-md bg-[rgba(245,196,106,.18)] px-1.5 py-0.5 text-xs font-semibold tracking-[0.06em] text-gold">AI</span></h2><p className="text-[13px] text-[#B9D1CC]">{copy.assistantDescription} · {locale === "es-MX" ? "no es un profesional clínico" : "not a clinician"}</p></div>
            </div>
            <p className="relative text-sm leading-relaxed">{controls.caution}</p>
            <div className="relative flex flex-wrap gap-2">
            <button type="button" className="min-h-11 rounded-full bg-gold px-4 py-2 text-sm font-semibold text-[#2B1F05]" onClick={() => { setInput(copy.quickPrompts[1]); setCareTeamOpened(true); setConversation("assistant"); setInbox(false); }}>{locale === "es-MX" ? "Reportar un síntoma" : "Report a symptom"}</button>
            <button ref={noraOpenRef} type="button" aria-label={`${CARE_ASSISTANT_NAME} · ${copy.assistantDescription}`} aria-pressed={false} className="min-h-11 rounded-full border border-white/20 bg-white/10 px-4 py-2 text-sm font-semibold text-white" onClick={() => { setCareTeamOpened(true); setConversation("assistant"); setInbox(false); }}>{locale === "es-MX" ? "Abrir chat" : "Open chat"}</button>
            </div>
        </section> : null}
        {(inbox || careTeamOpened) && <div hidden={!inbox && conversation !== "care-team"} className="space-y-4">
            <CareConversations compact locale={locale} visible={inbox || conversation === "care-team"} onThreadPresentationChange={setHumanThreadId} />
            {historicalMessages.length > 0 && <section hidden={Boolean(humanThreadId)} className="space-y-3 rounded-[22px] bg-surface p-4">
                <button className={button} type="button" aria-expanded={showHistory}
                    onClick={() => setShowHistory((current) => !current)}>
                    {copy.historicalCareTeamLabel} ({historicalMessages.length})
                </button>
                {showHistory && (inbox || conversation === "care-team") && <>
                    <p className="text-sm text-muted">{copy.historicalCareTeamIntro}</p>
                    {historicalMessages.map((message) => <ChatBubble key={message.id} role="clinician"
                        content={message.content} timestamp={message.createdAt} locale={locale}
                        language={message.language} clinicianLabel={copy.historicalCareTeamLabel} />)}
                </>}
            </section>}
        </div>}
        {!inbox && conversation === "assistant" && <>
            <p className="rounded-2xl bg-danger-tint p-3.5 text-sm text-danger-ink">{controls.caution}</p>
            {documentContext && <section className="rounded-[22px] border border-line-strong bg-brand-tint p-4">
                <p className="text-xs font-semibold text-brand-ink">{controls.recordContext}</p>
                <p className="mt-1 break-words font-semibold">{documentContext.documentName}</p>
                {documentContext.provider && <p className="mt-1 text-sm text-ink-2">{documentContext.provider}</p>}
                <button className={button + " mt-3"} onClick={dismissDocumentContext} type="button">{controls.dismiss}</button>
            </section>}
            {error && <p className="rounded-2xl bg-danger-tint p-3 text-sm text-danger-ink" role="alert">{controls.chatError}</p>}
            {safetyNotice && <div className="flex items-start gap-3 rounded-2xl bg-danger-tint p-3 text-sm text-danger-ink" role="alert">
                <p className="flex-1">{copy.escalationNotice}</p>
                <button className={button} onClick={dismissSafetyNotice} type="button">{controls.dismiss}</button>
            </div>}
            {voiceError && <p className="rounded-2xl bg-danger-tint p-3 text-sm text-danger-ink" role="alert">{controls.voiceError}</p>}
            <div className="flex-1 space-y-4" aria-busy={loading}>
                {loading && <p className="text-sm text-muted" role="status">{controls.loading}</p>}
                {!loading && !documentContext && !messages.some((message) => message.role === ChatRole.USER) && <section className="space-y-3 rounded-[22px] bg-surface p-4">
                    <p className="text-sm text-ink-2">{copy.emptyStateIntro}</p>
                    <div className="flex flex-col gap-2">{copy.quickPrompts.map((prompt) => <button className={button + " text-left"} key={prompt} type="button" onClick={() => setInput(prompt)}>{prompt}</button>)}</div>
                </section>}
                {visibleMessages.map((message) => <ChatBubble key={message.id} content={message.content}
                    language={message.language} locale={locale} role={message.role === ChatRole.USER ? "user" : "assistant"}
                    timestamp={message.createdAt} onPlayAudio={message.role === ChatRole.ASSISTANT && (Boolean(message.audioUrl) || canPlayAssistantAudio) ? () => handlePlayAssistantMessage(message) : undefined} />)}
                {assistantDraft && <ChatBubble content={assistantDraft} isStreaming language={locale} locale={locale}
                    role="assistant" timestamp={assistantDraftStartedAt ?? new Date().toISOString()} />}
                {isTyping && !assistantDraft && <p className="text-sm text-muted" role="status">{copy.typingMessage}</p>}
                <div ref={bottomRef} />
            </div>
            <form className="sticky bottom-0 z-10 mt-auto space-y-2 bg-background pt-3 pb-[calc(env(safe-area-inset-bottom)+12px)]" onSubmit={handleSend}>
                <div className="flex items-end gap-2">
                    <div className="flex min-h-[52px] min-w-0 flex-1 items-end rounded-[26px] border border-line-strong bg-surface pr-1 pb-1">
                        <ChatTextarea aria-label={controls.message} onChange={(event) => setInput(event.target.value)}
                        onKeyDown={(event) => {
                            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                                event.preventDefault();
                                if (input.trim() && connectionStatus === "connected" && profile)
                                    event.currentTarget.form?.requestSubmit();
                            }
                        }}
                        placeholder={voiceStatus === "listening" ? controls.listening : voiceStatus === "processing" ? controls.transcribing : copy.inputPlaceholder} value={input} />
                    <button className={button + " flex min-w-11 shrink-0 items-center justify-center rounded-full px-0"} aria-label={voiceStatus === "listening" ? controls.stopVoice : voiceStatus === "playing" ? controls.interrupt : controls.speak} aria-pressed={voiceStatus === "listening"}
                        disabled={voiceStatus === "unsupported" || voiceStatus === "processing" || !profile} onClick={handleMicClick} type="button">
                        {voiceStatus === "listening" ? <HiStop aria-hidden className="h-5 w-5" /> : <Icon name="mic" />}
                    </button>
                    </div>
                    <button className="flex h-[52px] w-[52px] shrink-0 items-center justify-center rounded-full bg-brand text-white disabled:opacity-50"
                        aria-label={controls.send} disabled={!input.trim() || connectionStatus !== "connected" || !profile} type="submit"><Icon name="send" /></button>
                </div>
                {handsFreeMode && <p className="text-xs text-muted">{controls.autoPlay}</p>}
                {!profile && <p className="text-sm text-muted" role="status">{controls.profileRequired}</p>}
            </form>
        </>}
    </div>;
}
