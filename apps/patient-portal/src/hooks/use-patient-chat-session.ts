"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useDispatch, useSelector } from "react-redux";
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
import {
    ChatRole,
    Language,
    type ChatMessage,
    type Language as ChatLanguage,
} from "@/types";

const CHAT_LANGUAGE_STORAGE_KEY = "patient-portal.chat.language";

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
                ? "Hola. Puedo ayudarte a entender resultados, seguir sintomas y preparar preguntas para tu medico."
                : "Hi. I can help explain results, track symptoms, and prepare questions for your doctor.",
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
    selectedLanguage: ChatLanguage;
    voiceError: string | null;
    voiceInterimTranscript: string;
    voiceModeEnabled: boolean;
    voiceStatus: VoiceStatus;
}

interface PatientChatSessionActions {
    dismissDocumentContext: () => void;
    handleLanguageSelection: (language: ChatLanguage) => void;
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
    const [initialLanguage] = useState<ChatLanguage>(
        () => initialDocumentContext?.preferredLanguage ?? resolveInitialLanguage(),
    );
    const [voiceCapabilities] = useState(getVoiceCapabilities);
    const [input, setInput] = useState(
        () => initialDocumentContext?.suggestedQuestion ?? "",
    );
    const [selectedLanguage, setSelectedLanguage] = useState<ChatLanguage>(initialLanguage);
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

    const recognitionRef = useRef<SpeechRecognitionController | null>(null);
    const playbackStopRef = useRef<(() => void) | null>(null);
    const selectedLanguageRef = useRef<ChatLanguage>(initialLanguage);
    const socketRef = useRef<WebSocket | null>(null);
    const voiceModeRef = useRef(false);

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
        playbackStopRef.current?.();
        playbackStopRef.current = null;
    }

    function stopSpeechRecognition(): void {
        recognitionRef.current?.stop();
        recognitionRef.current = null;
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
        resetVoiceFeedback();
        setInput("");
    }

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

                    if (voiceModeRef.current) {
                        stopAssistantPlayback();
                        playbackStopRef.current = playAssistantVoiceResponse({
                            audioUrl: assistantMessage.audioUrl,
                            language: assistantMessage.language,
                            onEnd: () => {
                                setVoiceStatus(voiceModeRef.current ? "idle" : "unsupported");
                            },
                            onStart: () => {
                                setVoiceStatus("playing");
                            },
                            text: assistantMessage.content,
                        });
                    }

                    if (payload.escalation_required) {
                        dispatch(
                            setChatError("Urgent symptoms detected. Contact your care team today."),
                        );
                    }
                    return;
                }
                case "escalation_recommended":
                    dispatch(setChatError(payload.message));
                    return;
                case "error":
                    resetAssistantDraft();
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

            resetAssistantDraft();
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
            stopSpeechRecognition();
            stopAssistantPlayback();
            socketRef.current = null;
            socket.close();
        };
    }, [accessToken, dispatch, initialLanguage, user]);

    useEffect(() => {
        return () => {
            stopSpeechRecognition();
            stopAssistantVoicePlayback();
        };
    }, []);

    function dismissDocumentContext(): void {
        setDocumentContext(null);
    }

    function handleLanguageSelection(language: ChatLanguage): void {
        selectedLanguageRef.current = language;
        setSelectedLanguage(language);
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
        voiceModeRef.current = nextValue;
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
                    return;
                }

                setInput(finalTranscript);
                setVoiceStatus("idle");
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

    function handlePlayAssistantMessage(message: ChatMessage): void {
        const canPlay = Boolean(message.audioUrl) || voiceCapabilities.synthesis;
        if (!canPlay) {
            setVoiceError("Audio playback is not available on this device.");
            return;
        }

        stopAssistantPlayback();
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

    return {
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
    };
}
