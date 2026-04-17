"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
    HiArrowUp,
    HiChevronDown,
    HiDocumentText,
    HiMicrophone,
    HiSparkles,
    HiStop,
} from "react-icons/hi2";
import { useDispatch, useSelector } from "react-redux";
import { ChatBubble } from "@/components/features";
import { Button, Input } from "@/components/ui";
import {
    createSpeechRecognitionController,
    getVoiceCapabilities,
    playAssistantVoiceResponse,
    stopAssistantVoicePlayback,
    type SpeechRecognitionController,
    type VoiceStatus,
} from "@/services/browser-voice";
import {
    consumePendingChatDocumentContext,
    type PendingChatDocumentContext,
} from "@/services/chat-bridge";
import {
    buildChatWebSocketUrl,
    fetchChatHistory,
    isChatSocketEvent,
    mapChatMessageFromApi,
} from "@/services/chat-api";
import {
    addMessage,
    clearChatState,
    setChatError,
    setConnectionStatus,
    setLoading,
    setMessages,
    setTyping,
} from "@/store/slices/chat-slice";
import type { AppDispatch, RootState } from "@/store/store";
import { ChatRole, Language, type ChatMessage, type Language as ChatLanguage } from "@/types";

const CHAT_LANGUAGE_STORAGE_KEY = "patient-portal.chat.language";

function getLanguageLabel(language: ChatLanguage): string {
    return language === Language.ES ? "Español" : "English";
}

function getConnectionLabel(status: RootState["chat"]["connectionStatus"]): string {
    if (status === "connected") {
        return "Online";
    }
    if (status === "connecting") {
        return "Connecting";
    }
    if (status === "error") {
        return "Connection issue";
    }
    return "Offline";
}

function resolveInitialLanguage(): ChatLanguage {
    if (typeof window === "undefined") {
        return Language.EN;
    }

    const stored = window.localStorage.getItem(CHAT_LANGUAGE_STORAGE_KEY);
    if (stored === Language.ES || stored === Language.EN) {
        return stored;
    }

    return window.navigator.language.toLowerCase().startsWith("es")
        ? Language.ES
        : Language.EN;
}

function buildWelcomeMessage(patientId: string, language: ChatLanguage): ChatMessage {
    return {
        content:
            language === Language.ES
                ? "Hola. Puedo ayudarte a entender resultados, seguir síntomas y preparar preguntas para tu médico."
                : "Hi. I can help explain results, track symptoms, and prepare questions for your doctor.",
        createdAt: new Date().toISOString(),
        id: "welcome-message",
        language,
        patientId,
        role: ChatRole.ASSISTANT,
    };
}

function formatSessionTimeLabel(): string {
    return `Today, ${new Date().toLocaleTimeString("en-US", {
        hour: "numeric",
        minute: "2-digit",
    })}`;
}

