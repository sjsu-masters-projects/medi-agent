"use client";

import { useEffect, useEffectEvent, useRef, useState, type FormEvent } from "react";
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
    buildVoiceAudioDataUrl,
    buildVoiceWebSocketUrl,
    blobToBase64,
    isVoiceSocketEvent,
    normalizeVoiceEventLanguage,
} from "@/services/voice-api";
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
        return capabilities.recording || capabilities.recognition || capabilities.synthesis
            ? "idle"
            : "unsupported";
    });
    const [documentContext, setDocumentContext] =
        useState<PendingChatDocumentContext | null>(initialDocumentContext);
    const [activeDocumentId, setActiveDocumentId] = useState<string | null>(initialDocumentId);
    const [safetyNotice, setSafetyNotice] = useState<string | null>(null);

    const voiceRefs = useRef<{
        finalTranscript: string;
        mediaRecorder: MediaRecorder | null;
        mediaStream: MediaStream | null;
        pendingPlayback: { language: ChatLocale; text: string } | null;
        queuedVoiceEvents: string[];
        recognition: SpeechRecognitionController | null;
        recordedAudioUrl: string | null;
        playbackStop: (() => void) | null;
        selectedLanguage: ChatLocale;
        voiceModeEnabled: boolean;
    }>({
        finalTranscript: "",
        mediaRecorder: null,
        mediaStream: null,
        playbackStop: null,
        pendingPlayback: null,
        queuedVoiceEvents: [],
        recognition: null,
        recordedAudioUrl: null,
        selectedLanguage: initialLanguage,
        voiceModeEnabled: false,
    });
    const socketRef = useRef<WebSocket | null>(null);
    const voiceSocketRef = useRef<WebSocket | null>(null);

    const canPlayAssistantAudio = Boolean(accessToken && user) || voiceCapabilities.synthesis;

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
        voiceRefs.current.pendingPlayback = null;
    }

    function stopSpeechRecognition(): void {
        voiceRefs.current.recognition?.stop();
        voiceRefs.current.recognition = null;
    }

    function stopMediaRecorder(): void {
        const recorder = voiceRefs.current.mediaRecorder;
        if (recorder && recorder.state !== "inactive") {
            recorder.stop();
        }
        voiceRefs.current.mediaRecorder = null;
        voiceRefs.current.mediaStream?.getTracks().forEach((track) => track.stop());
        voiceRefs.current.mediaStream = null;
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

    function playAssistantMessageWithBrowserFallback(message: ChatMessage): void {
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

    function closeVoiceSocket(): void {
        const socket = voiceSocketRef.current;
        voiceSocketRef.current = null;
        voiceRefs.current.queuedVoiceEvents = [];
        if (socket && socket.readyState !== WebSocket.CLOSED) {
            socket.close();
        }
    }

    function sendQueuedVoiceEvents(): void {
        const socket = voiceSocketRef.current;
        if (!socket || socket.readyState !== WebSocket.OPEN) {
            return;
        }

        while (voiceRefs.current.queuedVoiceEvents.length > 0) {
            const nextEvent = voiceRefs.current.queuedVoiceEvents.shift();
            if (nextEvent) {
                socket.send(nextEvent);
            }
        }
    }

    function connectVoiceSocket(): WebSocket | null {
        if (!accessToken || !user) {
            return null;
        }

        const existingSocket = voiceSocketRef.current;
        if (
            existingSocket &&
            (existingSocket.readyState === WebSocket.CONNECTING ||
                existingSocket.readyState === WebSocket.OPEN)
        ) {
            return existingSocket;
        }

        const socket = new WebSocket(buildVoiceWebSocketUrl(user.id, accessToken));
        voiceSocketRef.current = socket;

        socket.onopen = () => {
            sendQueuedVoiceEvents();
        };

        socket.onmessage = (event) => {
            let payload: unknown;
            try {
                payload = JSON.parse(event.data as string);
            } catch {
                return;
            }

            if (!isVoiceSocketEvent(payload)) {
                return;
            }

            if (payload.type === "voice_ready") {
                sendQueuedVoiceEvents();
                return;
            }

            if (payload.type === "audio_stream_started") {
                setVoiceStatus("listening");
                return;
            }

            if (payload.type === "transcript_partial") {
                setVoiceInterimTranscript(payload.transcript);
                return;
            }

            if (payload.type === "transcript_final") {
                voiceRefs.current.finalTranscript = payload.transcript;
                setVoiceInterimTranscript(payload.transcript);
                return;
            }

            if (payload.type === "audio_stream_complete") {
                const transcript = voiceRefs.current.finalTranscript.trim();
                voiceRefs.current.recordedAudioUrl = payload.audio_url ?? null;
                voiceRefs.current.finalTranscript = "";
                setVoiceInterimTranscript("");
                if (transcript) {
                    setVoiceStatus(voiceRefs.current.voiceModeEnabled ? "processing" : "idle");
                    sendChatMessage(transcript, payload.audio_url ?? undefined);
                } else {
                    setVoiceStatus("idle");
                }
                return;
            }

            if (payload.type === "assistant_audio_ready") {
                const pendingPlayback = voiceRefs.current.pendingPlayback;
                if (!pendingPlayback) {
                    return;
                }

                stopAssistantPlayback();
                voiceRefs.current.playbackStop = playAssistantVoiceResponse({
                    audioUrl: buildVoiceAudioDataUrl(payload),
                    language: normalizeVoiceEventLanguage(payload.language),
                    onEnd: () => {
                        setVoiceStatus("idle");
                    },
                    onStart: () => {
                        setVoiceStatus("playing");
                    },
                    text: pendingPlayback.text,
                });
                return;
            }

            if (payload.type === "voice_error") {
                const pendingPlayback = voiceRefs.current.pendingPlayback;
                voiceRefs.current.pendingPlayback = null;
                setVoiceError(
                    payload.message || "Voice playback is temporarily unavailable. Using device audio.",
                );

                if (pendingPlayback && voiceCapabilities.synthesis) {
                    voiceRefs.current.playbackStop = playAssistantVoiceResponse({
                        language: pendingPlayback.language,
                        onEnd: () => {
                            setVoiceStatus("idle");
                        },
                        onStart: () => {
                            setVoiceStatus("playing");
                        },
                        text: pendingPlayback.text,
                    });
                } else {
                    setVoiceStatus("idle");
                }
            }
        };

        socket.onerror = () => {
            const pendingPlayback = voiceRefs.current.pendingPlayback;
            voiceRefs.current.pendingPlayback = null;
            setVoiceError("Voice playback is reconnecting. Using device audio for now.");

            if (pendingPlayback && voiceCapabilities.synthesis) {
                voiceRefs.current.playbackStop = playAssistantVoiceResponse({
                    language: pendingPlayback.language,
                    onEnd: () => {
                        setVoiceStatus("idle");
                    },
                    onStart: () => {
                        setVoiceStatus("playing");
                    },
                    text: pendingPlayback.text,
                });
            } else {
                setVoiceStatus("idle");
            }
        };

        socket.onclose = () => {
            if (voiceSocketRef.current === socket) {
                voiceSocketRef.current = null;
            }
        };

        return socket;
    }

    function sendVoiceSocketEvent(event: Record<string, unknown>): WebSocket | null {
        const socket = connectVoiceSocket();
        if (!socket) {
            return null;
        }

        const payload = JSON.stringify(event);
        if (socket.readyState === WebSocket.OPEN) {
            socket.send(payload);
        } else {
            voiceRefs.current.queuedVoiceEvents.push(payload);
        }
        return socket;
    }

    function requestBackendAssistantAudio(message: ChatMessage): void {
        if (message.audioUrl) {
            playAssistantMessageWithBrowserFallback(message);
            return;
        }

        const socket = connectVoiceSocket();
        if (!socket) {
            playAssistantMessageWithBrowserFallback(message);
            return;
        }

        stopAssistantPlayback();
        voiceRefs.current.pendingPlayback = {
            language: message.language,
            text: message.content,
        };
        sendVoiceSocketEvent({
            type: "tts_request",
            message_id: message.id,
            text: message.content,
            language: message.language,
        });
        setVoiceStatus("processing");
    }

    const requestBackendAssistantAudioEvent = useEffectEvent((message: ChatMessage) => {
        requestBackendAssistantAudio(message);
    });

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
                        requestBackendAssistantAudioEvent(assistantMessage);
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
            closeVoiceSocket();
            socketRef.current = null;
            socket.close();
        };
    }, [accessToken, activeDocumentId, dispatch, initialLanguage, user]);

    useEffect(() => {
        return () => {
            stopSpeechRecognition();
            stopMediaRecorder();
            stopAssistantVoicePlayback();
            closeVoiceSocket();
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
            stopMediaRecorder();
            stopAssistantPlayback();
            setVoiceInterimTranscript("");
            setVoiceStatus("idle");
            return;
        }

        setVoiceError(null);
    }

    function handleMicClick(): void {
        if (voiceStatus === "listening") {
            stopMediaRecorder();
            stopSpeechRecognition();
            return;
        }

        if (voiceCapabilities.recording && accessToken && user) {
            void startBackendVoiceRecording();
            return;
        }

        if (!voiceCapabilities.recognition) {
            setVoiceStatus("unsupported");
            setVoiceError("Speech recognition is not supported in this browser.");
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

    async function startBackendVoiceRecording(): Promise<void> {
        resetVoiceFeedback();

        if (!navigator.mediaDevices?.getUserMedia || typeof window.MediaRecorder === "undefined") {
            setVoiceStatus("unsupported");
            setVoiceError("Voice recording is not supported in this browser.");
            return;
        }

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
                ? "audio/webm;codecs=opus"
                : "audio/webm";
            const recorder = new MediaRecorder(stream, { mimeType });
            voiceRefs.current.mediaStream = stream;
            voiceRefs.current.mediaRecorder = recorder;
            voiceRefs.current.finalTranscript = "";
            voiceRefs.current.recordedAudioUrl = null;

            sendVoiceSocketEvent({
                type: "audio_start",
                language: voiceRefs.current.selectedLanguage,
                mime_type: mimeType,
            });

            recorder.ondataavailable = (event) => {
                if (!event.data || event.data.size === 0) {
                    return;
                }

                void blobToBase64(event.data)
                    .then((audioBase64) => {
                        sendVoiceSocketEvent({
                            type: "audio_chunk",
                            audio_base64: audioBase64,
                        });
                    })
                    .catch(() => {
                        setVoiceError("Unable to process microphone audio.");
                    });
            };

            recorder.onerror = () => {
                setVoiceStatus("idle");
                setVoiceError("Voice recording failed. Please try again.");
            };

            recorder.onstop = () => {
                stream.getTracks().forEach((track) => track.stop());
                voiceRefs.current.mediaStream = null;
                voiceRefs.current.mediaRecorder = null;
                sendVoiceSocketEvent({ type: "audio_stop" });
                setVoiceStatus("processing");
            };

            recorder.start(1000);
            setVoiceStatus("listening");
        } catch {
            setVoiceStatus("idle");
            setVoiceError("Microphone access was blocked. You can still type your message.");
        }
    }

    function handlePlayAssistantMessage(message: ChatMessage): void {
        const canPlay = Boolean(message.audioUrl) || Boolean(accessToken && user) || voiceCapabilities.synthesis;
        if (!canPlay) {
            setVoiceError("Audio playback is not available on this device.");
            return;
        }

        stopAssistantPlayback();
        requestBackendAssistantAudio(message);
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
