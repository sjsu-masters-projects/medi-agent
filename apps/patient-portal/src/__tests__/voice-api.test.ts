import { describe, expect, it, vi } from "vitest";
import {
    buildVoiceAudioDataUrl,
    buildVoiceWebSocketUrl,
    isVoiceSocketEvent,
    normalizeVoiceEventLanguage,
} from "@/services/voice-api";

describe("voice-api", () => {
    it("builds secure websocket URLs from the backend URL", () => {
        vi.stubEnv("NEXT_PUBLIC_BACKEND_URL", "https://api.mediagent.live");

        expect(buildVoiceWebSocketUrl("patient-1", "token-1")).toBe(
            "wss://api.mediagent.live/ws/voice/patient-1?token=token-1",
        );
    });

    it("builds local websocket URLs from localhost backend URL", () => {
        vi.stubEnv("NEXT_PUBLIC_BACKEND_URL", "http://localhost:8000");

        expect(buildVoiceWebSocketUrl("patient-1", "token-1")).toBe(
            "ws://localhost:8000/ws/voice/patient-1?token=token-1",
        );
    });

    it("recognizes supported voice socket events only", () => {
        expect(isVoiceSocketEvent({ type: "assistant_audio_ready" })).toBe(true);
        expect(isVoiceSocketEvent({ type: "transcript_final" })).toBe(true);
        expect(isVoiceSocketEvent({ type: "unknown" })).toBe(false);
        expect(isVoiceSocketEvent(null)).toBe(false);
    });

    it("builds playable audio data URLs", () => {
        expect(
            buildVoiceAudioDataUrl({
                audio_base64: "YWJj",
                encoding: "mp3",
                language: "en-US",
                mime_type: "audio/mpeg",
                model: "aura-2-asteria-en",
                type: "assistant_audio_ready",
            }),
        ).toBe("data:audio/mpeg;base64,YWJj");
    });

    it("normalizes voice event language", () => {
        expect(normalizeVoiceEventLanguage("es")).toBe("es-MX");
        expect(normalizeVoiceEventLanguage(null)).toBe("en-US");
    });
});
