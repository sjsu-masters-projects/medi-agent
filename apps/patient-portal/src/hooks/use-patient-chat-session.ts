"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useDispatch, useSelector } from "react-redux";
import { getPatientChatCopy } from "@/content/chat-copy";
import {
    createSpeechRecognitionController,
    getVoiceCapabilities,
    playAssistantVoiceResponse,
    stopAssistantVoicePlayback,
    type SpeechRecognitionController,
    type VoiceStatus,
} from "@/services/browser-voice";
import {
    buildSuggestedDocumentQuestion,
    consumePendingChatDocumentContext,
    normalizeChatDocumentType,
    type PendingChatDocumentContext,
} from "@/services/chat-bridge";
import {
    buildChatWebSocketUrl,
    fetchChatHistory,
    isChatSocketEvent,
    mapChatMessageFromApi,
    type ChatDocumentContextApi,
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
import {
    ChatRole,
    DEFAULT_LOCALE,
    normalizeLocale,
    type ChatMessage,
    type Locale as ChatLocale,
} from "@/types";

const CHAT_LANGUAGE_STORAGE_KEY = "patient-portal.chat.language";
const FALLBACK_DOCUMENT_NAME = "medical record";

function resolveInitialLanguage(): ChatLocale {
    if (typeof window === "undefined") {
        return DEFAULT_LOCALE;
    }

    const stored = window.localStorage.getItem(CHAT_LANGUAGE_STORAGE_KEY);
    if (stored) {
        return normalizeLocale(stored);
    }

    return normalizeLocale(window.navigator.language);
}

function buildWelcomeMessage(patientId: string, language: ChatLocale): ChatMessage {
    return {
        content: getPatientChatCopy(language).welcomeMessage,
        createdAt: new Date().toISOString(),
        id: "welcome-message",
        language,
        patientId,
        role: ChatRole.ASSISTANT,
    };
}

function resolveInitialDocumentContext(): PendingChatDocumentContext | null {
    if (typeof window === "undefined") {
        return null;
    }

    const documentId = new URLSearchParams(window.location.search).get("document");
    return consumePendingChatDocumentContext(documentId);
}

function resolveInitialDocumentId(): string | null {
    if (typeof window === "undefined") {
        return null;
    }

    return new URLSearchParams(window.location.search).get("document");
}

function mapLoadedDocumentContext(
    document: ChatDocumentContextApi,
    preferredLanguage: ChatLocale,
): PendingChatDocumentContext | null {
    const documentId = typeof document.id === "string" ? document.id.trim() : "";
    if (!documentId) {
        return null;
    }

    const documentType = normalizeChatDocumentType(document.document_type);
    const documentName =
        typeof document.file_name === "string" && document.file_name.trim()
            ? document.file_name.trim()
            : FALLBACK_DOCUMENT_NAME;

    return {
        documentId,
        documentName,
        documentType,
        preferredLanguage,
        suggestedQuestion: buildSuggestedDocumentQuestion({
            documentName,
            documentType,
            preferredLanguage,
        }),
        summary: typeof document.summary === "string" ? document.summary : undefined,
    };
}

interface PatientChatSessionState {
    assistantDraft: string;
    assistantDraftStartedAt: string | null;
    canPlayAssistantAudio: boolean;
    connectionStatus: RootState["chat"]["connectionStatus"];
    documentContext: PendingChatDocumentContext | null;
    error: string | null;
    input: string;
    isTyping: boolean;
    loading: boolean;
    messages: ChatMessage[];
    selectedLanguage: ChatLocale;
    safetyNotice: string | null;
    voiceError: string | null;
    voiceInterimTranscript: string;
    voiceModeEnabled: boolean;
    voiceStatus: VoiceStatus;
}

interface PatientChatSessionActions {
    dismissDocumentContext: () => void;
    dismissSafetyNotice: () => void;
    handleLanguageSelection: (language: ChatLocale) => void;
    handleMicClick: () => void;
    handlePlayAssistantMessage: (message: ChatMessage) => void;
    handleSend: (event: FormEvent<HTMLFormElement>) => void;
    handleVoiceModeToggle: () => void;
    setInput: (value: string) => void;
}

export function usePatientChatSession(): PatientChatSessionState & PatientChatSessionActions {
    const dispatch = useDispatch<AppDispatch>();
    const router = useRouter();
    const searchParams = useSearchParams();
    const { accessToken, user } = useSelector((state: RootState) => state.auth);
    const { connectionStatus, error, isTyping, loading, messages } = useSelector(
        (state: RootState) => state.chat,
    );

    const [initialDocumentContext] = useState<PendingChatDocumentContext | null>(
        resolveInitialDocumentContext,
    );
    const [initialDocumentId] = useState<string | null>(
        () => initialDocumentContext?.documentId ?? resolveInitialDocumentId(),
    );
    const [initialLanguage] = useState<ChatLocale>(
        () => initialDocumentContext?.preferredLanguage ?? resolveInitialLanguage(),
    );
    const [voiceCapabilities] = useState(getVoiceCapabilities);
    const [input, setInput] = useState(
        () => initialDocumentContext?.suggestedQuestion ?? "",
    );
    const [selectedLanguage, setSelectedLanguage] = useState<ChatLocale>(initialLanguage);
    const [assistantDraft, setAssistantDraft] = useState("");
    const [assistantDraftStartedAt, setAssistantDraftStartedAt] = useState<string | null>(null);
    const [voiceModeEnabled, setVoiceModeEnabled] = useState(false);
    const [voiceError, setVoiceError] = useState<string | null>(null);
    const [voiceInterimTranscript, setVoiceInterimTranscript] = useState("");
    const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>(() => {
        const capabilities = getVoiceCapabilities();
        return capabilities.recognition || capabilities.synthesis ? "idle" : "unsupported";
    });
    const [documentContext, setDocumentContext] =
        useState<PendingChatDocumentContext | null>(initialDocumentContext);
    const [activeDocumentId, setActiveDocumentId] = useState<string | null>(initialDocumentId);
    const [safetyNotice, setSafetyNotice] = useState<string | null>(null);

    const voiceRefs = useRef<{
        recognition: SpeechRecognitionController | null;
        playbackStop: (() => void) | null;
        selectedLanguage: ChatLocale;
        voiceModeEnabled: boolean;
    }>({
        playbackStop: null,
        recognition: null,
        selectedLanguage: initialLanguage,
        voiceModeEnabled: false,
    });
    const socketRef = useRef<WebSocket | null>(null);

    const canPlayAssistantAudio = voiceCapabilities.synthesis;

    function resetAssistantDraft(): void {
        setAssistantDraft("");
        setAssistantDraftStartedAt(null);
    }

    function resetVoiceFeedback(): void {
        setVoiceError(null);
        setVoiceInterimTranscript("");
    }

    function stopAssistantPlayback(): void {
        voiceRefs.current.playbackStop?.();
        voiceRefs.current.playbackStop = null;
    }

    function stopSpeechRecognition(): void {
        voiceRefs.current.recognition?.stop();
        voiceRefs.current.recognition = null;
    }

    function sendChatMessage(content: string, audioUrl?: string): void {
        const trimmedContent = content.trim();
        if (!trimmedContent) {
            return;
        }

        if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
            dispatch(setChatError("Chat is reconnecting. Try sending in a moment."));
            setVoiceStatus("idle");
            return;
        }

        socketRef.current.send(
            JSON.stringify({
                type: "user_message",
                content: trimmedContent,
                language: voiceRefs.current.selectedLanguage,
                audio_url: audioUrl ?? null,
            }),
        );

        dispatch(setChatError(null));
        setSafetyNotice(null);
        resetVoiceFeedback();
        setInput("");
    }

    useEffect(() => {
        voiceRefs.current.selectedLanguage = selectedLanguage;
        if (typeof window !== "undefined") {
            window.localStorage.setItem(CHAT_LANGUAGE_STORAGE_KEY, selectedLanguage);
        }
    }, [selectedLanguage]);

    useEffect(() => {
        voiceRefs.current.voiceModeEnabled = voiceModeEnabled;
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

                dispatch(setMessages([buildWelcomeMessage(user.id, initialLanguage)]));
                dispatch(setChatError("Unable to load chat history. Live chat is still available."));
            })
            .finally(() => {
                if (isMounted) {
                    dispatch(setLoading(false));
                }
            });

        dispatch(setConnectionStatus("connecting"));
        dispatch(setChatError(null));

        const socket = new WebSocket(
            buildChatWebSocketUrl(user.id, accessToken, {
                documentId: activeDocumentId,
            }),
        );
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
                                : [buildWelcomeMessage(user.id, voiceRefs.current.selectedLanguage)],
                        ),
                    );
                    return;
                }
                case "chat_context_loaded": {
                    const loadedDocumentContext = mapLoadedDocumentContext(
                        payload.document,
                        voiceRefs.current.selectedLanguage,
                    );
                    if (loadedDocumentContext) {
                        setActiveDocumentId(loadedDocumentContext.documentId);
                        setDocumentContext(loadedDocumentContext);
                    }
                    return;
                }
                case "user_message_saved":
                    dispatch(addMessage(mapChatMessageFromApi(payload.message)));
                    return;
                case "assistant_start":
                    resetAssistantDraft();
                    setAssistantDraftStartedAt(new Date().toISOString());
                    dispatch(setTyping(true));
                    return;
                case "assistant_chunk":
                    setAssistantDraft((current) => `${current}${payload.content}`);
                    dispatch(setTyping(true));
                    return;
                case "assistant_complete": {
                    const assistantMessage = mapChatMessageFromApi(payload.message);
                    resetAssistantDraft();
                    dispatch(setTyping(false));
                    dispatch(addMessage(assistantMessage));

                    if (voiceRefs.current.voiceModeEnabled) {
                        stopAssistantPlayback();
                        voiceRefs.current.playbackStop = playAssistantVoiceResponse({
                            audioUrl: assistantMessage.audioUrl,
                            language: assistantMessage.language,
                            onEnd: () => {
                                setVoiceStatus("idle");
                            },
                            onStart: () => {
                                setVoiceStatus("playing");
                            },
                            text: assistantMessage.content,
                        });
                    }

                    if (payload.escalation_required) {
                        setSafetyNotice(
                            getPatientChatCopy(voiceRefs.current.selectedLanguage).escalationNotice,
                        );
                    }
                    return;
                }
                case "escalation_recommended":
                    setSafetyNotice(getPatientChatCopy(voiceRefs.current.selectedLanguage).escalationNotice);
                    return;
                case "error":
                    resetAssistantDraft();
                    dispatch(setTyping(false));
                    dispatch(setChatError(payload.message || "Chat request failed."));
                    setVoiceStatus("idle");
                    setVoiceModeEnabled(false);
                    voiceRefs.current.voiceModeEnabled = false;
                    return;
                default:
                    return;
            }
        };

        socket.onerror = () => {
            if (!isMounted) {
                return;
            }

            resetAssistantDraft();
            dispatch(setConnectionStatus("error"));
            dispatch(setTyping(false));
            dispatch(setChatError("Live chat connection encountered an issue."));
            setVoiceStatus("idle");
            setVoiceModeEnabled(false);
            voiceRefs.current.voiceModeEnabled = false;
        };

        socket.onclose = () => {
            if (!isMounted) {
                return;
            }

            dispatch(setConnectionStatus("disconnected"));
            dispatch(setTyping(false));
            setVoiceStatus("idle");
            setVoiceModeEnabled(false);
            voiceRefs.current.voiceModeEnabled = false;
        };

        return () => {
            isMounted = false;
            stopSpeechRecognition();
            stopAssistantPlayback();
            socketRef.current = null;
            socket.close();
        };
    }, [accessToken, activeDocumentId, dispatch, initialLanguage, user]);

    useEffect(() => {
        return () => {
            stopSpeechRecognition();
            stopAssistantVoicePlayback();
        };
    }, []);

    function dismissDocumentContext(): void {
        setActiveDocumentId(null);
        setDocumentContext(null);
    }

    function dismissSafetyNotice(): void {
        setSafetyNotice(null);
    }

    function handleLanguageSelection(language: ChatLocale): void {
        const nextLocale = normalizeLocale(language);
        voiceRefs.current.selectedLanguage = nextLocale;
        setSelectedLanguage(nextLocale);
        setVoiceError(null);
    }

    function handleSend(event: FormEvent<HTMLFormElement>): void {
        event.preventDefault();
        sendChatMessage(input);
    }

    function handleVoiceModeToggle(): void {
        if (voiceStatus === "unsupported") {
            setVoiceError("Voice mode is not available on this device.");
            return;
        }

        const nextValue = !voiceModeEnabled;
        voiceRefs.current.voiceModeEnabled = nextValue;
        setVoiceModeEnabled(nextValue);

        if (!nextValue) {
            stopSpeechRecognition();
            stopAssistantPlayback();
            setVoiceInterimTranscript("");
            setVoiceStatus("idle");
            return;
        }

        setVoiceError(null);
    }

    function handleMicClick(): void {
        if (!voiceCapabilities.recognition) {
            setVoiceStatus("unsupported");
            setVoiceError("Speech recognition is not supported in this browser.");
            return;
        }

        if (voiceStatus === "listening") {
            stopSpeechRecognition();
            return;
        }

        resetVoiceFeedback();

        const controller = createSpeechRecognitionController(voiceRefs.current.selectedLanguage, {
            onEnd: (finalTranscript) => {
                voiceRefs.current.recognition = null;
                setVoiceStatus(voiceRefs.current.voiceModeEnabled ? "processing" : "idle");
                setVoiceInterimTranscript("");

                if (!finalTranscript) {
                    setVoiceStatus("idle");
                    return;
                }

                if (voiceRefs.current.voiceModeEnabled) {
                    sendChatMessage(finalTranscript);
                    return;
                }

                setInput(finalTranscript);
                setVoiceStatus("idle");
            },
            onError: (message) => {
                voiceRefs.current.recognition = null;
                setVoiceStatus("idle");
                setVoiceInterimTranscript("");
                setVoiceError(message);
            },
            onStart: () => {
                setVoiceStatus("listening");
            },
            onTranscript: ({ finalTranscript, interimTranscript }) => {
                if (!voiceRefs.current.voiceModeEnabled && finalTranscript) {
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

        voiceRefs.current.recognition = controller;
        controller.start();
    }

    function handlePlayAssistantMessage(message: ChatMessage): void {
        const canPlay = Boolean(message.audioUrl) || voiceCapabilities.synthesis;
        if (!canPlay) {
            setVoiceError("Audio playback is not available on this device.");
            return;
        }

        stopAssistantPlayback();
        voiceRefs.current.playbackStop = playAssistantVoiceResponse({
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

    return {
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
    };
}
