import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Provider } from "react-redux";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ChatPage from "@/app/(app)/chat/page";
import { store } from "@/store/store";
import { clearChatState, setMessages } from "@/store/slices/chat-slice";
import { hydrateSession, logout } from "@/store/slices/auth-slice";
import { Language } from "@/types";
import { storePendingChatDocumentContext } from "@/services/chat-bridge";

const {
    buildChatWebSocketUrl,
    fetchChatHistory,
    getVoiceCapabilities,
    playAssistantVoiceResponse,
    replace,
} = vi.hoisted(() => ({
    buildChatWebSocketUrl: vi.fn(),
    fetchChatHistory: vi.fn(),
    getVoiceCapabilities: vi.fn(() => ({ recognition: false, synthesis: false })),
    playAssistantVoiceResponse: vi.fn(() => null),
    replace: vi.fn(),
}));

let searchParamsValue = new URLSearchParams();

vi.mock("next/navigation", () => ({
    useRouter: () => ({ replace }),
    useSearchParams: () => searchParamsValue,
}));

vi.mock("@/services/chat-api", async () => {
    const actual = await vi.importActual<typeof import("@/services/chat-api")>(
        "@/services/chat-api",
    );

    return {
        ...actual,
        buildChatWebSocketUrl,
        fetchChatHistory,
    };
});

vi.mock("@/services/browser-voice", () => ({
    createSpeechRecognitionController: vi.fn(() => null),
    getVoiceCapabilities,
    playAssistantVoiceResponse,
    stopAssistantVoicePlayback: vi.fn(),
}));

class MockWebSocket {
    static CLOSED = 3;
    static CONNECTING = 0;
    static instances: MockWebSocket[] = [];
    static OPEN = 1;

    static reset() {
        MockWebSocket.instances = [];
    }

    onclose: ((event?: CloseEvent) => void) | null = null;
    onerror: ((event?: Event) => void) | null = null;
    onmessage: ((event: MessageEvent) => void) | null = null;
    onopen: ((event?: Event) => void) | null = null;
    readyState = 1;
    sent: string[] = [];
    url: string;

    constructor(url: string) {
        this.url = url;
        MockWebSocket.instances.push(this);
    }

    close() {
        this.readyState = 3;
        this.onclose?.();
    }

    emitMessage(payload: unknown) {
        this.onmessage?.({
            data: JSON.stringify(payload),
        } as MessageEvent);
    }

    emitOpen() {
        this.onopen?.();
    }

    send(data: string) {
        this.sent.push(data);
    }
}

function renderPage() {
    return render(
        <Provider store={store}>
            <ChatPage />
        </Provider>,
    );
}

