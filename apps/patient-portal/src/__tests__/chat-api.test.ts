import { buildChatWebSocketUrl, mapChatMessageFromApi } from "@/services/chat-api";
import { Locale } from "@/types";
import { describe, expect, it, vi } from "vitest";

describe("chat API helpers", () => {
    it("maps snake_case chat rows to shared camelCase contract", () => {
        const mapped = mapChatMessageFromApi({
            audio_url: "https://cdn/audio.mp3",
            content: "hello",
            created_at: "2026-04-17T10:00:00Z",
            id: "msg-1",
            intent: "general",
            language: Locale.EN_US,
            patient_id: "patient-1",
            role: "assistant",
        });

        expect(mapped).toEqual({
            audioUrl: "https://cdn/audio.mp3",
            content: "hello",
            createdAt: "2026-04-17T10:00:00Z",
            id: "msg-1",
            intent: "general",
            language: Locale.EN_US,
            patientId: "patient-1",
            role: "assistant",
        });
    });

    it("builds websocket URL using backend origin and token", () => {
        vi.stubEnv("NEXT_PUBLIC_BACKEND_URL", "https://api.example.com");

        const url = buildChatWebSocketUrl("patient-1", "abc123==");

        expect(url).toBe("wss://api.example.com/ws/chat/patient-1?token=abc123%3D%3D");

        vi.unstubAllEnvs();
    });
});
