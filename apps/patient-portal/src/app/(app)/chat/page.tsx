"use client";

import { useEffect, useRef } from "react";
import { getPatientChatCopy } from "@/content/chat-copy";
import {
    HiArrowUp,
    HiChevronDown,
    HiDocumentText,
    HiMicrophone,
    HiSparkles,
    HiStop,
} from "react-icons/hi2";
import { ChatBubble } from "@/components/features";
import { Button, Input } from "@/components/ui";
import { usePatientChatSession } from "@/hooks/use-patient-chat-session";
import {
    ChatRole,
    SUPPORTED_LOCALES,
    getLocaleLabel,
    getLocaleSelectorLabel,
    type Locale as ChatLocale,
} from "@/types";

function getConnectionLabel(
    connectionStatus: "idle" | "connected" | "connecting" | "disconnected" | "error",
): string {
    if (connectionStatus === "connected") {
        return "Online";
    }
    if (connectionStatus === "connecting") {
        return "Connecting";
    }
    if (connectionStatus === "error") {
        return "Connection issue";
    }
    return "Offline";
}

function formatSessionTimeLabel(locale: ChatLocale): string {
    return new Intl.DateTimeFormat(locale, {
        dateStyle: "medium",
        timeStyle: "short",
    }).format(new Date());
}

