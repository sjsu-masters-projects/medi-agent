"use client";

import { useEffect, useEffectEvent, useRef, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useDispatch, useSelector } from "react-redux";
import { getPatientChatCopy } from "@/content/chat-copy";
import { useChatTurnRecovery, type RecoverableTurn } from "@/hooks/use-chat-turn-recovery";
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
    newConversationId,
    todayConversationId,
    isInternalChatAlert,
    mapClinicianMessageFromApi,
    mapChatMessageFromApi,
    type ChatDocumentContextApi,
    type ChatTurnApi,
} from "@/services/chat-api";
import {
    buildVoiceAudioDataUrl,
    buildVoiceWebSocketUrl,
    blobToBase64,
    isVoiceSocketEvent,
    normalizeVoiceEventLanguage,
} from "@/services/voice-api";
import { socketAuthProtocols } from "@/services/ws-auth";
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
    type ChatMessage,
    type Locale as ChatLocale,
} from "@/types";

const MAX_RECOVERY_POLLS = 60;
const HANDS_FREE_STORAGE_KEY = "patient-portal.chat.handsFree";
const FALLBACK_DOCUMENT_NAME = "medical record";

function resolveInitialHandsFree(): boolean {
    if (typeof window === "undefined") {
        return false;
    }
    return window.localStorage.getItem(HANDS_FREE_STORAGE_KEY) === "true";
}

function composeDictatedInput(prefix: string, transcript: string): string {
    const trimmedTranscript = transcript.trim();
    if (!trimmedTranscript) {
        return prefix;
    }
    if (!prefix) {
        return trimmedTranscript;
    }
    const needsSpace = !/\s$/.test(prefix);
    return `${prefix}${needsSpace ? " " : ""}${trimmedTranscript}`;
}
const MAX_CHAT_RECONNECT_ATTEMPTS = 5;
const BASE_CHAT_RECONNECT_DELAY_MS = 800;
const MAX_CHAT_RECONNECT_DELAY_MS = 8_000;

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

// The document id comes from useSearchParams, not window.location: during in-app
// navigation from Records, window.location still shows the previous page while the chat
// page renders, so the handoff was lost and the inbox opened instead of Nora.
function resolveInitialDocumentContext(documentId: string | null): PendingChatDocumentContext | null {
    if (typeof window === "undefined") {
        return null;
    }
    return consumePendingChatDocumentContext(documentId);
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
    receivingStream: boolean;
    canPlayAssistantAudio: boolean;
    connectionStatus: RootState["chat"]["connectionStatus"];
    documentContext: PendingChatDocumentContext | null;
    /** The conversation's document could no longer be read. */
    documentUnavailable: boolean;
    error: string | null;
    handsFreeMode: boolean;
    input: string;
    isTyping: boolean;
    loading: boolean;
    messages: ChatMessage[];
    selectedLanguage: ChatLocale;
    safetyNotice: string | null;
    sessionId: string;
    voiceError: string | null;
    voiceInterimTranscript: string;
    voiceStatus: VoiceStatus;
    recoveryTurns: RecoverableTurn[];
    turnBusy: boolean;
}

interface PatientChatSessionActions {
    reconnectChat: () => void;
    retryTurn: (id: string) => void;
    dismissTurn: (id: string) => void;
    dismissDocumentContext: () => void;
    dismissSafetyNotice: () => void;
    handleHandsFreeToggle: () => void;
    handleMicClick: () => void;
    handlePlayAssistantMessage: (message: ChatMessage) => void;
    handleSend: (event: FormEvent<HTMLFormElement>) => void;
    openConversation: (sessionId: string) => void;
    setInput: (value: string) => void;
    startNewConversation: () => void;
}