function buildQuickPrompts(language: ChatLanguage): string[] {
    if (language === Language.ES) {
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

export default function ChatPage() {
    const dispatch = useDispatch<AppDispatch>();
    const router = useRouter();
    const searchParams = useSearchParams();
    const { accessToken, user } = useSelector((state: RootState) => state.auth);
    const { connectionStatus, error, isTyping, loading, messages } = useSelector(
        (state: RootState) => state.chat,
    );

    const [initialDocumentContext] = useState<PendingChatDocumentContext | null>(() => {
        if (typeof window === "undefined") {
            return null;
        }

        const documentId = new URLSearchParams(window.location.search).get("document");
        return consumePendingChatDocumentContext(documentId);
    });
    const [initialLanguage] = useState<ChatLanguage>(
        () => initialDocumentContext?.preferredLanguage ?? resolveInitialLanguage(),
    );
    const voiceCapabilities = getVoiceCapabilities();
    const selectedLanguageRef = useRef<ChatLanguage>(initialLanguage);
    const voiceModeRef = useRef(false);
    const recognitionRef = useRef<SpeechRecognitionController | null>(null);
    const playbackStopRef = useRef<(() => void) | null>(null);
    const socketRef = useRef<WebSocket | null>(null);
    const bottomRef = useRef<HTMLDivElement | null>(null);

    const [input, setInput] = useState(
        () => initialDocumentContext?.suggestedQuestion ?? "",
    );
    const [sessionTimeLabel] = useState(() => formatSessionTimeLabel());
    const [selectedLanguage, setSelectedLanguage] =
        useState<ChatLanguage>(initialLanguage);
    const [assistantDraft, setAssistantDraft] = useState("");
    const [assistantDraftStartedAt, setAssistantDraftStartedAt] = useState<string | null>(null);
    const [voiceModeEnabled, setVoiceModeEnabled] = useState(false);
    const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>(
        voiceCapabilities.recognition || voiceCapabilities.synthesis
            ? "idle"
            : "unsupported",
    );
    const [voiceError, setVoiceError] = useState<string | null>(null);
    const [voiceInterimTranscript, setVoiceInterimTranscript] = useState("");
    const [documentContext, setDocumentContext] =
        useState<PendingChatDocumentContext | null>(initialDocumentContext);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [assistantDraft, isTyping, messages]);

    useEffect(() => {
        selectedLanguageRef.current = selectedLanguage;
        if (typeof window !== "undefined") {
            window.localStorage.setItem(CHAT_LANGUAGE_STORAGE_KEY, selectedLanguage);
        }
    }, [selectedLanguage]);

    useEffect(() => {
        voiceModeRef.current = voiceModeEnabled;
    }, [voiceModeEnabled]);

    useEffect(() => {
        const documentId = searchParams.get("document");
        if (!documentId) {
            return;
        }

        router.replace("/chat");
    }, [router, searchParams]);

    useEffect(() => {
        if (!accessToken || !user) {
            return;
        }

        let isMounted = true;
        dispatch(clearChatState());
        dispatch(setLoading(true));

        fetchChatHistory(user.id, accessToken)
            .then((history) => {
                if (!isMounted) {
                    return;
                }

                dispatch(
                    setMessages(
                        history.length > 0
                            ? history
                            : [buildWelcomeMessage(user.id, initialLanguage)],
                    ),
                );
            })
            .catch(() => {
                if (!isMounted) {
                    return;
                }

                dispatch(
                    setMessages([
                        buildWelcomeMessage(user.id, initialLanguage),
                    ]),
                );
                dispatch(setChatError("Unable to load chat history. Live chat is still available."));
            })
            .finally(() => {
                if (isMounted) {
                    dispatch(setLoading(false));
                }
            });

        dispatch(setConnectionStatus("connecting"));
        dispatch(setChatError(null));

        const socket = new WebSocket(buildChatWebSocketUrl(user.id, accessToken));
        socketRef.current = socket;

        socket.onopen = () => {
            if (!isMounted) {
                return;
            }
            dispatch(setConnectionStatus("connected"));
            dispatch(setChatError(null));
        };

        socket.onmessage = (event) => {
            let payload: unknown;

            try {
                payload = JSON.parse(event.data as string);
            } catch {
                return;
            }

            if (!isChatSocketEvent(payload)) {
                return;
            }

            switch (payload.type) {
                case "chat_history": {
                    const incomingHistory = payload.messages.map(mapChatMessageFromApi);
                    dispatch(
                        setMessages(
                            incomingHistory.length > 0
                                ? incomingHistory
                                : [buildWelcomeMessage(user.id, selectedLanguageRef.current)],
                        ),
                    );
                    return;
                }
                case "user_message_saved":
                    dispatch(addMessage(mapChatMessageFromApi(payload.message)));
                    return;
                case "assistant_start":
                    setAssistantDraft("");
                    setAssistantDraftStartedAt(new Date().toISOString());
                    dispatch(setTyping(true));
                    return;
                case "assistant_chunk":
                    setAssistantDraft((current) => `${current}${payload.content}`);
                    dispatch(setTyping(true));
                    return;
                case "assistant_complete": {
                    const assistantMessage = mapChatMessageFromApi(payload.message);
                    setAssistantDraft("");
                    setAssistantDraftStartedAt(null);
                    dispatch(setTyping(false));
                    dispatch(addMessage(assistantMessage));

                    if (voiceModeRef.current) {
                        playbackStopRef.current?.();
                        playbackStopRef.current = playAssistantVoiceResponse({
                            audioUrl: assistantMessage.audioUrl,
                            language: assistantMessage.language,
                            onEnd: () => {
                                setVoiceStatus(
                                    voiceModeRef.current ? "idle" : "unsupported",
                                );
                            },
                            onStart: () => {
                                setVoiceStatus("playing");
                            },
                            text: assistantMessage.content,
                        });
                    }

                    if (payload.escalation_required) {
                        dispatch(
                            setChatError(
                                "Urgent symptoms detected. Contact your care team today.",
                            ),
                        );
                    }
                    return;
                }
                case "escalation_recommended":
                    dispatch(setChatError(payload.message));
                    return;
                case "error":
                    setAssistantDraft("");
                    setAssistantDraftStartedAt(null);
                    dispatch(setTyping(false));
                    dispatch(setChatError(payload.message || "Chat request failed."));
                    return;
                default:
                    return;
            }
        };

        socket.onerror = () => {
            if (!isMounted) {
                return;
            }
            setAssistantDraft("");
            setAssistantDraftStartedAt(null);
            dispatch(setConnectionStatus("error"));
            dispatch(setTyping(false));
            dispatch(setChatError("Live chat connection encountered an issue."));
        };

        socket.onclose = () => {
            if (!isMounted) {
                return;
            }
            dispatch(setConnectionStatus("disconnected"));
            dispatch(setTyping(false));
        };

        return () => {
            isMounted = false;
            recognitionRef.current?.stop();
            playbackStopRef.current?.();
            playbackStopRef.current = null;
            socketRef.current = null;
            socket.close();
        };
    }, [accessToken, dispatch, initialLanguage, user]);

    useEffect(() => {
        return () => {
            recognitionRef.current?.stop();
            stopAssistantVoicePlayback();
        };
    }, []);

    function dismissDocumentContext() {
        setDocumentContext(null);
    }

    function sendChatMessage(content: string, audioUrl?: string): void {
        const trimmedContent = content.trim();
        if (!trimmedContent) {
            return;
        }

        if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
            dispatch(setChatError("Chat is reconnecting. Try sending in a moment."));
            return;
        }

        socketRef.current.send(
            JSON.stringify({
                type: "user_message",
                content: trimmedContent,
                language: selectedLanguageRef.current,
                audio_url: audioUrl ?? null,
            }),
        );

        dispatch(setChatError(null));
        setVoiceError(null);
        setVoiceInterimTranscript("");
        setInput("");
    }

    function handleSend(event: React.FormEvent<HTMLFormElement>) {
        event.preventDefault();
        sendChatMessage(input);
    }

    function handleLanguageSelection(language: ChatLanguage) {
        setSelectedLanguage(language);
        setVoiceError(null);
    }

    function handleVoiceModeToggle() {
        if (voiceStatus === "unsupported") {
            setVoiceError("Voice mode is not available on this device.");
            return;
        }

        const nextValue = !voiceModeEnabled;
        setVoiceModeEnabled(nextValue);

        if (!nextValue) {
            recognitionRef.current?.stop();
            playbackStopRef.current?.();
            playbackStopRef.current = null;
            setVoiceInterimTranscript("");
            setVoiceStatus("idle");
        } else {
            setVoiceError(null);
        }
    }

    function handleMicClick() {
        if (!voiceCapabilities.recognition) {
            setVoiceStatus("unsupported");
            setVoiceError("Speech recognition is not supported in this browser.");
            return;
        }

        if (voiceStatus === "listening") {
            recognitionRef.current?.stop();
            return;
        }

        setVoiceError(null);
        setVoiceInterimTranscript("");

        const controller = createSpeechRecognitionController(selectedLanguageRef.current, {
            onEnd: (finalTranscript) => {
                recognitionRef.current = null;
                setVoiceStatus(voiceModeRef.current ? "processing" : "idle");
                setVoiceInterimTranscript("");

                if (!finalTranscript) {
                    setVoiceStatus("idle");
                    return;
                }

                if (voiceModeRef.current) {
                    sendChatMessage(finalTranscript);
                } else {
                    setInput(finalTranscript);
                    setVoiceStatus("idle");
                }
            },
            onError: (message) => {
                recognitionRef.current = null;
                setVoiceStatus("idle");
                setVoiceInterimTranscript("");
                setVoiceError(message);
            },
            onStart: () => {
                setVoiceStatus("listening");
            },
            onTranscript: ({ finalTranscript, interimTranscript }) => {
                if (!voiceModeRef.current && finalTranscript) {
                    setInput(finalTranscript);
                }
                setVoiceInterimTranscript(interimTranscript);
            },
        });

        if (!controller) {
            setVoiceStatus("unsupported");
            setVoiceError("Speech recognition is not supported in this browser.");
            return;
        }

        recognitionRef.current = controller;
        controller.start();
    }

    function handlePlayAssistantMessage(message: ChatMessage) {
        const canPlay =
            Boolean(message.audioUrl) || voiceCapabilities.synthesis;

        if (!canPlay) {
            setVoiceError("Audio playback is not available on this device.");
            return;
        }

        playbackStopRef.current?.();
        playbackStopRef.current = playAssistantVoiceResponse({
            audioUrl: message.audioUrl,
            language: message.language,
            onEnd: () => {
                setVoiceStatus("idle");
            },
            onStart: () => {
                setVoiceStatus("playing");
            },
            text: message.content,
        });
    }

    const canPlayAssistantAudio = voiceCapabilities.synthesis;
    const quickPrompts = buildQuickPrompts(selectedLanguage);
    const showQuickPrompts =
        !loading
        && !documentContext
        && messages.filter((message) => message.role === ChatRole.USER).length === 0;

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
                            {[Language.EN, Language.ES].map((language) => {
                                const isActive = selectedLanguage === language;
                                return (
                                    <button
                                        aria-pressed={isActive}
                                        className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                                            isActive
                                                ? "bg-[#EADFFF] text-[#5F4A90]"
                                                : "text-[#5E6F8D] hover:bg-[#F4F8FD]"
                                        }`}
                                        key={language}
                                        onClick={() => handleLanguageSelection(language)}
                                        type="button"
                                    >
                                        {language === Language.EN ? "EN" : "ES"}
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
                                    {selectedLanguage === Language.ES
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
                                        selectedLanguage === Language.ES
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
