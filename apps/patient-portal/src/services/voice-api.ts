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
    audio_url?: string | null;
    mime_type: string;
    encoding: string;
    language: Locale;
    model: string;
    signed_url?: string | null;
}

export interface TranscriptFinalEvent {
    type: "transcript_final";
    transcript: string;
    language: Locale;
    model: string;
}

export interface TranscriptPartialEvent {
    type: "transcript_partial";
    transcript: string;
    language: Locale;
    model: string;
}

export interface AudioStreamStartedEvent {
    type: "audio_stream_started";
}

export interface AudioStreamCompleteEvent {
    type: "audio_stream_complete";
    audio_url?: string | null;
    signed_url?: string | null;
}

export interface VoiceErrorEvent {
    type: "voice_error";
    code?: string;
    message?: string;
}

export type VoiceSocketEvent =
    | AudioStreamCompleteEvent
    | AudioStreamStartedEvent
    | AssistantAudioReadyEvent
    | TranscriptFinalEvent
    | TranscriptPartialEvent
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
        eventType === "audio_stream_complete" ||
        eventType === "audio_stream_started" ||
        eventType === "pong" ||
        eventType === "transcript_final" ||
        eventType === "transcript_partial" ||
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

export async function blobToBase64(blob: Blob): Promise<string> {
    const buffer = await blob.arrayBuffer();
    let binary = "";
    const bytes = new Uint8Array(buffer);
    for (const byte of bytes) {
        binary += String.fromCharCode(byte);
    }
    return window.btoa(binary);
}
