"use client";

import { useEffect, useRef } from "react";
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
import { ChatRole, Locale, isSpanishLocale, type Locale as ChatLocale } from "@/types";

function getLanguageLabel(locale: ChatLocale): string {
    return isSpanishLocale(locale) ? "Español (México)" : "English (US)";
}

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

function buildQuickPrompts(locale: ChatLocale): string[] {
    if (isSpanishLocale(locale)) {
        return [
            "Explica mis resultados recientes",
            "¿Debo preocuparme por este síntoma?",
            "Ayúdame a preparar preguntas para mi médico",
        ];
    }

    return [
        "Explain my recent results",
        "Should I worry about this symptom?",
        "Help me prepare questions for my doctor",
    ];
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
        selectedLanguage,
        setInput,
        voiceError,
        voiceInterimTranscript,
        voiceModeEnabled,
        voiceStatus,
    } = usePatientChatSession();
    const sessionTimeLabel = formatSessionTimeLabel(selectedLanguage);

    const quickPrompts = buildQuickPrompts(selectedLanguage);
    const showQuickPrompts =
        !loading
        && !documentContext
        && !messages.some((message) => message.role === ChatRole.USER);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [assistantDraft, isTyping, messages]);

    return (
        <div className="min-h-full bg-[#F5F8FE] px-3 py-4 text-[#23324A] sm:px-6 sm:py-6">
            <div className="mx-auto flex min-h-full max-w-[28rem] flex-col">
                <div className="rounded-[28px] border border-[#E3EBF7] bg-white px-4 pt-5 pb-4 shadow-[0_18px_40px_rgba(70,96,140,0.10)] sm:px-5">
                    <div className="flex items-start justify-between gap-4">
                        <div className="flex items-start gap-3">
                            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-[#DCE6F3] bg-[#F6FAFF] text-sm text-[#1B95E0] shadow-[0_12px_26px_rgba(80,119,177,0.12)]">
                                <HiSparkles className="h-5 w-5" />
                            </div>
                            <div className="space-y-1">
                                <h1 className="text-[1.35rem] font-semibold tracking-[-0.02em] text-[#16263F]">
                                    Care Companion
                                </h1>
                                <p className="inline-flex items-center gap-2 text-sm text-[#6E829F]">
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
                            className="inline-flex rounded-full border border-[#D9E4F2] bg-[#FBFCFF] p-1 shadow-[0_10px_24px_rgba(70,96,140,0.08)]"
                            role="group"
                        >
                            {[Locale.EN_US, Locale.ES_MX].map((locale) => {
                                const isActive = selectedLanguage === locale;
                                return (
                                    <button
                                        aria-pressed={isActive}
                                        className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                                            isActive
                                                ? "bg-[#EADFFF] text-[#5F4A90]"
                                                : "text-[#5E6F8D] hover:bg-[#F4F8FD]"
                                        }`}
                                        key={locale}
                                        onClick={() => handleLanguageSelection(locale)}
                                        type="button"
                                    >
                                        {locale === Locale.EN_US ? "EN" : "ES"}
                                    </button>
                                );
                            })}
                            <span className="pointer-events-none flex items-center px-1 text-[#7389A8]">
                                <HiChevronDown className="h-3.5 w-3.5" />
                            </span>
                        </div>
                    </div>
                </div>

                <div className="mt-4 flex-1 overflow-y-auto px-1 pb-4">
                    <div className="mx-auto w-fit rounded-full border border-[#E3EBF7] bg-white px-3 py-1 text-[11px] font-medium text-[#7B8EA9] shadow-[0_10px_24px_rgba(70,96,140,0.08)]">
                        {sessionTimeLabel}
                    </div>

                    <div className="mt-4 space-y-4">
                        {documentContext ? (
                            <div className="rounded-[24px] border border-[#DDE8F5] bg-white p-4 shadow-[0_18px_40px_rgba(70,96,140,0.10)]">
                                <div className="flex items-start justify-between gap-3">
                                    <div className="flex items-start gap-3">
                                        <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-[#DCE7F4] bg-[#F4F9FF] text-[#1B95E0]">
                                            <HiDocumentText className="h-5 w-5" />
                                        </div>
                                        <div className="space-y-1">
                                            <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[#6F88B0]">
                                                Record context attached
                                            </p>
                                            <p className="text-sm font-medium text-[#16263F]">
                                                {documentContext.documentName}
                                            </p>
                                            <p className="text-sm text-[#6E829F]">
                                                Asking in {getLanguageLabel(documentContext.preferredLanguage)}
                                                {documentContext.provider
                                                    ? ` about ${documentContext.provider}`
                                                    : ""}
                                                .
                                            </p>
                                        </div>
                                    </div>
                                    <button
                                        className="rounded-full border border-[#D9E4F2] bg-[#F8FBFF] px-3 py-1 text-xs text-[#4C6286] transition hover:bg-white"
                                        onClick={dismissDocumentContext}
                                        type="button"
                                    >
                                        Dismiss
                                    </button>
                                </div>
                            </div>
                        ) : null}

                        {error ? (
                            <div className="rounded-[20px] border border-[#F1D4DA] bg-[#FFECEF] px-4 py-3 text-sm text-[#8D4155]">
                                {error}
                            </div>
                        ) : null}

                        {voiceError ? (
                            <div className="rounded-[20px] border border-[#F1D4DA] bg-[#FFF0F3] px-4 py-3 text-sm text-[#8D4155]">
                                {voiceError}
                            </div>
                        ) : null}

                        {showQuickPrompts ? (
                            <div className="space-y-3">
                                <div className="rounded-[22px] border border-[#E3EBF7] bg-white px-4 py-3 text-sm text-[#41536F] shadow-[0_16px_32px_rgba(70,96,140,0.08)]">
                                    {isSpanishLocale(selectedLanguage)
                                        ? "Puedo ayudarte con síntomas, resultados y próximos pasos. Prueba una de estas preguntas:"
                                        : "I can help with symptoms, results, and next steps. Try one of these prompts:"}
                                </div>
                                <div className="flex flex-col gap-2">
                                    {quickPrompts.map((prompt) => (
                                        <button
                                            className="rounded-[18px] border border-[#DDE8F5] bg-white px-4 py-2.5 text-left text-sm text-[#385678] shadow-[0_10px_24px_rgba(70,96,140,0.06)] transition hover:bg-[#F8FBFF]"
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
                                <div className="rounded-[20px] border border-[#E3EBF7] bg-white px-4 py-3 text-sm text-[#6E829F] shadow-[0_14px_30px_rgba(70,96,140,0.08)]">
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
                                <div className="w-fit rounded-full border border-[#E3EBF7] bg-white px-3 py-2 text-xs text-[#6E829F] shadow-[0_10px_24px_rgba(70,96,140,0.08)]">
                                    Care Companion is typing...
                                </div>
                            ) : null}
                            <div ref={bottomRef} />
                        </div>
                    </div>
                </div>

                <form
                    className="sticky bottom-24 mt-2 rounded-[28px] border border-[#E3EBF7] bg-white px-4 py-4 shadow-[0_20px_40px_rgba(70,96,140,0.12)] sm:px-5"
                    onSubmit={handleSend}
                >
                    <div className="rounded-[24px] bg-[#FAFCFF] p-2.5">
                        <Button
                            className="mx-auto mb-3 block rounded-full border-0 bg-[#304463] px-4 py-2 text-sm font-semibold text-white shadow-[0_12px_22px_rgba(48,68,99,0.22)] hover:bg-[#243551]"
                            onClick={handleVoiceModeToggle}
                            type="button"
                            variant="ghost"
                        >
                            {voiceModeEnabled
                                ? "Stop Voice-to-Voice Mode"
                                : "Start Voice-to-Voice Mode"}
                        </Button>

                        {voiceModeEnabled ? (
                            <div className="mb-3 rounded-[18px] border border-[#E3EBF7] bg-white px-4 py-3 text-sm text-[#5E6F8D]">
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
                                        ? "border-[#F4C7D1] bg-[#FFECEF] text-[#E15371]"
                                        : "border-[#E3EBF7] bg-white text-[#48607E]"
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
                            <div className="flex-1 rounded-[24px] border border-[#E3EBF7] bg-white px-1 py-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.8)]">
                                <Input
                                    className="border-0 bg-transparent px-3 py-3 text-[#23324A] shadow-none placeholder:text-[#8DA0BA] focus:border-0 focus:ring-0"
                                    onChange={(event) => setInput(event.target.value)}
                                    placeholder={
                                        isSpanishLocale(selectedLanguage)
                                            ? "Escribe o habla un mensaje..."
                                            : "Type or speak a message..."
                                    }
                                    value={input}
                                />
                            </div>
                            <button
                                aria-label="Send message"
                                className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-[#1B95E0] text-white shadow-[0_14px_28px_rgba(27,149,224,0.22)] transition hover:bg-[#1187D0] disabled:cursor-not-allowed disabled:bg-[#C8D9EC] disabled:text-[#7E96B6] disabled:shadow-none"
                                disabled={!input.trim() || connectionStatus !== "connected"}
                                type="submit"
                            >
                                <HiArrowUp className="h-5 w-5" />
                            </button>
                        </div>

                        {voiceInterimTranscript ? (
                            <p className="mt-3 text-sm text-[#7B8EA9]">
                                Listening:{" "}
                                <span className="text-[#23324A]">{voiceInterimTranscript}</span>
                            </p>
                        ) : null}
                    </div>
                </form>
            </div>
        </div>
    );
}