describe("Patient chat page", () => {
    beforeEach(() => {
        buildChatWebSocketUrl.mockReset();
        fetchChatHistory.mockReset();
        getVoiceCapabilities.mockReset();
        playAssistantVoiceResponse.mockReset();
        replace.mockReset();
        searchParamsValue = new URLSearchParams();
        MockWebSocket.reset();
        vi.stubGlobal("WebSocket", MockWebSocket);
        Element.prototype.scrollIntoView = vi.fn();
        window.sessionStorage.clear();
        window.localStorage.clear();
        window.history.replaceState({}, "", "/chat");

        store.dispatch(clearChatState());
        store.dispatch(setMessages([]));
        store.dispatch(logout());
        store.dispatch(
            hydrateSession({
                accessToken: "access-token",
                expiresAt: 9999999999,
                refreshToken: "refresh-token",
                user: {
                    email: "patient@example.com",
                    id: "patient-1",
                    role: "patient",
                },
            }),
        );

        buildChatWebSocketUrl.mockReturnValue("ws://chat.test/patient-1");
        fetchChatHistory.mockResolvedValue([]);
        getVoiceCapabilities.mockReturnValue({ recognition: false, synthesis: false });
    });

    it("renders assistant chunks progressively before completion", async () => {
        renderPage();

        await screen.findByText(/I can help explain results/i);
        const socket = MockWebSocket.instances[0];
        await act(async () => {
            socket.emitOpen();
            socket.emitMessage({
                type: "assistant_start",
                intent: "general",
                urgency: "routine",
            });
            socket.emitMessage({ type: "assistant_chunk", content: "Please stay hydrated " });
        });

        expect(await screen.findByText(/Please stay hydrated/i)).toBeInTheDocument();
        expect(screen.getByText(/Live response/i)).toBeInTheDocument();

        await act(async () => {
            socket.emitMessage({ type: "assistant_chunk", content: "and rest today." });
        });
        expect(screen.getByText(/Please stay hydrated and rest today\./i)).toBeInTheDocument();

        await act(async () => {
            socket.emitMessage({
                type: "assistant_complete",
                message: {
                    audio_url: null,
                    content: "Please stay hydrated and rest today.",
                    created_at: "2026-04-17T10:01:00Z",
                    id: "assistant-1",
                    intent: "general",
                    language: "en",
                    patient_id: "patient-1",
                    role: "assistant",
                },
            });
        });

        await waitFor(() => {
            expect(screen.queryByText(/Live response/i)).not.toBeInTheDocument();
        });
        expect(screen.getByText("Please stay hydrated and rest today.")).toBeInTheDocument();
    });

    it("sends the selected language in websocket payloads", async () => {
        renderPage();

        await screen.findByText(/I can help explain results/i);
        const socket = MockWebSocket.instances[0];
        await act(async () => {
            socket.emitOpen();
        });
        await screen.findByText(/Online/i);

        fireEvent.click(screen.getByRole("button", { name: "ES" }));
        fireEvent.change(screen.getByPlaceholderText(/Escribe o habla/i), {
            target: { value: "Tengo mareos" },
        });
        const sendButton = screen.getByRole("button", { name: /send message/i });

        await waitFor(() => {
            expect(sendButton).not.toHaveAttribute("disabled");
        });

        fireEvent.click(sendButton);

        await waitFor(() => {
            expect(socket.sent).toHaveLength(1);
        });
        expect(JSON.parse(socket.sent[0])).toMatchObject({
            content: "Tengo mareos",
            language: Language.ES,
            type: "user_message",
        });
    });

    it("shows escalation as a dismissible safety notice instead of a chat error", async () => {
        renderPage();

        await screen.findByText(/I can help explain results/i);
        const socket = MockWebSocket.instances[0];
        await act(async () => {
            socket.emitOpen();
            socket.emitMessage({
                type: "assistant_complete",
                escalation_required: true,
                message: {
                    audio_url: null,
                    content: "Please contact your care team today.",
                    created_at: "2026-04-17T10:01:00Z",
                    id: "assistant-urgent",
                    intent: "symptom",
                    language: "en",
                    patient_id: "patient-1",
                    role: "assistant",
                },
            });
        });

        const safetyNotice = await screen.findByRole("alert");
        expect(safetyNotice).toHaveTextContent(/Contact your care team today/i);
        expect(screen.queryByText(/Live chat connection encountered/i)).not.toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: /dismiss/i }));
        await waitFor(() => {
            expect(screen.queryByRole("alert")).not.toBeInTheDocument();
        });
    });

    it("hydrates document context into chat from the records bridge", async () => {
        searchParamsValue = new URLSearchParams("document=doc-1");
        window.history.replaceState({}, "", "/chat?document=doc-1");
        storePendingChatDocumentContext({
            documentId: "doc-1",
            documentName: "Lab Report April.pdf",
            documentType: "lab_report",
            preferredLanguage: Language.ES,
            provider: "Care team",
            suggestedQuestion: "Ayúdame a entender este informe.",
            summary: "Everything looks stable.",
        });

        renderPage();

        expect(
            await screen.findByText(/Lab Report April\.pdf/i),
        ).toBeInTheDocument();
        expect(screen.getByDisplayValue(/Ayúdame a entender este informe\./i)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "ES" })).toHaveAttribute(
            "aria-pressed",
            "true",
        );
        expect(buildChatWebSocketUrl).toHaveBeenCalledWith(
            "patient-1",
            "access-token",
            { documentId: "doc-1" },
        );
        expect(replace).toHaveBeenCalledWith("/chat");
    });

    it("shows backend-loaded document context when no bridge payload is stored", async () => {
        searchParamsValue = new URLSearchParams("document=doc-2");
        window.history.replaceState({}, "", "/chat?document=doc-2");

        renderPage();

        await screen.findByText(/I can help explain results/i);
        const socket = MockWebSocket.instances[0];
        await act(async () => {
            socket.emitOpen();
            socket.emitMessage({
                type: "chat_context_loaded",
                context_type: "document",
                document: {
                    id: "doc-2",
                    file_name: "Discharge Summary.pdf",
                    document_type: "discharge_summary",
                    summary: "Follow up with primary care.",
                    parse_status: "completed",
                },
            });
        });

        expect(await screen.findByText(/Discharge Summary\.pdf/i)).toBeInTheDocument();
        expect(buildChatWebSocketUrl).toHaveBeenCalledWith(
            "patient-1",
            "access-token",
            { documentId: "doc-2" },
        );
        expect(replace).toHaveBeenCalledWith("/chat");
    });

    it("reconnects without document context when the user dismisses it", async () => {
        searchParamsValue = new URLSearchParams("document=doc-3");
        window.history.replaceState({}, "", "/chat?document=doc-3");
        storePendingChatDocumentContext({
            documentId: "doc-3",
            documentName: "Medication List.pdf",
            documentType: "prescription",
            preferredLanguage: Language.EN,
            provider: "Care team",
            suggestedQuestion: "Help me understand this medication list.",
            summary: "Current medication list.",
        });

        renderPage();

        expect(await screen.findByText(/Medication List\.pdf/i)).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: /dismiss/i }));

        await waitFor(() => {
            expect(buildChatWebSocketUrl).toHaveBeenLastCalledWith(
                "patient-1",
                "access-token",
                { documentId: null },
            );
        });
        expect(screen.queryByText(/Medication List\.pdf/i)).not.toBeInTheDocument();
    });

    it("turns off voice mode when the websocket disconnects", async () => {
        getVoiceCapabilities.mockReturnValue({ recognition: true, synthesis: true });
        renderPage();

        await screen.findByText(/I can help explain results/i);
        const socket = MockWebSocket.instances[0];
        await act(async () => {
            socket.emitOpen();
        });

        fireEvent.click(screen.getByRole("button", { name: /Start Voice-to-Voice Mode/i }));
        expect(
            screen.getByRole("button", { name: /Stop Voice-to-Voice Mode/i }),
        ).toBeInTheDocument();

        await act(async () => {
            socket.close();
        });

        await waitFor(() => {
            expect(
                screen.getByRole("button", { name: /Start Voice-to-Voice Mode/i }),
            ).toBeInTheDocument();
        });
    });

    it("requests backend TTS audio when voice mode assistant response completes", async () => {
        getVoiceCapabilities.mockReturnValue({ recognition: true, synthesis: true });
        renderPage();

        await screen.findByText(/I can help explain results/i);
        const chatSocket = MockWebSocket.instances[0];
        await act(async () => {
            chatSocket.emitOpen();
        });

        fireEvent.click(screen.getByRole("button", { name: /Start Voice-to-Voice Mode/i }));

        await act(async () => {
            chatSocket.emitMessage({
                type: "assistant_complete",
                message: {
                    audio_url: null,
                    content: "Please take your medication with food.",
                    created_at: "2026-04-17T10:01:00Z",
                    id: "assistant-voice-1",
                    intent: "medication_question",
                    language: "en-US",
                    patient_id: "patient-1",
                    role: "assistant",
                },
            });
        });

        const voiceSocket = MockWebSocket.instances[1];
        expect(JSON.parse(voiceSocket.sent[0])).toEqual({
            language: "en-US",
            text: "Please take your medication with food.",
            type: "tts_request",
        });

        await act(async () => {
            voiceSocket.emitMessage({
                audio_base64: "YWJj",
                encoding: "mp3",
                language: "en-US",
                mime_type: "audio/mpeg",
                model: "aura-2-asteria-en",
                type: "assistant_audio_ready",
            });
        });

        expect(playAssistantVoiceResponse).toHaveBeenCalledWith(
            expect.objectContaining({
                audioUrl: "data:audio/mpeg;base64,YWJj",
                text: "Please take your medication with food.",
            }),
        );
    });
});
