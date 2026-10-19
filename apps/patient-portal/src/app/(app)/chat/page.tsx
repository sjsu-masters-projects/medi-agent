"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { HiStop } from "react-icons/hi2";
import { CARE_ASSISTANT_NAME, getPatientChatCopy, getChatControlsCopy, getChatRecoveryCopy } from "@/content/chat-copy";
import { CareConversations } from "@/components/features/care-conversations";
import { NoraConversations } from "@/components/features/nora-conversations";
import { NotificationBell } from "@/components/features/notification-centre";
import { ADRFollowUpEntryRow } from "@/components/features/adr-follow-up-entry-row";
import { ADRFollowUpView } from "@/components/features/adr-follow-up-view";
import { getADRFollowUpCopy } from "@/content/adr-follow-up-copy";
import { todayConversationId } from "@/services/chat-api";
import { ChatBubble } from "@/components/features";
import { Icon } from "@/components/ui/icons";
import { ChatTextarea } from "@/components/features/chat-presentation";
import { ChatTurnRecovery } from "@/components/features/chat-turn-recovery";
import { ProcessingDots } from "@/components/ui/motion";
import { isTurnInProgress } from "@/hooks/use-chat-turn-recovery";
import { usePatientChatSession } from "@/hooks/use-patient-chat-session";
import { usePatientProfile } from "@/hooks/use-patient-profile";
import { usePatientShell } from "@/contexts/patient-shell-context";
import { ChatRole, DEFAULT_LOCALE } from "@/types";

const RECONNECT_QUIET_MS = 3000;
const SLOW_TURN_MS = 15_000;

