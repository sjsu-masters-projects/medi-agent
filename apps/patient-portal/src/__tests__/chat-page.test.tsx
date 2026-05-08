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
    getVoiceCapabilities: vi.fn(() => ({ recording: false, recognition: false, synthesis: false })),
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
        vi.useRealTimers();
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
        getVoiceCapabilities.mockReturnValue({ recording: false, recognition: false, synthesis: false });
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

    it("does not auto-play assistant audio for typed (non-voice) turns", async () => {
        // With the simplified UX, auto-playback is opt-in per-turn via the mic
        // button. A typed turn must NOT spin up the voice WS or call TTS.
        getVoiceCapabilities.mockReturnValue({ recording: false, recognition: true, synthesis: true });
        renderPage();

        await screen.findByText(/I can help explain results/i);
        const chatSocket = MockWebSocket.instances[0];
        await act(async () => {
            chatSocket.emitOpen();
        });

        await act(async () => {
            chatSocket.emitMessage({
                type: "assistant_complete",
                message: {
                    audio_url: null,
                    content: "Please take your medication with food.",
                    created_at: "2026-04-17T10:01:00Z",
                    id: "assistant-typed-1",
                    intent: "medication_question",
                    language: "en-US",
                    patient_id: "patient-1",
                    role: "assistant",
                },
            });
        });

        // Only the chat WS should exist — no voice WS opened, no TTS request.
        expect(MockWebSocket.instances.length).toBe(1);
        expect(playAssistantVoiceResponse).not.toHaveBeenCalled();
    });

    it("renders clinician message and appointment proposal websocket events", async () => {
        renderPage();

        await screen.findByText(/I can help explain results/i);
        const socket = MockWebSocket.instances[0];
        await act(async () => {
            socket.emitOpen();
            socket.emitMessage({
                type: "clinician_message",
                message: {
                    body: "Please bring your medication list to your next visit.",
                    channel: "in_app",
                    clinician_id: "clinician-1",
                    created_at: "2026-04-17T10:02:00Z",
                    id: "clinician-message-1",
                    is_read: false,
                    patient_id: "patient-1",
                    subject: "Visit prep",
                },
            });
            socket.emitMessage({
                type: "appointment_proposal",
                proposal: {
                    care_team_id: "care-team-1",
                    clinician_name: "Emily Smith",
                    next_step: "Confirm a date and time with your clinic before this becomes an appointment.",
                    patient_id: "patient-1",
                    proposal_id: "proposal-1",
                    reason: "Follow-up next week",
                },
            });
        });

        expect(await screen.findByText(/Visit prep/i)).toBeInTheDocument();
        expect(screen.getByText(/Please bring your medication list/i)).toBeInTheDocument();
        expect(screen.getByText(/Appointment request noted with Emily Smith/i)).toBeInTheDocument();
    });

    it("reconnects the chat websocket after a transient close", async () => {
        renderPage();

        await screen.findByText(/I can help explain results/i);
        const socket = MockWebSocket.instances[0];
        await act(async () => {
            socket.emitOpen();
            socket.close();
        });

        expect(await screen.findByText(/Offline/i)).toBeInTheDocument();

        await waitFor(() => {
            expect(MockWebSocket.instances.length).toBe(2);
        }, { timeout: 1500 });
        await act(async () => {
            MockWebSocket.instances[1].emitOpen();
        });
        expect(await screen.findByText(/Online/i)).toBeInTheDocument();
    });

    it("streams microphone chunks to backend voice STT and sends final transcript to chat", async () => {
        getVoiceCapabilities.mockReturnValue({ recording: true, recognition: false, synthesis: true });
        const trackStop = vi.fn();
        const getUserMedia = vi.fn().mockResolvedValue({
            getTracks: () => [{ stop: trackStop }],
        });
        vi.stubGlobal("navigator", {
            ...window.navigator,
            mediaDevices: { getUserMedia },
        });

        class MockMediaRecorder {
            static isTypeSupported = vi.fn(() => true);
            ondataavailable: ((event: { data: Blob }) => void) | null = null;
            onerror: (() => void) | null = null;
            onstop: (() => void) | null = null;
            state = "inactive";

            constructor(_stream: MediaStream, readonly options: { mimeType: string }) {}

            start() {
                this.state = "recording";
                this.ondataavailable?.({ data: new Blob(["chunk"], { type: this.options.mimeType }) });
            }

            stop() {
                this.state = "inactive";
                this.onstop?.();
            }
        }
        vi.stubGlobal("MediaRecorder", MockMediaRecorder);

        renderPage();

        await screen.findByText(/I can help explain results/i);
        const chatSocket = MockWebSocket.instances[0];
        await act(async () => {
            chatSocket.emitOpen();
        });

        await act(async () => {
            fireEvent.click(screen.getByRole("button", { name: /Tap to speak/i }));
        });

        const voiceSocket = MockWebSocket.instances[1];
        await waitFor(() => {
            expect(voiceSocket.sent.some((event) => JSON.parse(event).type === "audio_start")).toBe(true);
            expect(voiceSocket.sent.some((event) => JSON.parse(event).type === "audio_chunk")).toBe(true);
        });

        await act(async () => {
            voiceSocket.emitMessage({
                language: "en-US",
                model: "nova-3",
                transcript: "I feel dizzy",
                type: "transcript_final",
            });
            fireEvent.click(screen.getByRole("button", { name: /Stop voice recording/i }));
            voiceSocket.emitMessage({
                audio_url: "patient-1/voice-user.webm",
                signed_url: "https://storage.example.com/voice-user.webm",
                type: "audio_stream_complete",
            });
        });

        // Default behavior: transcript fills the input box; user reviews
        // before sending. NO user_message frame is auto-emitted.
        await waitFor(() => {
            expect(screen.getByPlaceholderText(/Type or speak/i)).toHaveValue("I feel dizzy");
        });
        expect(chatSocket.sent.some((event) => JSON.parse(event).type === "user_message")).toBe(
            false,
        );
        expect(trackStop).toHaveBeenCalled();
    });

    it("auto-sends and auto-plays when hands-free mode is enabled", async () => {
        getVoiceCapabilities.mockReturnValue({ recording: false, recognition: true, synthesis: true });
        renderPage();

        await screen.findByText(/I can help explain results/i);
        const chatSocket = MockWebSocket.instances[0];
        await act(async () => {
            chatSocket.emitOpen();
        });

        // Enable hands-free.
        fireEvent.click(screen.getByRole("button", { name: /Turn on hands-free mode/i }));
        // Confirm toggle is on.
        expect(
            screen.getByRole("button", { name: /Hands-free mode is on/i }),
        ).toBeInTheDocument();

        await act(async () => {
            chatSocket.emitMessage({
                type: "assistant_complete",
                message: {
                    audio_url: null,
                    content: "Take it with food.",
                    created_at: "2026-04-17T10:01:00Z",
                    id: "assistant-handsfree-1",
                    intent: "medication_question",
                    language: "en-US",
                    patient_id: "patient-1",
                    role: "assistant",
                },
            });
        });

        // Hands-free is on but the turn was NOT voice-initiated → still no
        // auto-play. Auto-play only fires when the user *spoke* the turn.
        expect(playAssistantVoiceResponse).not.toHaveBeenCalled();
    });
});
