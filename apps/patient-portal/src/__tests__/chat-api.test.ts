import {
    buildChatWebSocketUrl,
    fetchChatHistory,
    isChatSocketEvent,
    mapChatMessageFromApi,
    mapClinicianMessageFromApi,
} from "@/services/chat-api";
import { Locale } from "@/types";
import { describe, expect, it, vi } from "vitest";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/services/api", () => ({ api: { get } }));

const RESULT_ROW = {
    kind: "lab_result",
    name: "Potassium",
    value: "6.9",
    unit: "mmol/L",
    reference_range: "3.5-5.1",
    flag: "HH",
    flag_meaning: "critical",
    range_status: "above",
    panel: "Basic metabolic panel",
    observed_at: "10/01/2026",
    page: 1,
    reviewed: false,
};

const RESULTS_ATTACHMENT = {
    type: "document_results",
    document_id: "doc-1",
    file_name: "labs.pdf",
    title: { "en-US": "Lab report", "es-MX": "Reporte de laboratorio" },
    results: [RESULT_ROW],
};

const ASSISTANT_ROW = {
    content: "Your potassium was printed as critical.",
    created_at: "2026-10-13T10:00:00Z",
    id: "msg-2",
    language: Locale.EN_US,
    patient_id: "patient-1",
    role: "assistant" as const,
};

describe("chat API helpers", () => {
    it("opts into durable turns explicitly without changing the legacy socket URL", () => {
        expect(new URL(buildChatWebSocketUrl("patient", { durableTurns: true })).searchParams.get("turn_protocol")).toBe("1");
        expect(new URL(buildChatWebSocketUrl("patient")).searchParams.has("turn_protocol")).toBe(false);
    });
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

    it("maps the symptom note offer and drops one without a source message", () => {
        expect(mapChatMessageFromApi({ ...ASSISTANT_ROW, attachments: [
            { type: "symptom_intake_offer", source_message_id: "user-1" }, { type: "symptom_intake_offer" },
        ] }).attachments).toEqual([{ type: "symptom_intake_offer", sourceMessageId: "user-1" }]);
    });

    it("maps a server-built results card and leaves messages without one unchanged", () => {
        expect(mapChatMessageFromApi({ ...ASSISTANT_ROW, attachments: [RESULTS_ATTACHMENT] }).attachments).toEqual([
            {
                type: "document_results",
                documentId: "doc-1",
                fileName: "labs.pdf",
                title: { "en-US": "Lab report", "es-MX": "Reporte de laboratorio" },
                results: [RESULT_ROW],
            },
        ]);
        for (const attachments of [undefined, null, []]) {
            const mapped = mapChatMessageFromApi({ ...ASSISTANT_ROW, attachments });
            expect(mapped).toStrictEqual(mapChatMessageFromApi(ASSISTANT_ROW));
            expect("attachments" in mapped).toBe(false);
        }
    });

    it("drops malformed rows, malformed cards and unknown attachment types", () => {
        const mapped = mapChatMessageFromApi({
            ...ASSISTANT_ROW,
            attachments: [
                null,
                "document_results",
                { type: "medication_card", document_id: "doc-1", results: [RESULT_ROW] },
                { ...RESULTS_ATTACHMENT, document_id: "" },
                { ...RESULTS_ATTACHMENT, results: "Potassium 6.9" },
                { ...RESULTS_ATTACHMENT, results: [{ ...RESULT_ROW, value: "" }, { kind: "diagnosis", name: "x", value: "y" }] },
                {
                    ...RESULTS_ATTACHMENT,
                    document_id: "doc-2",
                    file_name: 42,
                    title: { "en-US": "  ", "es-MX": 7, fr: "Rapport" },
                    results: [{ name: "Missing kind", value: "1" }, { ...RESULT_ROW, flag_meaning: "dangerous", reviewed: "yes" }],
                },
            ],
        });
        expect(mapped.attachments).toEqual([
            {
                type: "document_results",
                documentId: "doc-2",
                fileName: null,
                title: {},
                results: [{ ...RESULT_ROW, flag_meaning: null, reviewed: false }],
            },
        ]);
        expect("attachments" in mapChatMessageFromApi({
            ...ASSISTANT_ROW,
            attachments: [{ type: "unknown" }, { ...RESULTS_ATTACHMENT, results: [] }],
        })).toBe(false);
    });

    it("keeps results cards on REST chat history", async () => {
        get.mockResolvedValueOnce([
            { ...ASSISTANT_ROW, id: "msg-1", attachments: null },
            { ...ASSISTANT_ROW, attachments: [RESULTS_ATTACHMENT] },
        ]);
        const history = await fetchChatHistory("patient-1", "token", "chat-1");
        expect(get).toHaveBeenCalledWith("/api/v1/chat/history/patient-1?session_id=chat-1", { token: "token" });
        expect(history[0].attachments).toBeUndefined();
        expect(history[1].attachments?.[0]).toMatchObject({ documentId: "doc-1", results: [RESULT_ROW] });
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

describe("isChatSocketEvent", () => {
    it("accepts queued turns and unknown statuses, and rejects malformed turn events", () => {
        const turn = { client_message_id: "a", status: "queued" };
        expect(isChatSocketEvent({ type: "chat_turn", turn })).toBe(true);
        expect(isChatSocketEvent({ type: "chat_turns", turns: [turn, { ...turn, status: "future" }] })).toBe(true);
        expect(isChatSocketEvent({ type: "chat_turn", turn: {} })).toBe(false);
        expect(isChatSocketEvent({ type: "chat_turns", turns: "x" })).toBe(false);
        expect(isChatSocketEvent({ type: "pong" })).toBe(true);
        expect(isChatSocketEvent(null)).toBe(false);
    });
});

describe("has_evidence", () => {
    const base = { id: "m", patient_id: "p", content: "hi", role: "assistant" as const, language: "en-US" as const, created_at: "2099-01-01T00:00:00Z" };
    it("maps true to hasEvidence and leaves false or missing unset", async () => {
        const { mapChatMessageFromApi } = await import("@/services/chat-api");
        expect(mapChatMessageFromApi({ ...base, has_evidence: true }).hasEvidence).toBe(true);
        expect(mapChatMessageFromApi({ ...base, has_evidence: false }).hasEvidence).toBeUndefined();
        expect(mapChatMessageFromApi(base).hasEvidence).toBeUndefined();
    });
});