export default function ChatPage() {
    const profile = usePatientProfile();
    const { conversationOpen, setConversationOpen } = usePatientShell();
    const locale = profile?.preferredLanguage ?? DEFAULT_LOCALE;
    const copy = getPatientChatCopy(locale);
    const controls = getChatControlsCopy(locale);
    const recoveryCopy = getChatRecoveryCopy(locale);
    const [conversation, setConversation] = useState<"assistant" | "care-team">("assistant");
    const [careTeamOpened, setCareTeamOpened] = useState(false);
    const searchParams = useSearchParams();
    const router = useRouter();
    // `?view=follow-up` hosts the ADR follow-up view; `request` wins over `assessment`.
    const followUpMode = searchParams.get("view") === "follow-up";
    const followUpRequestId = followUpMode ? searchParams.get("request") : null;
    const followUpAssessmentId = followUpMode && !followUpRequestId ? searchParams.get("assessment") : null;
    const careTeamDestination = searchParams.get("view") === "care-team";
    const conversationId = careTeamDestination ? searchParams.get("conversation") : null;
    const recipientId = careTeamDestination ? searchParams.get("recipient") : null;
    // A document handoff from Records opens Nora directly (see usePatientChatSession).
    const [inbox, setInbox] = useState(() => !conversationOpen && !searchParams.has("document") && !searchParams.has("session"));
    const requestedDestination = careTeamDestination ? `${conversationId ?? ""}:${recipientId ?? ""}` : null;
    const [appliedDestination, setAppliedDestination] = useState<string | null>(null);
    const documentDestination = searchParams.get("document");
    const [appliedDocument, setAppliedDocument] = useState(documentDestination);
    if (documentDestination !== appliedDocument) {
        setAppliedDocument(documentDestination);
        if (documentDestination) { setConversation("assistant"); setInbox(false); }
    }
    if (requestedDestination !== appliedDestination) {
        setAppliedDestination(requestedDestination);
        if (requestedDestination !== null) { setConversation("care-team"); setCareTeamOpened(true); setInbox(true); }
    }
    const [showHistory, setShowHistory] = useState(false);
    const [humanThreadId, setHumanThreadId] = useState<string | null>(null);
    const bottomRef = useRef<HTMLDivElement | null>(null);
    const headingRef = useRef<HTMLHeadingElement | null>(null);
    const noraOpenRef = useRef<HTMLButtonElement | null>(null);
    const previousInbox = useRef(inbox);
    const wasFollowUp = useRef(false);
    const { assistantDraft, assistantDraftStartedAt, canPlayAssistantAudio, connectionStatus,
        dismissDocumentContext, dismissSafetyNotice, documentContext, documentUnavailable, error, handleHandsFreeToggle,
        handleMicClick, handlePlayAssistantMessage, handleSend, handsFreeMode, input,
        isTyping, loading, messages, openConversation, safetyNotice, sessionId, setInput,
        startNewConversation, retryUnsentMessage, removeUnsentMessage, recoveryTurns, retryTurn, dismissTurn, reconnectChat, reconnecting, turnBusy, voiceError, voiceStatus } = usePatientChatSession(locale);
    // A drop shorter than RECONNECT_QUIET_MS is invisible: the header keeps saying Connected.
    const [reconnectSlow, setReconnectSlow] = useState(false);
    useEffect(() => {
        if (!reconnecting) return;
        const timer = window.setTimeout(() => setReconnectSlow(true), RECONNECT_QUIET_MS);
        return () => { window.clearTimeout(timer); setReconnectSlow(false); };
    }, [reconnecting]);
    const connectionLabel = connectionStatus === "connected" || (reconnecting && !reconnectSlow)
        ? controls.connection.connected : reconnecting ? controls.connection.reconnecting : controls.connection[connectionStatus];
    const connectionTone = connectionStatus === "connected" || (reconnecting && !reconnectSlow) ? "connected"
        : connectionStatus === "connecting" || reconnecting ? "connecting" : "offline";
    // The stream is available while connected, or during a short drop. Then the typing
    // indicator (or the draft) is the only progress element, and the card stays hidden.
    const streamAvailable = connectionStatus === "connected" || (reconnecting && !reconnectSlow);
    const pending = recoveryTurns.filter((turn) => isTurnInProgress(turn.status));
    // Every tab shows a turn in progress the same way: one element, inline below the user message at
    // the bottom of the thread, the typing bubble until a draft exists and then the draft.
    const showTyping = !assistantDraft && (pending.length > 0 || (isTyping && streamAvailable));
    const [slowTurnId, setSlowTurnId] = useState<string | null>(null);
    const pendingId = pending[0]?.client_message_id ?? null;
    useEffect(() => {
        if (!pendingId || assistantDraft) return;
        const timer = window.setTimeout(() => setSlowTurnId(pendingId), SLOW_TURN_MS);
        return () => window.clearTimeout(timer);
    }, [pendingId, assistantDraft]);
    const showSlowNote = showTyping && pendingId !== null && slowTurnId === pendingId;
    const newChat = locale === "es-MX" ? "Nueva conversación" : "New chat";
    const openNora = (conversationId: string = todayConversationId()) => {
        openConversation(conversationId);
        setCareTeamOpened(true); setConversation("assistant"); setInbox(false);
    };
    const historicalMessages = messages.filter((message) => message.role === ChatRole.CLINICIAN);
    const visibleMessages = messages.filter((message) => message.role !== ChatRole.CLINICIAN)
        .map((message) => message.id === "welcome-message"
            ? { ...message, content: copy.welcomeMessage, language: locale, audioUrl: undefined }
            : message);
    const voiceBusy = ["listening", "processing", "playing"].includes(voiceStatus);
    const back = locale === "es-MX" ? "Volver a mensajes" : "Back to messages";
    const threadOpen = (!inbox && conversation === "assistant") || Boolean(humanThreadId) || followUpMode;

    useEffect(() => {
        setConversationOpen(threadOpen);
        return () => setConversationOpen(false);
    }, [threadOpen, setConversationOpen]);

    useEffect(() => {
        if (followUpMode) headingRef.current?.focus();
        else if (wasFollowUp.current) noraOpenRef.current?.focus();
        wasFollowUp.current = followUpMode;
    }, [followUpMode]);

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

    const assistantThread = !inbox && conversation === "assistant";
    const iconButton = "ma-press flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-surface text-ink-2 hover:bg-surface-2 disabled:opacity-50";
    if (followUpMode) {
        const followUpCopy = getADRFollowUpCopy(locale);
        const leaveFollowUp = () => { setInbox(true); setCareTeamOpened(true); router.replace("/chat"); };
        return <div className="flex min-h-dvh w-full flex-col gap-3 px-4 pb-[calc(env(safe-area-inset-bottom)+24px)] text-ink" lang={locale}>
            <header className="sticky top-0 z-20 -mx-4 flex items-center gap-2.5 bg-background/90 px-3 pt-3 pb-2.5 backdrop-blur-md">
                <button type="button" className="ma-press flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-ink hover:bg-surface" aria-label={back} onClick={leaveFollowUp}><Icon name="back" className="h-[22px] w-[22px]" /></button>
                <div className="min-w-0 flex-1">
                    <h1 ref={headingRef} tabIndex={-1} className="break-words text-base font-semibold leading-tight outline-none">{followUpCopy.entry.title}</h1>
                </div>
            </header>
            <p className="flex items-start gap-2 rounded-2xl bg-danger-tint px-3.5 py-2.5 text-[13px] leading-snug text-danger-ink"><Icon name="alert" className="mt-px h-4 w-4 shrink-0" />{controls.caution}</p>
            <ADRFollowUpView locale={profile ? locale : undefined} timeZone={profile?.timezone} requestId={followUpRequestId} assessmentId={followUpAssessmentId} onBack={leaveFollowUp} />
        </div>;
    }
    return <div className={`flex w-full flex-col text-ink ${threadOpen ? "min-h-dvh" : "min-h-[calc(100dvh-110px)]"} ${assistantThread ? "gap-3 px-4 pb-0" : humanThreadId ? "gap-4 px-4 pt-4 pb-0" : "gap-4 px-4 pt-4 pb-6"}`} lang={locale}>
        <header hidden={Boolean(humanThreadId)} className={inbox ? "flex items-center justify-between gap-3 px-1.5" : "sticky top-0 z-20 -mx-4 flex items-center gap-2.5 bg-background/90 px-3 pt-3 pb-2.5 backdrop-blur-md"}>
            {!inbox && <button type="button" className="ma-press flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-ink hover:bg-surface disabled:opacity-50" aria-label={back} disabled={voiceBusy} onClick={() => { setInbox(true); setCareTeamOpened(true); }}><Icon name="back" className="h-[22px] w-[22px]" /></button>}
            {!inbox && conversation === "assistant" && <span aria-hidden="true" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-deep text-gold"><Icon name="spark" className="h-[18px] w-[18px]" /></span>}
            <div className="min-w-0 flex-1">
            <h1 ref={headingRef} tabIndex={-1} className={inbox ? "break-words pt-0 text-[32px] font-semibold leading-[1.1] tracking-[-0.02em] outline-none" : "break-words text-base font-semibold leading-tight outline-none"}>{inbox ? "Chat" : conversation === "assistant" ? CARE_ASSISTANT_NAME : copy.careTeamLabel}</h1>
            {!inbox && conversation === "assistant" && <>
                <p className="flex flex-wrap items-center gap-x-1.5 text-xs text-muted"><span>{copy.assistantDescription}</span><span aria-hidden="true">·</span><span role="status" className={`inline-flex items-center gap-1 ${connectionTone === "connected" ? "text-brand-ink" : connectionTone === "connecting" ? "text-muted" : "text-danger-ink"}`}><span aria-hidden="true" className={`h-1.5 w-1.5 shrink-0 rounded-full ${connectionTone === "connected" ? "bg-brand" : connectionTone === "connecting" ? "bg-gold" : "bg-danger-seg"}`} />{connectionLabel}</span></p>
            </>}
            </div>
            {inbox && !humanThreadId && <NotificationBell />}
            {!inbox && <button type="button" aria-label={conversation === "assistant" ? copy.careTeamLabel : `${CARE_ASSISTANT_NAME} · ${copy.assistantDescription}`} aria-pressed={false} disabled={voiceBusy}
                className={iconButton}
                onClick={() => { setCareTeamOpened(true); setConversation(conversation === "assistant" ? "care-team" : "assistant"); }}>
                <Icon name={conversation === "assistant" ? "users" : "spark"} className="h-5 w-5" />
            </button>}
            {!inbox && conversation === "assistant" && <button type="button" className={iconButton} aria-label={newChat} title={newChat} disabled={voiceBusy || isTyping} onClick={startNewConversation}><Icon name="plus" className="h-5 w-5" /></button>}
            {!inbox && conversation === "assistant" && <button className={`${iconButton} ${handsFreeMode ? "!bg-brand !text-white" : ""}`} aria-label={handsFreeMode ? controls.handsFreeOn : controls.handsFreeOff} aria-pressed={handsFreeMode} onClick={handleHandsFreeToggle} type="button"><Icon name="speaker" className="h-5 w-5" /></button>}
        </header>
        {inbox ? <section hidden={Boolean(humanThreadId)} className="relative flex flex-col gap-4 overflow-hidden rounded-[28px] bg-brand-deep p-5 text-[#F2F7F5] shadow-[var(--shadow-nora)]">
            <span aria-hidden="true" className="pointer-events-none absolute -right-[60px] -top-[60px] h-[200px] w-[200px] rounded-full bg-[radial-gradient(circle,rgba(245,196,106,.28),transparent_70%)]" />
            <div className="relative flex items-center gap-3">
                <span aria-hidden="true" className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-white/20 bg-white/10 text-gold"><Icon name="spark" className="h-[22px] w-[22px]" /></span>
                <div className="min-w-0 flex-1 break-words"><h2 className="flex items-center gap-2 text-[19px] font-semibold leading-tight">{CARE_ASSISTANT_NAME} <span className="rounded-md bg-[rgba(245,196,106,.18)] px-1.5 py-0.5 text-[11px] font-semibold tracking-[0.06em] text-gold">AI</span></h2><p className="mt-0.5 text-[13px] text-[#B9D1CC]">{copy.assistantDescription} · {locale === "es-MX" ? "no es un profesional clínico" : "not a clinician"}</p></div>
            </div>
            <p className="relative text-[15px] leading-relaxed text-[#E4EEEB]">{controls.caution}</p>
            <div className="relative flex flex-wrap gap-2">
            <button type="button" className="ma-press min-h-11 rounded-full bg-gold px-4 py-2 text-sm font-semibold text-[#2B1F05] hover:bg-[#F7CD80]" onClick={() => { openNora(); setInput(copy.quickPrompts[1]); }}>{locale === "es-MX" ? "Reportar un síntoma" : "Report a symptom"}</button>
            <button ref={noraOpenRef} type="button" aria-label={`${CARE_ASSISTANT_NAME} · ${copy.assistantDescription}`} aria-pressed={false} className="ma-press inline-flex min-h-11 items-center gap-1.5 rounded-full border border-white/15 bg-white/10 px-4 py-2 text-sm font-semibold text-white hover:bg-white/15" onClick={() => openNora()}>{locale === "es-MX" ? "Abrir chat" : "Open chat"}<Icon name="arrow" className="h-4 w-4" /></button>
            </div>
        </section> : null}
        {inbox && <div hidden={Boolean(humanThreadId)} className="empty:hidden"><ADRFollowUpEntryRow locale={locale} /></div>}
        {inbox && !humanThreadId && <NoraConversations locale={locale} activeSessionId={sessionId} onOpen={openNora} />}
        {(inbox || careTeamOpened) && <div hidden={!inbox && conversation !== "care-team"} className="space-y-3">
            <CareConversations compact locale={locale} conversationId={conversationId} recipientId={recipientId} visible={inbox || conversation === "care-team"} onThreadPresentationChange={setHumanThreadId} />
            {historicalMessages.length > 0 && <section hidden={Boolean(humanThreadId)} className="overflow-hidden rounded-[22px] bg-surface">
                <button className="flex min-h-14 w-full items-center gap-3 px-[14px] py-3 text-left hover:bg-[#FBF7F0]" type="button" aria-expanded={showHistory}
                    onClick={() => setShowHistory((current) => !current)}>
                    <span aria-hidden="true" className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[13px] bg-surface-2 text-ink-2"><Icon name="history" className="h-5 w-5" /></span>
                    <span className="min-w-0 flex-1 text-[15px] font-medium text-ink">{copy.historicalCareTeamLabel} ({historicalMessages.length})</span>
                    <Icon name="chevronDown" className={`h-[18px] w-[18px] shrink-0 text-muted transition-transform duration-[240ms] ${showHistory ? "rotate-180" : ""}`} />
                </button>
                {showHistory && (inbox || conversation === "care-team") && <div className="ma-enter space-y-3 border-t border-line px-[14px] pt-3 pb-4">
                    <p className="text-[13px] leading-relaxed text-muted">{copy.historicalCareTeamIntro}</p>
                    {historicalMessages.map((message) => <ChatBubble key={message.id} role="clinician"
                        content={message.content} timestamp={message.createdAt} locale={locale}
                        language={message.language} clinicianLabel={copy.historicalCareTeamLabel} />)}
                </div>}
            </section>}
        </div>}
        {assistantThread && <>
            <p className="flex items-start gap-2 rounded-2xl bg-danger-tint px-3.5 py-2.5 text-[13px] leading-snug text-danger-ink"><Icon name="alert" className="mt-px h-4 w-4 shrink-0" />{controls.caution}</p>
            <div className="empty:hidden"><ADRFollowUpEntryRow locale={locale} /></div>
            {documentContext && <section className="flex items-start gap-3 rounded-[22px] bg-brand-tint p-3.5">
                <span aria-hidden="true" className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-surface text-brand"><Icon name="note" className="h-5 w-5" /></span>
                <div className="min-w-0 flex-1">
                    <p className="text-xs font-semibold text-brand-ink">{controls.recordContext}</p>
                    <p className="mt-0.5 break-words text-[15px] font-semibold [overflow-wrap:anywhere]">{documentContext.documentName}</p>
                    {documentContext.provider && <p className="mt-0.5 text-[13px] text-ink-2">{documentContext.provider}</p>}
                </div>
                <button className="ma-press min-h-11 shrink-0 rounded-xl px-3 text-sm font-semibold text-brand-ink hover:bg-surface/70" onClick={dismissDocumentContext} type="button">{controls.dismiss}</button>
            </section>}
            {!documentContext && documentUnavailable && <div className="rounded-2xl bg-surface px-3.5 py-2.5 text-[13px] text-ink-2" role="status"><p>{controls.documentUnavailable}</p><button type="button" className="min-h-11 px-3 font-semibold text-brand-ink" onClick={dismissDocumentContext}>{controls.dismiss}</button></div>}
            {error && <div className="rounded-2xl bg-danger-tint p-3.5 text-sm text-danger-ink" role="alert">
                <p>{error === "CHAT_TURN_BUSY" ? recoveryCopy.busy : error === "CHAT_TURN_EXPIRED" ? recoveryCopy.expired : error === "CHAT_STARTUP_UNAVAILABLE" ? recoveryCopy.unavailable : controls.chatError}</p>
                {error === "CHAT_STARTUP_UNAVAILABLE" && <button type="button" className="mt-2 min-h-11 rounded-xl bg-surface px-3 font-semibold" onClick={reconnectChat}>{recoveryCopy.reconnect}</button>}
            </div>}
            {safetyNotice && <div className="flex items-start gap-3 rounded-2xl border border-danger-ink/20 bg-danger-tint p-3.5 text-sm text-danger-ink" role="alert">
                <Icon name="alert" className="mt-px h-5 w-5 shrink-0" />
                <p className="flex-1 font-medium">{copy.escalationNotice}</p>
                <button className="ma-press min-h-11 shrink-0 rounded-xl bg-surface px-3 text-sm font-semibold text-danger-ink" onClick={dismissSafetyNotice} type="button">{controls.dismiss}</button>
            </div>}
            {voiceError && <p className="rounded-2xl bg-danger-tint p-3.5 text-sm text-danger-ink" role="alert">{controls.voiceError}</p>}
            <div className="flex flex-1 flex-col gap-3 pt-1" aria-busy={loading}>
                {loading && <p className="text-center text-sm text-muted" role="status">{controls.loading}</p>}
                {visibleMessages.map((message) => <ChatBubble key={message.clientMessageId ?? message.id} attachments={message.role === ChatRole.ASSISTANT ? message.attachments : undefined} content={message.content}
                    language={message.language} locale={locale} role={message.role === ChatRole.USER ? "user" : "assistant"}
                    delivery={message.delivery} onRetrySend={message.clientMessageId ? () => retryUnsentMessage(message.clientMessageId!) : undefined}
                    onRemoveUnsent={message.clientMessageId ? () => removeUnsentMessage(message.clientMessageId!) : undefined}
                    timestamp={message.createdAt} onPlayAudio={message.role === ChatRole.ASSISTANT && (Boolean(message.audioUrl) || canPlayAssistantAudio) ? () => handlePlayAssistantMessage(message) : undefined} />)}
                {!loading && !documentContext && !messages.some((message) => message.role === ChatRole.USER) && <section className="ma-enter space-y-2.5 pt-1">
                    <p className="px-1 text-[13px] text-muted">{copy.emptyStateIntro}</p>
                    <div className="flex flex-col items-start gap-2">{copy.quickPrompts.map((prompt) => <button className="ma-press min-h-11 rounded-full border border-line-strong bg-surface px-4 py-2 text-left text-sm font-medium text-ink-2 hover:border-brand/40 hover:text-brand-ink" key={prompt} type="button" onClick={() => setInput(prompt)}>{prompt}</button>)}</div>
                </section>}
                {assistantDraft && <ChatBubble content={assistantDraft} isStreaming language={locale} locale={locale}
                    role="assistant" timestamp={assistantDraftStartedAt ?? new Date().toISOString()} />}
                {showTyping && <div className="ma-bubble flex items-center gap-2 self-start rounded-[20px_20px_20px_6px] bg-surface px-4 py-3" role="status"><ProcessingDots /><span className="text-[13px] text-muted">{copy.typingMessage}</span></div>}
                {showSlowNote && <p className="-mt-1 self-start px-1 text-xs text-muted">{recoveryCopy.leaveAndReturn}</p>}
                <ChatTurnRecovery turns={recoveryTurns} locale={locale} connected={connectionStatus === "connected"} onRetry={retryTurn} onDismiss={dismissTurn} />
                <div ref={bottomRef} />
            </div>
            <form className="sticky bottom-0 z-10 -mx-4 mt-auto space-y-1.5 bg-background/95 px-3 pt-2 pb-[calc(env(safe-area-inset-bottom)+12px)] backdrop-blur-md" onSubmit={handleSend}>
                <div className="flex items-end gap-2">
                    <div className="flex min-h-[52px] min-w-0 flex-1 items-end rounded-[26px] border border-line-strong bg-surface pr-1.5 pb-1.5 transition focus-within:border-brand focus-within:ring-4 focus-within:ring-brand/12">
                        <ChatTextarea aria-label={controls.message} className="pl-[18px]" onChange={(event) => setInput(event.target.value)}
                        onKeyDown={(event) => {
                            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                                event.preventDefault();
                                if (input.trim() && connectionStatus === "connected" && profile)
                                    event.currentTarget.form?.requestSubmit();
                            }
                        }}
                        placeholder={voiceStatus === "listening" ? controls.listening : voiceStatus === "processing" ? controls.transcribing : copy.inputPlaceholder} value={input} />
                    <button className={`ma-press flex h-10 w-10 shrink-0 items-center justify-center rounded-full disabled:opacity-40 ${voiceStatus === "listening" ? "bg-danger-ink text-white" : "bg-surface-2 text-ink-2 hover:bg-line-strong"}`} aria-label={voiceStatus === "listening" ? controls.stopVoice : voiceStatus === "playing" ? controls.interrupt : controls.speak} aria-pressed={voiceStatus === "listening"}
                        disabled={turnBusy || documentUnavailable || voiceStatus === "unsupported" || voiceStatus === "processing" || !profile} onClick={handleMicClick} type="button">
                        {voiceStatus === "listening" ? <HiStop aria-hidden className="h-5 w-5" /> : voiceStatus === "processing" ? <ProcessingDots /> : <Icon name="mic" className="h-5 w-5" />}
                    </button>
                    </div>
                    <button className="ma-press flex h-[52px] w-[52px] shrink-0 items-center justify-center rounded-full bg-brand text-white shadow-[var(--shadow-fab)] hover:bg-brand-hover disabled:opacity-40 disabled:shadow-none"
                        aria-label={controls.send} disabled={turnBusy || documentUnavailable || !input.trim() || connectionStatus !== "connected" || !profile} type="submit"><Icon name="send" /></button>
                </div>
                {handsFreeMode && <p className="px-2 text-xs text-brand-ink">{controls.autoPlay}</p>}
                {!profile && <p className="px-2 text-sm text-muted" role="status">{controls.profileRequired}</p>}
            </form>
        </>}
    </div>;
}
