"use client";

import { useEffect, useRef, useState } from "react";
import { HiArrowUp, HiMicrophone, HiSpeakerWave, HiStop } from "react-icons/hi2";
import { CARE_ASSISTANT_NAME, getPatientChatCopy, getChatControlsCopy } from "@/content/chat-copy";
import { CareConversations } from "@/components/features/care-conversations";
import { ChatBubble } from "@/components/features";
import { Input } from "@/components/ui";
import { usePatientChatSession } from "@/hooks/use-patient-chat-session";
import { usePatientProfile } from "@/hooks/use-patient-profile";
import { ChatRole, DEFAULT_LOCALE } from "@/types";

export default function ChatPage() {
    const profile = usePatientProfile();
    const locale = profile?.preferredLanguage ?? DEFAULT_LOCALE;
    const copy = getPatientChatCopy(locale);
    const controls = getChatControlsCopy(locale);
    const [conversation, setConversation] = useState<"assistant" | "care-team">("assistant");
    const [careTeamOpened, setCareTeamOpened] = useState(false);
    const [showHistory, setShowHistory] = useState(false);
    const bottomRef = useRef<HTMLDivElement | null>(null);
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
    const button = "min-h-11 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 focus-visible:outline-2 focus-visible:outline-blue-600 disabled:opacity-50";

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }, [assistantDraft, isTyping, messages, conversation]);

    return <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col gap-4 px-3 py-4 text-gray-900 sm:px-6 sm:py-6" lang={locale}>
        <header className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <h1 className="text-2xl font-bold">{conversation === "assistant" ? CARE_ASSISTANT_NAME : copy.careTeamLabel}</h1>
            {conversation === "assistant" && <>
                <p className="mt-1 text-sm text-gray-500">{copy.assistantDescription}</p>
                <p className="mt-2 text-xs text-gray-500" role="status">{controls.connection[connectionStatus]}</p>
            </>}
        </header>
        <div className="grid grid-cols-2 gap-2" role="group" aria-label={copy.careTeamLabel}>
            <button type="button" aria-pressed={conversation === "assistant"}
                className={button + (conversation === "assistant" ? " border-blue-600 bg-blue-50 text-blue-800" : "")}
                onClick={() => setConversation("assistant")}>
                {CARE_ASSISTANT_NAME} · {copy.assistantDescription}
            </button>
            <button type="button" aria-pressed={conversation === "care-team"} disabled={voiceBusy}
                className={button + (conversation === "care-team" ? " border-blue-600 bg-blue-50 text-blue-800" : "")}
                onClick={() => { setCareTeamOpened(true); setConversation("care-team"); }}>
                {copy.careTeamLabel}
            </button>
        </div>
        {careTeamOpened && <div hidden={conversation !== "care-team"} className="space-y-4">
            <CareConversations locale={locale} visible={conversation === "care-team"} />
            {historicalMessages.length > 0 && <section className="space-y-3 rounded-xl border border-gray-200 bg-white p-5">
                <button className={button} type="button" aria-expanded={showHistory}
                    onClick={() => setShowHistory((current) => !current)}>
                    {copy.historicalCareTeamLabel} ({historicalMessages.length})
                </button>
                {showHistory && conversation === "care-team" && <>
                    <p className="text-sm text-gray-500">{copy.historicalCareTeamIntro}</p>
                    {historicalMessages.map((message) => <ChatBubble key={message.id} role="clinician"
                        content={message.content} timestamp={message.createdAt} locale={locale}
                        language={message.language} clinicianLabel={copy.historicalCareTeamLabel} />)}
                </>}
            </section>}
        </div>}
        {conversation === "assistant" && <>
            <p className="rounded-lg bg-yellow-100 p-3 text-sm text-yellow-800">{controls.caution}</p>
            {documentContext && <section className="rounded-xl border border-blue-100 bg-blue-50 p-4">
                <p className="text-xs font-semibold text-blue-800">{controls.recordContext}</p>
                <p className="mt-1 break-words font-semibold">{documentContext.documentName}</p>
                {documentContext.provider && <p className="mt-1 text-sm text-gray-700">{documentContext.provider}</p>}
                <button className={button + " mt-3"} onClick={dismissDocumentContext} type="button">{controls.dismiss}</button>
            </section>}
            {error && <p className="rounded-lg bg-red-100 p-3 text-sm text-red-800" role="alert">{controls.chatError}</p>}
            {safetyNotice && <div className="flex items-start gap-3 rounded-lg bg-yellow-100 p-3 text-sm text-yellow-800" role="alert">
                <p className="flex-1">{copy.escalationNotice}</p>
                <button className={button} onClick={dismissSafetyNotice} type="button">{controls.dismiss}</button>
            </div>}
            {voiceError && <p className="rounded-lg bg-red-100 p-3 text-sm text-red-800" role="alert">{controls.voiceError}</p>}
            <div className="flex-1 space-y-4" aria-busy={loading}>
                {loading && <p className="text-sm text-gray-500" role="status">{controls.loading}</p>}
                {!loading && !documentContext && !messages.some((message) => message.role === ChatRole.USER) && <section className="space-y-3 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
                    <p className="text-sm text-gray-700">{copy.emptyStateIntro}</p>
                    <div className="flex flex-col gap-2">{copy.quickPrompts.map((prompt) => <button className={button + " text-left"} key={prompt} type="button" onClick={() => setInput(prompt)}>{prompt}</button>)}</div>
                </section>}
                {visibleMessages.map((message) => <ChatBubble key={message.id} content={message.content}
                    language={message.language} locale={locale} role={message.role === ChatRole.USER ? "user" : "assistant"}
                    timestamp={message.createdAt} onPlayAudio={message.role === ChatRole.ASSISTANT && (Boolean(message.audioUrl) || canPlayAssistantAudio) ? () => handlePlayAssistantMessage(message) : undefined} />)}
                {assistantDraft && <ChatBubble content={assistantDraft} isStreaming language={locale} locale={locale}
                    role="assistant" timestamp={assistantDraftStartedAt ?? new Date().toISOString()} />}
                {isTyping && !assistantDraft && <p className="text-sm text-gray-500" role="status">{copy.typingMessage}</p>}
                <div ref={bottomRef} />
            </div>
            <form className="sticky bottom-0 z-10 space-y-3 rounded-xl border border-gray-200 bg-white p-3 shadow-sm sm:p-4" onSubmit={handleSend}>
                <div className="flex items-end gap-2">
                    <div className="min-w-0 flex-1"><Input aria-label={controls.message} onChange={(event) => setInput(event.target.value)}
                        placeholder={voiceStatus === "listening" ? controls.listening : voiceStatus === "processing" ? controls.transcribing : copy.inputPlaceholder} value={input} /></div>
                    <button className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-blue-600 text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 disabled:opacity-50"
                        aria-label={controls.send} disabled={!input.trim() || connectionStatus !== "connected" || !profile} type="submit"><HiArrowUp aria-hidden className="h-5 w-5" /></button>
                </div>
                <div className="flex flex-wrap gap-2">
                    <button className={button + " inline-flex items-center gap-2"} aria-pressed={voiceStatus === "listening"}
                        disabled={voiceStatus === "unsupported" || voiceStatus === "processing" || !profile} onClick={handleMicClick} type="button">
                        {voiceStatus === "listening" ? <HiStop aria-hidden className="h-5 w-5" /> : <HiMicrophone aria-hidden className="h-5 w-5" />}
                        {voiceStatus === "listening" ? controls.stopVoice : voiceStatus === "playing" ? controls.interrupt : controls.speak}
                    </button>
                    <button className={button + " inline-flex items-center gap-2"} aria-pressed={handsFreeMode} onClick={handleHandsFreeToggle} type="button">
                        <HiSpeakerWave aria-hidden className="h-5 w-5" />{handsFreeMode ? controls.handsFreeOn : controls.handsFreeOff}
                    </button>
                </div>
                {handsFreeMode && <p className="text-xs text-gray-500">{controls.autoPlay}</p>}
                {!profile && <p className="text-sm text-gray-500" role="status">{controls.profileRequired}</p>}
            </form>
        </>}
    </div>;
}
