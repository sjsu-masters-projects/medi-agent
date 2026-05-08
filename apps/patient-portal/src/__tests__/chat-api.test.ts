import {
    buildChatWebSocketUrl,
    mapChatMessageFromApi,
    mapClinicianMessageFromApi,
} from "@/services/chat-api";
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

    it("maps clinician messages to system chat messages", () => {
        const mapped = mapClinicianMessageFromApi({
            body: "Please schedule labs this week.",
            channel: "in_app",
            clinician_id: "clinician-1",
            created_at: "2026-04-17T10:00:00Z",
            id: "clinician-message-1",
            is_read: false,
            patient_id: "patient-1",
            subject: "Lab follow-up",
        });

        expect(mapped).toMatchObject({
            content: "Lab follow-up\n\nPlease schedule labs this week.",
            createdAt: "2026-04-17T10:00:00Z",
            id: "clinician-message-clinician-message-1",
            patientId: "patient-1",
            role: "system",
        });
    });

    it("adds document context and session parameters to websocket URLs", () => {
        vi.stubEnv("NEXT_PUBLIC_BACKEND_URL", "https://api.example.com");

        const url = buildChatWebSocketUrl("patient-1", "abc123==", {
            documentId: "doc-1",
            sessionId: "records",
        });

        expect(url).toBe(
            "wss://api.example.com/ws/chat/patient-1?token=abc123%3D%3D&context=doc%3Adoc-1&session_id=records",
        );

        vi.unstubAllEnvs();
    });
});