export default function ChatPage() {
    const bottomRef = useRef<HTMLDivElement | null>(null);
    const {
        assistantDraft,
        assistantDraftStartedAt,
        canPlayAssistantAudio,
        connectionStatus,
        dismissDocumentContext,
        dismissSafetyNotice,
        documentContext,
        error,
        handleLanguageSelection,
        handleMicClick,
        handlePlayAssistantMessage,
        handleSend,
        handleVoiceModeToggle,
        input,
        isTyping,
        loading,
        messages,
        safetyNotice,
        selectedLanguage,
        setInput,
        voiceError,
        voiceInterimTranscript,
        voiceModeEnabled,
        voiceStatus,
    } = usePatientChatSession();
    const sessionTimeLabel = formatSessionTimeLabel(selectedLanguage);

    const chatCopy = getPatientChatCopy(selectedLanguage);
    const quickPrompts = chatCopy.quickPrompts;
    const showQuickPrompts =
        !loading
        && !documentContext
        && !messages.some((message) => message.role === ChatRole.USER);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [assistantDraft, isTyping, messages]);

    return (
        <div className="patient-page min-h-full px-3 py-4 text-[#17233a] sm:px-6 sm:py-6">
            <div className="mx-auto flex min-h-full max-w-[28rem] flex-col">
                <div className="rounded-[32px] border border-white/70 bg-white/88 px-4 pt-5 pb-4 shadow-[0_18px_48px_rgba(42,58,84,0.10)] ring-1 ring-[#eadfd4]/70 backdrop-blur sm:px-5">
                    <div className="flex items-start justify-between gap-4">
                        <div className="flex items-start gap-3">
                            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-[#b6d9d2] bg-[#e6f4f1] text-sm text-[#147465] shadow-[0_12px_26px_rgba(20,116,101,0.12)]">
                                <HiSparkles className="h-5 w-5" />
                            </div>
                            <div className="space-y-1">
                                <h1 className="text-[1.45rem] font-black tracking-[-0.03em] text-[#17233a]">
                                    Care Companion
                                </h1>
                                <p className="inline-flex items-center gap-2 text-sm font-medium text-[#64748b]">
                                    <span
                                        className={`h-2 w-2 rounded-full ${
                                            connectionStatus === "connected"
                                                ? "bg-emerald-400"
                                                : connectionStatus === "connecting"
                                                  ? "bg-amber-400"
                                                  : "bg-rose-500"
                                        }`}
                                    />
                                    {getConnectionLabel(connectionStatus)}
                                </p>
                            </div>
                        </div>
                        <div
                            aria-label="Chat language"
                            className="inline-flex rounded-full border border-[#d9cbc0] bg-[#fffaf4] p-1 shadow-[0_10px_24px_rgba(42,58,84,0.08)]"
                            role="group"
                        >
                            {SUPPORTED_LOCALES.map((locale) => {
                                const isActive = selectedLanguage === locale;
                                return (
                                    <button
                                        aria-pressed={isActive}
                                        className={`min-h-9 rounded-full px-3 py-1.5 text-xs font-bold transition ${
                                            isActive
                                                ? "bg-[#147465] text-white"
                                                : "text-[#5b6b83] hover:bg-white"
                                        }`}
                                        key={locale}
                                        onClick={() => handleLanguageSelection(locale)}
                                        type="button"
                                    >
                                        {getLocaleSelectorLabel(locale)}
                                    </button>
                                );
                            })}
                            <span className="pointer-events-none flex items-center px-1 text-[#8090a5]">
                                <HiChevronDown className="h-3.5 w-3.5" />
                            </span>
                        </div>
                    </div>
                </div>

                <div className="mt-4 flex-1 overflow-y-auto px-1 pb-4">
                    <div className="mx-auto w-fit rounded-full border border-[#eadfd4] bg-white/82 px-3 py-1 text-[11px] font-bold text-[#64748b] shadow-[0_10px_24px_rgba(42,58,84,0.08)]">
                        {sessionTimeLabel}
                    </div>

                    <div className="mt-4 space-y-4">
                        {documentContext ? (
                            <div className="rounded-[26px] border border-[#b6d9d2] bg-[#e6f4f1] p-4 shadow-[0_18px_40px_rgba(20,116,101,0.10)]">
                                <div className="flex items-start justify-between gap-3">
                                    <div className="flex items-start gap-3">
                                        <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-[#b6d9d2] bg-white text-[#147465]">
                                            <HiDocumentText className="h-5 w-5" />
                                        </div>
                                        <div className="space-y-1">
                                            <p className="text-[11px] font-black uppercase tracking-[0.22em] text-[#147465]">
                                                Record context attached
                                            </p>
                                            <p className="text-base font-bold text-[#17233a]">
                                                {documentContext.documentName}
                                            </p>
                                            <p className="text-sm leading-6 text-[#5b6b83]">
                                                {chatCopy.documentContextIntro} {getLocaleLabel(documentContext.preferredLanguage)}
                                                {documentContext.provider
                                                    ? ` about ${documentContext.provider}`
                                                    : ""}
                                                {chatCopy.documentContextSuffix}
                                            </p>
                                        </div>
                                    </div>
                                    <button
                                        className="min-h-10 rounded-full border border-[#b6d9d2] bg-white px-3 py-1 text-xs font-bold text-[#147465] transition hover:bg-[#fffaf4]"
                                        onClick={dismissDocumentContext}
                                        type="button"
                                    >
                                        Dismiss
                                    </button>
                                </div>
                            </div>
                        ) : null}

                        {error ? (
                            <div className="rounded-[20px] border border-[#efbeb5] bg-[#fff2ef] px-4 py-3 text-sm font-semibold text-[#b94032]">
                                {error}
                            </div>
                        ) : null}

                        {safetyNotice ? (
                            <div
                                className="rounded-[20px] border border-[#F6D49A] bg-[#FFF7E8] px-4 py-3 text-sm text-[#7A4C00]"
                                role="alert"
                            >
                                <div className="flex items-start justify-between gap-3">
                                    <p>{safetyNotice}</p>
                                    <button
                                        className="rounded-full border border-[#F0D7AA] bg-white/70 px-3 py-1 text-xs font-semibold text-[#7A4C00] transition hover:bg-white"
                                        onClick={dismissSafetyNotice}
                                        type="button"
                                    >
                                        Dismiss
                                    </button>
                                </div>
                            </div>
                        ) : null}

                        {voiceError ? (
                            <div className="rounded-[20px] border border-[#efbeb5] bg-[#fff2ef] px-4 py-3 text-sm font-semibold text-[#b94032]">
                                {voiceError}
                            </div>
                        ) : null}

                        {showQuickPrompts ? (
                            <div className="space-y-3">
                                <div className="rounded-[24px] border border-white/70 bg-white/86 px-4 py-3 text-base leading-7 text-[#42526b] shadow-[0_16px_32px_rgba(42,58,84,0.08)]">
                                    {chatCopy.emptyStateIntro}
                                </div>
                                <div className="flex flex-col gap-2">
                                    {quickPrompts.map((prompt) => (
                                        <button
                                            className="min-h-12 rounded-[20px] border border-[#d9cbc0] bg-white/88 px-4 py-3 text-left text-base text-[#30415f] shadow-[0_10px_24px_rgba(42,58,84,0.06)] transition hover:bg-[#fffaf4]"
                                            key={prompt}
                                            onClick={() => setInput(prompt)}
                                            type="button"
                                        >
                                            {prompt}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        ) : null}

                        <div className="space-y-4">
                            {loading && messages.length === 0 ? (
                                <div className="rounded-[20px] border border-[#eadfd4] bg-white/88 px-4 py-3 text-base text-[#64748b] shadow-[0_14px_30px_rgba(42,58,84,0.08)]">
                                    Loading conversation...
                                </div>
                            ) : null}

                            {messages.map((message) => (
                                <ChatBubble
                                    content={message.content}
                                    key={message.id}
                                    language={message.language}
                                    onPlayAudio={
                                        message.role === ChatRole.ASSISTANT
                                        && (Boolean(message.audioUrl) || canPlayAssistantAudio)
                                            ? () => handlePlayAssistantMessage(message)
                                            : undefined
                                    }
                                    role={message.role === ChatRole.USER ? "user" : "assistant"}
                                    timestamp={message.createdAt}
                                />
                            ))}

                            {assistantDraft ? (
                                <ChatBubble
                                    content={assistantDraft}
                                    isStreaming
                                    language={selectedLanguage}
                                    role="assistant"
                                    timestamp={assistantDraftStartedAt ?? new Date().toISOString()}
                                />
                            ) : null}

                            {isTyping && !assistantDraft ? (
                                <div className="w-fit rounded-full border border-[#eadfd4] bg-white/88 px-3 py-2 text-xs font-bold text-[#64748b] shadow-[0_10px_24px_rgba(42,58,84,0.08)]">
                                    Care Companion is typing...
                                </div>
                            ) : null}
                            <div ref={bottomRef} />
                        </div>
                    </div>
                </div>

                <form
                    className="sticky bottom-28 mt-2 rounded-[30px] border border-white/75 bg-white/92 px-4 py-4 shadow-[0_20px_48px_rgba(42,58,84,0.14)] ring-1 ring-[#eadfd4]/80 backdrop-blur sm:px-5"
                    onSubmit={handleSend}
                >
                    <div className="rounded-[26px] bg-[#fffaf4] p-2.5">
                        <Button
                            className="mx-auto mb-3 block rounded-full border-0 bg-[#30415f] px-4 py-2 text-sm font-bold text-white shadow-[0_12px_22px_rgba(48,65,95,0.22)] hover:bg-[#17233a]"
                            onClick={handleVoiceModeToggle}
                            type="button"
                            variant="ghost"
                        >
                            {voiceModeEnabled
                                ? "Stop Voice-to-Voice Mode"
                                : "Start Voice-to-Voice Mode"}
                        </Button>

                        {voiceModeEnabled ? (
                            <div className="mb-3 rounded-[20px] border border-[#b6d9d2] bg-[#e6f4f1] px-4 py-3 text-sm leading-6 text-[#147465]">
                                Voice mode is on. Your speech sends as a message, and assistant replies play back automatically when audio is available.
                            </div>
                        ) : null}

                        <div className="flex items-end gap-3">
                            <button
                                aria-label={
                                    voiceStatus === "listening"
                                        ? "Stop voice recording"
                                        : "Start voice recording"
                                }
                                className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full border shadow-[0_12px_22px_rgba(70,96,140,0.12)] transition ${
                                    voiceStatus === "listening"
                                        ? "border-[#efbeb5] bg-[#fff2ef] text-[#b94032]"
                                        : "border-[#d9cbc0] bg-white text-[#30415f]"
                                }`}
                                onClick={handleMicClick}
                                type="button"
                            >
                                {voiceStatus === "listening" ? (
                                    <HiStop className="h-5 w-5" />
                                ) : (
                                    <HiMicrophone className="h-5 w-5" />
                                )}
                            </button>
                            <div className="flex-1 rounded-[24px] border border-[#d9cbc0] bg-white px-1 py-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.8)]">
                                <Input
                                    className="border-0 bg-transparent px-3 py-3 text-[#17233a] shadow-none placeholder:text-[#8d9bae] focus:border-0 focus:ring-0"
                                    onChange={(event) => setInput(event.target.value)}
                                    placeholder={chatCopy.inputPlaceholder}
                                    value={input}
                                />
                            </div>
                            <button
                                aria-label="Send message"
                                className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-[#147465] text-white shadow-[0_14px_28px_rgba(20,116,101,0.24)] transition hover:bg-[#0f5f53] disabled:cursor-not-allowed disabled:bg-[#d7dce5] disabled:text-[#8090a5] disabled:shadow-none"
                                disabled={!input.trim() || connectionStatus !== "connected"}
                                type="submit"
                            >
                                <HiArrowUp className="h-5 w-5" />
                            </button>
                        </div>

                        {voiceInterimTranscript ? (
                            <p className="mt-3 text-sm text-[#64748b]">
                                Listening:{" "}
                                <span className="font-semibold text-[#17233a]">{voiceInterimTranscript}</span>
                            </p>
                        ) : null}
                    </div>
                </form>
            </div>
        </div>
    );
}
