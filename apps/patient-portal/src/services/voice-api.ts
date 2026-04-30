import { normalizeLocale, type Locale } from "@/types";

export interface VoiceReadyEvent {
    type: "voice_ready";
    stt_supported: boolean;
    tts_supported: boolean;
    max_audio_bytes: number;
}

export interface AssistantAudioReadyEvent {
    type: "assistant_audio_ready";
    audio_base64: string;
    mime_type: string;
    encoding: string;
    language: Locale;
    model: string;
}

export interface TranscriptFinalEvent {
    type: "transcript_final";
    transcript: string;
    language: Locale;
    model: string;
}

export interface VoiceErrorEvent {
    type: "voice_error";
    code?: string;
    message?: string;
}

export type VoiceSocketEvent =
    | AssistantAudioReadyEvent
    | TranscriptFinalEvent
    | VoiceErrorEvent
    | VoiceReadyEvent
    | { type: "pong" };

export function buildVoiceWebSocketUrl(patientId: string, token: string): string {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
    const parsed = new URL(backendBaseUrl);
    parsed.protocol = parsed.protocol === "https:" ? "wss:" : "ws:";
    parsed.pathname = `/ws/voice/${patientId}`;
    parsed.search = "";
    parsed.searchParams.set("token", token);
    return parsed.toString();
}

export function isVoiceSocketEvent(value: unknown): value is VoiceSocketEvent {
    if (!value || typeof value !== "object") {
        return false;
    }

    const eventType = (value as { type?: unknown }).type;
    return (
        eventType === "assistant_audio_ready" ||
        eventType === "pong" ||
        eventType === "transcript_final" ||
        eventType === "voice_error" ||
        eventType === "voice_ready"
    );
}

export function buildVoiceAudioDataUrl(event: AssistantAudioReadyEvent): string {
    return `data:${event.mime_type};base64,${event.audio_base64}`;
}

export function normalizeVoiceEventLanguage(language: unknown): Locale {
    return normalizeLocale(typeof language === "string" ? language : undefined);
}