export function usePatientChatSession(selectedLanguage: ChatLocale = DEFAULT_LOCALE): PatientChatSessionState & PatientChatSessionActions {
    const dispatch = useDispatch<AppDispatch>();
    const router = useRouter();
    const searchParams = useSearchParams();
    const { accessToken, user } = useSelector((state: RootState) => state.auth);
    const { connectionStatus, error, isTyping, loading, messages } = useSelector(
        (state: RootState) => state.chat,
    );

    const [initialDocumentContext] = useState<PendingChatDocumentContext | null>(() =>
        resolveInitialDocumentContext(searchParams.get("document")),
    );
    const [initialDocumentId] = useState<string | null>(
        () => initialDocumentContext?.documentId ?? (searchParams.get("document")?.trim() || null),
    );
    // Today's conversation by default; a question about a document starts its own.
    const [sessionId, setSessionId] = useState<string>(() =>
        /^[A-Za-z0-9_-]{1,64}$/.test(searchParams.get("session") ?? "")
            ? searchParams.get("session")!
            : searchParams.get("document") ? newConversationId() : todayConversationId(),
    );
    const [voiceCapabilities] = useState(getVoiceCapabilities);
    const [input, setInput] = useState(
        () => initialDocumentContext?.suggestedQuestion ?? "",
    );
    const [assistantDraft, setAssistantDraft] = useState("");
    const [assistantDraftStartedAt, setAssistantDraftStartedAt] = useState<string | null>(null);
    const [handsFreeMode, setHandsFreeMode] = useState<boolean>(resolveInitialHandsFree);
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
    // A dismissal travels with the next connection so the server stops restoring the
    // document it saved for this conversation; clearing it here alone brought it back.
    const [documentDismissed, setDocumentDismissed] = useState(searchParams.get("focus") === "none");
    const [documentUnavailable, setDocumentUnavailable] = useState(false);
    const [safetyNotice, setSafetyNotice] = useState<string | null>(null);
    const [reconnectSignal, setReconnectSignal] = useState(0);
    // True while THIS tab receives the reply's stream (it sent the turn, or the server
    // replayed the draft to it). Only then is "Nora is typing" the whole story: the
    // recovery card is for tabs that are not receiving the stream.
    const [receivingStream, setReceivingStream] = useState(false);
    // What the socket was opened with; later focus changes are sent over the open socket.
    const connectedFocusRef = useRef<{ documentId: string | null; dismissed: boolean } | null>(null);
    const connectedScopeRef = useRef<string | null>(null);

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
        // Set true when the user sends a turn via the mic in hands-free mode;
        // consumed and reset on the next assistant_complete to trigger
        // auto-playback. Typed turns and dictation turns leave this false.
        autoPlayNextAssistantMessage: boolean;
        // Existing input text captured at the moment recording starts, so
        // dictated transcript can be appended (matches iOS keyboard dictation).
        inputPrefixForDictation: string;
        handsFreeMode: boolean;
    }>({
        finalTranscript: "",
        mediaRecorder: null,
        mediaStream: null,
        playbackStop: null,
        pendingPlayback: null,
        queuedVoiceEvents: [],
        recognition: null,
        recordedAudioUrl: null,
        selectedLanguage,
        autoPlayNextAssistantMessage: false,
        inputPrefixForDictation: "",
        handsFreeMode: resolveInitialHandsFree(),
    });
    const socketRef = useRef<WebSocket | null>(null);
    const durableReadyRef = useRef(false);
    const recovery = useChatTurnRecovery(`${user?.id ?? ""}:${sessionId}`, socketRef);
    const receiveTurns = useEffectEvent((rows: ChatTurnApi[], snapshot = false) => {
        recovery.accept(rows, snapshot);
        if (error === "CHAT_TURN_BUSY" && !rows.some((row) => row.status === "processing")) dispatch(setChatError(null));
        if (snapshot || rows.some((row) => row.status !== "processing")) {
            setAssistantDraft("");
            setAssistantDraftStartedAt(null);
            dispatch(setTyping(rows.some((row) => row.status === "processing")));
        }
        if (!rows.some((row) => row.status === "processing")) setReceivingStream(false);
    });
    const rejectTurn = useEffectEvent((id: string) => {
        const content = recovery.reject(id);
        if (content) setInput((current) => !current || current === content ? content : `${content}\n\n${current}`);
    });
    const voiceSocketRef = useRef<WebSocket | null>(null);
    const reconnectRef = useRef<{
        attempts: number;
        timer: ReturnType<typeof setTimeout> | null;
    }>({
        attempts: 0,
        timer: null,
    });

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

        if (!durableReadyRef.current || !socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) {
            dispatch(setChatError("CHAT_STARTUP_UNAVAILABLE"));
            voiceRefs.current.autoPlayNextAssistantMessage = false;
            setInput((current) => current || trimmedContent);
            setVoiceStatus("idle");
            return;
        }

        if (documentUnavailable || !recovery.send(trimmedContent,
            voiceRefs.current.selectedLanguage, activeDocumentId, audioUrl)) return;

        setReceivingStream(true);
        // Feedback must begin when the user sends, not after the model has classified the turn.
        // `assistant_complete`, socket errors, and socket close all clear this state.
        dispatch(setTyping(true));
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

        const socket = new WebSocket(
            buildVoiceWebSocketUrl(user.id),
            socketAuthProtocols(accessToken),
        );
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
                setInput(
                    composeDictatedInput(
                        voiceRefs.current.inputPrefixForDictation,
                        payload.transcript,
                    ),
                );
                return;
            }

            if (payload.type === "transcript_final") {
                voiceRefs.current.finalTranscript = payload.transcript;
                setVoiceInterimTranscript("");
                setInput(
                    composeDictatedInput(
                        voiceRefs.current.inputPrefixForDictation,
                        payload.transcript,
                    ),
                );
                return;
            }

            if (payload.type === "audio_stream_complete") {
                const transcript = voiceRefs.current.finalTranscript.trim();
                const audioUrl = payload.audio_url ?? null;
                voiceRefs.current.recordedAudioUrl = audioUrl;
                voiceRefs.current.finalTranscript = "";
                setVoiceInterimTranscript("");

                if (!transcript) {
                    setVoiceStatus("idle");
                    return;
                }

                if (voiceRefs.current.handsFreeMode) {
                    // Hands-free: auto-send + auto-play TTS reply.
                    voiceRefs.current.autoPlayNextAssistantMessage = true;
                    setVoiceStatus("processing");
                    sendChatMessage(transcript, audioUrl ?? undefined);
                } else {
                    // Default dictation: leave transcript in input, user reviews
                    // and taps Send. The transcript is already in `input` from
                    // the transcript_final handler above.
                    voiceRefs.current.inputPrefixForDictation = "";
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

    function clearChatReconnectTimer(): void {
        const timer = reconnectRef.current.timer;
        if (timer) {
            clearTimeout(timer);
            reconnectRef.current.timer = null;
        }
    }

    function scheduleChatReconnect(): void {
        if (reconnectRef.current.timer) {
            return;
        }

        const attempt = reconnectRef.current.attempts;
        if (attempt >= MAX_CHAT_RECONNECT_ATTEMPTS) {
            dispatch(setChatError("Live chat is offline. Refresh the page to reconnect."));
            return;
        }

        const delay = Math.min(
            BASE_CHAT_RECONNECT_DELAY_MS * 2 ** attempt,
            MAX_CHAT_RECONNECT_DELAY_MS,
        );
        reconnectRef.current.attempts = attempt + 1;
        reconnectRef.current.timer = setTimeout(() => {
            reconnectRef.current.timer = null;
            setReconnectSignal((current) => current + 1);
        }, delay);
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
    const scheduleChatReconnectEvent = useEffectEvent(() => {
        scheduleChatReconnect();
    });

    useEffect(() => {
        voiceRefs.current.selectedLanguage = selectedLanguage;
    }, [selectedLanguage]);

    const applyDocumentRoute = useEffectEvent(() => {
        const requestedSession = searchParams.get("session");
        if (requestedSession && /^[A-Za-z0-9_-]{1,64}$/.test(requestedSession) && requestedSession !== sessionId) {
            setSessionId(requestedSession);
            setDocumentContext(null);
            setActiveDocumentId(searchParams.get("document"));
            setDocumentDismissed(searchParams.get("focus") === "none");
            setDocumentUnavailable(false);
            return;
        }
        const documentId = searchParams.get("document")?.trim();
        if (!documentId) return;
        if (documentId !== activeDocumentId) {
            const next = resolveInitialDocumentContext(documentId);
            setActiveDocumentId(documentId);
            setDocumentContext(next);
            setDocumentDismissed(false);
            setDocumentUnavailable(false);
            if (next?.suggestedQuestion) setInput((draft) => draft || next.suggestedQuestion || "");
        }
        if (searchParams.get("session") !== sessionId) {
            router.replace(`/chat?session=${encodeURIComponent(sessionId)}&document=${encodeURIComponent(documentId)}`);
        }
    });
    useEffect(() => { applyDocumentRoute(); }, [searchParams]);

    // A reply still being saved by another tab or connection is polled while it is in
    // flight only, and never for more than MAX_RECOVERY_POLLS (the server deadline is shorter).
    const turnInFlight = recovery.turns.some((turn) => turn.status === "processing" || turn.status === "unknown");
    useEffect(() => {
        if (!turnInFlight) return;
        let polls = 0;
        const recover = () => {
            if (polls >= MAX_RECOVERY_POLLS) return;
            if (document.visibilityState === "visible" && socketRef.current?.readyState === WebSocket.OPEN) {
                polls += 1;
                socketRef.current.send(JSON.stringify({ type: "recover_turns" }));
            }
        };
        const timer = window.setInterval(recover, 5000);
        document.addEventListener("visibilitychange", recover);
        window.addEventListener("focus", recover);
        return () => { window.clearInterval(timer); document.removeEventListener("visibilitychange", recover); window.removeEventListener("focus", recover); };
    }, [turnInFlight, sessionId]);

    // A silent token refresh replaces the token and user objects. The socket must not be
    // rebuilt for that (it interrupted the live reply); it reads them once per connection.
    const connectionUserId = user?.id ?? null;
    const hasAccessToken = Boolean(accessToken);
    // The socket's identity is the patient and the conversation (plus an explicit
    // reconnect after a real close). Document focus is read once per connection and
    // later changes travel over the open socket, so attaching, dismissing or a URL
    // search-param change never closes a socket that is receiving a reply.
    const readSession = useEffectEvent(() => ({ accessToken, user, activeDocumentId, documentDismissed }));
    useEffect(() => {
        const { accessToken, user, activeDocumentId, documentDismissed } = readSession();
        if (!accessToken || !user) {
            return;
        }

        let isMounted = true;
        let socketHistoryReceived = false;
        // A reconnect to the same conversation keeps what is on screen; only a different
        // patient or conversation starts clean.
        const scope = `${user.id}:${sessionId}`;
        const sameScope = connectedScopeRef.current === scope;
        connectedScopeRef.current = scope;
        connectedFocusRef.current = { documentId: activeDocumentId, dismissed: documentDismissed };
        if (!sameScope) {
            dispatch(clearChatState());
            dispatch(setLoading(true));
        }

        const historyRequest = sameScope ? Promise.resolve(null) : fetchChatHistory(user.id, accessToken, sessionId);
        historyRequest
            .then((history) => {
                if (history === null) return;
                if (!isMounted || socketHistoryReceived) {
                    return;
                }

                dispatch(
                    setMessages(
                        history.length > 0
                            ? history
                            : [buildWelcomeMessage(user.id, voiceRefs.current.selectedLanguage)],
                    ),
                );
            })
            .catch(() => {
                if (!isMounted || socketHistoryReceived) {
                    return;
                }

                dispatch(setMessages([buildWelcomeMessage(user.id, voiceRefs.current.selectedLanguage)]));
                dispatch(setChatError("Unable to load chat history. Live chat is still available."));
            })
            .finally(() => {
                if (isMounted && !sameScope) {
                    dispatch(setLoading(false));
                }
            });

        dispatch(setConnectionStatus("connecting"));
        dispatch(setChatError(null));

        const socket = new WebSocket(
            buildChatWebSocketUrl(user.id, {
                durableTurns: true,
                documentId: activeDocumentId,
                sessionId,
                ...(documentDismissed && !activeDocumentId ? { documentDismissed: true } : {}),
            }),
            socketAuthProtocols(accessToken),
        );
        socketRef.current = socket;
        durableReadyRef.current = false;
        let durableReady = false;
        const handshakeTimer = window.setTimeout(() => {
            if (isMounted && !durableReady) {
                dispatch(setConnectionStatus("error"));
                dispatch(setChatError("CHAT_STARTUP_UNAVAILABLE"));
                socket.close();
            }
        }, 15000);

        socket.onopen = () => {
            if (!isMounted) {
                return;
            }

            clearChatReconnectTimer();
            // A socket opening alone does not prove the backend supports safe retries.
            // Keep sending disabled until its durable recovery handshake arrives.
            dispatch(setChatError(null));
        };

        socket.onmessage = (event) => {
            if (!isMounted) return;
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
                case "chat_turn": receiveTurns([payload.turn]); return;
                case "chat_turns":
                    durableReady = true;
                    durableReadyRef.current = true;
                    reconnectRef.current.attempts = 0;
                    window.clearTimeout(handshakeTimer);
                    dispatch(setConnectionStatus("connected"));
                    receiveTurns(payload.turns, true);
                    return;
                case "chat_history": {
                    socketHistoryReceived = true;
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
                        setDocumentDismissed(false);
                        setDocumentUnavailable(false);
                    }
                    return;
                }
                case "chat_context_unavailable":
                    // Nora would otherwise answer from the general chart while the card
                    // still named a document she cannot read.
                    setDocumentContext(null);
                    setDocumentUnavailable(true);
                    return;
                case "clinician_message":
                    // Also protect clients during staggered backend/frontend rollout.
                    if (!isInternalChatAlert(payload.message)) {
                        dispatch(addMessage(mapClinicianMessageFromApi(payload.message)));
                    }
                    return;
                case "appointment_proposal": {
                    const spanish = voiceRefs.current.selectedLanguage === "es-MX";
                    const clinician = payload.proposal.clinician_name
                        ? `${spanish ? " con" : " with"} ${payload.proposal.clinician_name}`
                        : "";
                    const reason = payload.proposal.reason
                        ? `\n\n${spanish ? "Motivo" : "Reason"}: ${payload.proposal.reason}`
                        : "";
                    dispatch(
                        addMessage({
                            content: `${spanish ? "Solicitud de cita registrada" : "Appointment request noted"}${clinician}. ${payload.proposal.next_step}${reason}`,
                            createdAt: new Date().toISOString(),
                            id: `appointment-proposal-${payload.proposal.proposal_id}`,
                            language: voiceRefs.current.selectedLanguage,
                            patientId: user.id,
                            role: ChatRole.SYSTEM,
                        }),
                    );
                    return;
                }
                case "appointment_created":
                    dispatch(
                        addMessage({
                            content: `${voiceRefs.current.selectedLanguage === "es-MX" ? "Cita programada para" : "Appointment scheduled for"} ${new Intl.DateTimeFormat(
                                voiceRefs.current.selectedLanguage,
                                {
                                    dateStyle: "medium",
                                    timeStyle: "short",
                                },
                            ).format(new Date(payload.appointment.scheduled_at))}.`,
                            createdAt: new Date().toISOString(),
                            id: `appointment-created-${payload.appointment.id}`,
                            language: voiceRefs.current.selectedLanguage,
                            patientId: user.id,
                            role: ChatRole.SYSTEM,
                        }),
                    );
                    return;
                case "user_message_saved":
                    dispatch(addMessage(mapChatMessageFromApi(payload.message)));
                    return;
                case "assistant_start":
                    setReceivingStream(true);
                    resetAssistantDraft();
                    setAssistantDraftStartedAt(new Date().toISOString());
                    dispatch(setTyping(true));
                    return;
                case "assistant_chunk":
                    setReceivingStream(true);
                    setAssistantDraft((current) => `${current}${payload.content}`);
                    dispatch(setTyping(true));
                    return;
                case "assistant_complete": {
                    const assistantMessage = mapChatMessageFromApi(payload.message);
                    setReceivingStream(false);
                    resetAssistantDraft();
                    dispatch(setTyping(false));
                    dispatch(addMessage(assistantMessage));

                    // Auto-play only when this turn was voice-initiated.
                    // Typed turns never trigger TTS automatically.
                    if (voiceRefs.current.autoPlayNextAssistantMessage) {
                        voiceRefs.current.autoPlayNextAssistantMessage = false;
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
                    if (payload.client_message_id && ["CHAT_TURN_BUSY", "CHAT_TURN_CONFLICT", "CHAT_TURN_INVALID", "CHAT_DOCUMENT_UNAVAILABLE", "CHAT_DOCUMENT_CHANGED"].includes(payload.code ?? "")) {
                        rejectTurn(payload.client_message_id);
                    }
                    if (["CHAT_DOCUMENT_UNAVAILABLE", "CHAT_DOCUMENT_CHANGED"].includes(payload.code ?? "")) setDocumentUnavailable(true);
                    setReceivingStream(false);
                    resetAssistantDraft();
                    dispatch(setTyping(false));
                    dispatch(setChatError(payload.code === "CHAT_TURN_BUSY" || payload.code === "CHAT_TURN_EXPIRED" ? payload.code : payload.message || "Chat request failed."));
                    // The saved message and its Retry card come from the server's turn list.
                    if ((payload.code === "CHAT_TURN_BUSY" || payload.code === "CHAT_TURN_EXPIRED") && socket.readyState === WebSocket.OPEN) {
                        socket.send(JSON.stringify({ type: "recover_turns" }));
                    }
                    // A backend error mid-turn invalidates pending auto-play
                    // but does NOT take the mic offline; user can retry.
                    voiceRefs.current.autoPlayNextAssistantMessage = false;
                    setVoiceStatus((prev) =>
                        prev === "processing" || prev === "playing" ? "idle" : prev,
                    );
                    return;
                default:
                    return;
            }
        };

        socket.onerror = () => {
            if (!isMounted) {
                return;
            }

            // A broken connection is not a failed reply: the server keeps running the turn
            // and this tab re-subscribes on reconnect. Only a socket that never became
            // ready is reported as an error.
            resetAssistantDraft();
            setReceivingStream(false);
            dispatch(setConnectionStatus("error"));
            dispatch(setTyping(false));
            if (!durableReady) dispatch(setChatError("Live chat connection encountered an issue."));
            voiceRefs.current.autoPlayNextAssistantMessage = false;
            setVoiceStatus((prev) => (prev === "processing" || prev === "playing" ? "idle" : prev));
        };

        socket.onclose = () => {
            if (!isMounted) {
                return;
            }

            durableReadyRef.current = false;
            // The draft is replayed by the server when this tab re-subscribes.
            resetAssistantDraft();
            setReceivingStream(false);
            if (!durableReady) {
                dispatch(setConnectionStatus("error"));
                dispatch(setChatError("CHAT_STARTUP_UNAVAILABLE"));
                dispatch(setTyping(false));
                return;
            }
            dispatch(setConnectionStatus("disconnected"));
            dispatch(setTyping(false));
            voiceRefs.current.autoPlayNextAssistantMessage = false;
            // Don't change voiceStatus on close — if user is mid-recording on
            // the voice WS that's an independent connection. Only reset when
            // we were waiting on the chat WS for a reply.
            setVoiceStatus((prev) => (prev === "processing" || prev === "playing" ? "idle" : prev));
            scheduleChatReconnectEvent();
        };

        return () => {
            isMounted = false;
            window.clearTimeout(handshakeTimer);
            durableReadyRef.current = false;
            stopSpeechRecognition();
            stopAssistantPlayback();
            closeVoiceSocket();
            socketRef.current = null;
            socket.close();
        };
    }, [connectionUserId, hasAccessToken, dispatch, reconnectSignal, sessionId]);

    // Attach or dismiss a document without rebuilding the socket.
    useEffect(() => {
        const socket = socketRef.current;
        const last = connectedFocusRef.current;
        if (!socket || socket.readyState !== WebSocket.OPEN || !durableReadyRef.current || !last) return;
        const dismissed = documentDismissed && !activeDocumentId;
        if (last.documentId === activeDocumentId && last.dismissed === dismissed) return;
        connectedFocusRef.current = { documentId: activeDocumentId, dismissed };
        socket.send(JSON.stringify({ type: "document_focus", document_id: activeDocumentId }));
    }, [activeDocumentId, documentDismissed]);

    useEffect(() => {
        return () => {
            stopSpeechRecognition();
            stopMediaRecorder();
            stopAssistantVoicePlayback();
            closeVoiceSocket();
            clearChatReconnectTimer();
        };
    }, []);

    function dismissDocumentContext(): void {
        setActiveDocumentId(null);
        setDocumentContext(null);
        setDocumentDismissed(true);
        setDocumentUnavailable(false);
        router.replace(`/chat?session=${encodeURIComponent(sessionId)}&focus=none`);
    }

    function openConversation(nextSessionId: string): void {
        if (!/^[A-Za-z0-9_-]{1,64}$/.test(nextSessionId)) return;
        router.replace(`/chat?session=${encodeURIComponent(nextSessionId)}`);
        if (nextSessionId === sessionId) return;
        setActiveDocumentId(null);
        setDocumentContext(null);
        setDocumentDismissed(false);
        setDocumentUnavailable(false);
        setSessionId(nextSessionId);
    }

    function startNewConversation(): void {
        openConversation(newConversationId());
        setInput("");
    }

    function dismissSafetyNotice(): void {
        setSafetyNotice(null);
    }

    function handleSend(event: FormEvent<HTMLFormElement>): void {
        event.preventDefault();
        sendChatMessage(input);
    }

    function handleHandsFreeToggle(): void {
        const next = !handsFreeMode;
        setHandsFreeMode(next);
        voiceRefs.current.handsFreeMode = next;
        if (typeof window !== "undefined") {
            window.localStorage.setItem(HANDS_FREE_STORAGE_KEY, next ? "true" : "false");
        }
        // Turning hands-free off mid-flight: stop any in-progress playback.
        if (!next) {
            stopAssistantPlayback();
            voiceRefs.current.autoPlayNextAssistantMessage = false;
        }
    }

    function handleMicClick(): void {
        // Tap while listening = stop and let onstop/onEnd handle send.
        if (voiceStatus === "listening") {
            stopMediaRecorder();
            stopSpeechRecognition();
            return;
        }

        // While we're waiting on transcription, ignore taps so the user
        // can't start a new recording before the previous transcript arrives.
        if (voiceStatus === "processing") {
            return;
        }

        // While the assistant is speaking, tapping mic interrupts playback so
        // the user can speak again immediately (matches phone-assistant UX).
        if (voiceStatus === "playing") {
            stopAssistantPlayback();
            setVoiceStatus("idle");
        }

        if (voiceStatus === "unsupported") {
            setVoiceError("Voice mode is not available on this device.");
            return;
        }

        // Capture whatever the user has already typed so dictated text appends
        // to it instead of replacing it.
        voiceRefs.current.inputPrefixForDictation = input;

        // Prefer backend recording (Deepgram via voice WS) when available.
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

        // Browser SpeechRecognition fallback. Default behavior matches the
        // backend path: transcript fills the input box; user reviews and
        // taps Send. In hands-free mode the transcript auto-sends.
        const controller = createSpeechRecognitionController(voiceRefs.current.selectedLanguage, {
            onEnd: (finalTranscript) => {
                voiceRefs.current.recognition = null;
                setVoiceInterimTranscript("");

                if (!finalTranscript) {
                    setVoiceStatus("idle");
                    return;
                }

                const composed = composeDictatedInput(
                    voiceRefs.current.inputPrefixForDictation,
                    finalTranscript,
                );

                if (voiceRefs.current.handsFreeMode) {
                    voiceRefs.current.autoPlayNextAssistantMessage = true;
                    setVoiceStatus("processing");
                    sendChatMessage(composed);
                } else {
                    setInput(composed);
                    voiceRefs.current.inputPrefixForDictation = "";
                    setVoiceStatus("idle");
                }
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
            onTranscript: ({ interimTranscript }) => {
                setVoiceInterimTranscript(interimTranscript);
                setInput(
                    composeDictatedInput(
                        voiceRefs.current.inputPrefixForDictation,
                        interimTranscript,
                    ),
                );
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
        reconnectChat: () => { clearChatReconnectTimer(); reconnectRef.current.attempts = 0; setReconnectSignal((current) => current + 1); },
        recoveryTurns: recovery.turns,
        turnBusy: recovery.turnBusy,
        retryTurn: (id: string) => { if (durableReadyRef.current && recovery.retry(id)) { setReceivingStream(true); dispatch(setTyping(true)); dispatch(setChatError(null)); } },
        dismissTurn: recovery.dismiss,
        assistantDraft,
        assistantDraftStartedAt,
        receivingStream,
        canPlayAssistantAudio,
        connectionStatus,
        dismissDocumentContext,
        dismissSafetyNotice,
        documentContext,
        documentUnavailable,
        error,
        handleHandsFreeToggle,
        handleMicClick,
        handlePlayAssistantMessage,
        handleSend,
        handsFreeMode,
        input,
        isTyping,
        loading,
        messages,
        safetyNotice,
        openConversation,
        selectedLanguage,
        sessionId,
        setInput,
        startNewConversation,
        voiceError,
        voiceInterimTranscript,
        voiceStatus,
    };
}
