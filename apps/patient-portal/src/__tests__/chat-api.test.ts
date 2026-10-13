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

    it("builds websocket URL using backend origin, without the token", () => {
        vi.stubEnv("NEXT_PUBLIC_BACKEND_URL", "https://api.example.com");

        const url = buildChatWebSocketUrl("patient-1");

        expect(url).toBe("wss://api.example.com/ws/chat/patient-1");

        vi.unstubAllEnvs();
    });

    it("never puts the access token in the URL", () => {
        // The backend logs full request paths, so a token in the query string lands in the
        // access log as a replayable credential.
        vi.stubEnv("NEXT_PUBLIC_BACKEND_URL", "https://api.example.com");

        const url = buildChatWebSocketUrl("patient-1", { documentId: "doc-1" });

        expect(url).not.toContain("token");

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
            role: "clinician",
        });
    });

    it("adds document context and session parameters to websocket URLs", () => {
        vi.stubEnv("NEXT_PUBLIC_BACKEND_URL", "https://api.example.com");

        const url = buildChatWebSocketUrl("patient-1", {
            documentId: "doc-1",
            sessionId: "records",
        });

        expect(url).toBe(
            "wss://api.example.com/ws/chat/patient-1?context=doc%3Adoc-1&session_id=records",
        );

        vi.unstubAllEnvs();
    });

    it("asks the server to drop a dismissed document, unless a document is being attached", () => {
        vi.stubEnv("NEXT_PUBLIC_BACKEND_URL", "https://api.example.com");

        expect(buildChatWebSocketUrl("patient-1", { documentDismissed: true, sessionId: "chat-1" })).toBe(
            "wss://api.example.com/ws/chat/patient-1?context=none&session_id=chat-1",
        );
        expect(
            buildChatWebSocketUrl("patient-1", { documentDismissed: true, documentId: "doc-2" }),
        ).toBe("wss://api.example.com/ws/chat/patient-1?context=doc%3Adoc-2");

        vi.unstubAllEnvs();
    });
});

describe("conversation ids", () => {
    it("names today's conversation by local date and makes new ones unguessable", async () => {
        const { newConversationId, todayConversationId } = await import("@/services/chat-api");
        expect(todayConversationId(new Date(2026, 9, 1, 23, 30))).toBe("day-2026-10-01");
        const first = newConversationId();
        // The server accepts only [A-Za-z0-9_-]{1,64}; a UUID keeps it unpredictable.
        expect(first).toMatch(/^chat-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
        expect(first.length).toBeLessThanOrEqual(64);
        expect(newConversationId()).not.toBe(first);
    });
});
