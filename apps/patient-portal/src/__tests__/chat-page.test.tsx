import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { Provider } from "react-redux";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ChatPage from "@/app/(app)/chat/page";
import { store } from "@/store/store";
import { clearChatState, setMessages } from "@/store/slices/chat-slice";
import { hydrateSession, logout } from "@/store/slices/auth-slice";
import { ChatRole, Language, type Locale } from "@/types";
import { storePendingChatDocumentContext } from "@/services/chat-bridge";
import { getChatControlsCopy, getPatientChatCopy } from "@/content/chat-copy";

vi.mock("@/services/symptom-intakes", () => ({ fetchActiveIntake: vi.fn().mockResolvedValue(null) }));

const {
    buildChatWebSocketUrl,
    fetchChatConversations,
    fetchChatHistory,
    getVoiceCapabilities,
    playAssistantVoiceResponse,
    replace,
    setConversationOpen,
    shell,
    pending,
    followUpView,
    profileState,
} = vi.hoisted(() => ({
    buildChatWebSocketUrl: vi.fn(),
    fetchChatConversations: vi.fn(),
    fetchChatHistory: vi.fn(),
    getVoiceCapabilities: vi.fn(() => ({ recording: false, recognition: false, synthesis: false })),
    playAssistantVoiceResponse: vi.fn(() => null),
    replace: vi.fn(),
    setConversationOpen: vi.fn(),
    shell: { conversationOpen: false },
    pending: { count: 0, loaded: true },
    followUpView: vi.fn(),
    profileState: { loaded: true },
}));

vi.mock("@/contexts/patient-shell-context", () => ({
    usePatientShell: () => ({ conversationOpen: shell.conversationOpen, setConversationOpen }),
}));

vi.mock("@/services/care-conversations", () => ({
    careConversations: { recipients: vi.fn().mockResolvedValue([]), list: vi.fn().mockResolvedValue([]) },
    getConversationCopy: (locale: string) => ({
        notice: locale === "es-MX"
            ? "Estos mensajes no se supervisan continuamente. Para una emergencia, llama al 911."
            : "Messages are not continuously monitored. For an emergency, call 911.",
    }),
}));

let searchParamsValue = new URLSearchParams();
const profile: { preferredLanguage: Locale } = { preferredLanguage: Language.EN };
vi.mock("@/hooks/use-patient-profile", () => ({
    usePatientProfile: () => (profileState.loaded ? profile : null),
}));
let renderedPage: ReturnType<typeof render>;
function changePreferredLanguage(locale: Locale) {
    profile.preferredLanguage = locale;
    renderedPage.rerender(<Provider store={store}><ChatPage /></Provider>);
}

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
        fetchChatConversations,
        fetchChatHistory,
    };
});

vi.mock("@/services/browser-voice", () => ({
    createSpeechRecognitionController: vi.fn(() => null),
    getVoiceCapabilities,
    playAssistantVoiceResponse,
    stopAssistantVoicePlayback: vi.fn(),
}));

vi.mock("@/hooks/use-pending-adr-follow-ups", () => ({
    usePendingADRFollowUps: () => ({ count: pending.count, loaded: pending.loaded }),
}));
// The view has its own tests; here it only records the props the host passes.
vi.mock("@/components/features/adr-follow-up-view", () => ({
    ADRFollowUpView: (props: { onBack?: () => void }) => {
        followUpView(props);
        return <section data-testid="follow-up-view">Follow-up view</section>;
    },
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
    renderedPage = render(
        <Provider store={store}>
            <ChatPage />
        </Provider>,
    );
    if (!searchParamsValue.has("document")) {
        fireEvent.click(screen.getByRole("button", { name: /Nora ·/ }));
    }
    return renderedPage;
}

describe("Patient chat page", () => {
    beforeEach(() => {
        profile.preferredLanguage = Language.EN;
        buildChatWebSocketUrl.mockReset();
        fetchChatHistory.mockReset();
        getVoiceCapabilities.mockReset();
        playAssistantVoiceResponse.mockReset();
        replace.mockReset();
        setConversationOpen.mockReset();
        shell.conversationOpen = false;
        pending.count = 0;
        pending.loaded = true;
        profileState.loaded = true;
        followUpView.mockReset();
        vi.useRealTimers();
        searchParamsValue = new URLSearchParams();
        MockWebSocket.reset();
        vi.stubGlobal("WebSocket", MockWebSocket);
        Element.prototype.scrollIntoView = vi.fn();
        Element.prototype.scrollTo = vi.fn();
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
        fetchChatConversations.mockResolvedValue([]);
        getVoiceCapabilities.mockReturnValue({ recording: false, recognition: false, synthesis: false });
    });

    it("opens Nora from a distinct inbox card, restores inbox focus and resets the shell on exit", async () => {
        renderedPage = render(<Provider store={store}><ChatPage /></Provider>);
        expect(screen.getByRole("heading", { name: "Nora AI" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "New message" })).toBeInTheDocument();
        expect(screen.queryByRole("textbox", { name: "Message to Nora" })).not.toBeInTheDocument();
        expect(setConversationOpen).toHaveBeenLastCalledWith(false);
        fireEvent.click(screen.getByRole("button", { name: "Nora · AI care assistant" }));
        expect(await screen.findByRole("textbox", { name: "Message to Nora" })).toBeInTheDocument();
        expect(setConversationOpen).toHaveBeenLastCalledWith(true);
        expect(screen.getByRole("heading", { name: "Nora" })).toHaveFocus();
        fireEvent.change(screen.getByRole("textbox", { name: "Message to Nora" }), { target: { value: "Unsent question" } });
        fireEvent.click(screen.getByRole("button", { name: "Back to messages" }));
        expect(setConversationOpen).toHaveBeenLastCalledWith(false);
        expect(screen.getByRole("button", { name: "Nora · AI care assistant" })).toHaveFocus();
        fireEvent.click(screen.getByRole("button", { name: "Nora · AI care assistant" }));
        expect(screen.getByRole("textbox", { name: "Message to Nora" })).toHaveValue("Unsent question");
        renderedPage.unmount();
        expect(setConversationOpen).toHaveBeenLastCalledWith(false);
    });

    it.each([Language.EN, Language.ES])("uses one thread header with accessible care-team switching and preserves Nora drafts (%s)", async (locale) => {
        profile.preferredLanguage = locale;
        const spanish = locale === Language.ES;
        const team = getPatientChatCopy(locale).careTeamLabel;
        const nora = `Nora · ${getPatientChatCopy(locale).assistantDescription}`;
        renderedPage = render(<Provider store={store}><ChatPage /></Provider>);
        expect(screen.getByRole("heading", { level: 1, name: "Chat" })).toBeInTheDocument();
        expect(screen.getByRole("heading", { name: spanish ? "Tu equipo clínico" : "Your care team" })).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: nora }));
        expect(screen.queryByRole("group", { name: team })).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: nora })).not.toBeInTheDocument();
        const message = screen.getByRole("textbox", { name: spanish ? "Mensaje para Nora" : "Message to Nora" });
        fireEvent.change(message, { target: { value: "Unsent bilingual question" } });
        const switchAction = screen.getByRole("button", { name: team });
        expect(switchAction.closest("header")).not.toBeNull();
        fireEvent.click(switchAction);
        expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
        expect(await screen.findByText(spanish ? "Todavía no hay conversaciones." : "No conversations yet.")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: nora }));
        expect(screen.getByRole("textbox", { name: spanish ? "Mensaje para Nora" : "Message to Nora" })).toHaveValue("Unsent bilingual question");
        expect(screen.getByRole("button", { name: spanish ? "Activar manos libres" : "Turn on hands-free mode" })).toBeInTheDocument();
    });

    it("honors a direct Nora presentation request on the existing route", async () => {
        shell.conversationOpen = true;
        renderedPage = render(<Provider store={store}><ChatPage /></Provider>);
        expect(screen.getByRole("textbox", { name: "Message to Nora" })).toBeInTheDocument();
        expect(screen.getByRole("heading", { name: "Nora" })).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "New message" })).not.toBeInTheDocument();
        expect(window.location.pathname).toBe("/chat");
        expect(setConversationOpen).toHaveBeenLastCalledWith(true);
        await screen.findByText(getPatientChatCopy(Language.EN).welcomeMessage);
        expect(MockWebSocket.instances[0].sent).toEqual([]);
    });

    it("opens the symptom prompt for review without sending it", async () => {
        renderedPage = render(<Provider store={store}><ChatPage /></Provider>);
        fireEvent.click(screen.getByRole("button", { name: "Report a symptom" }));
        expect(screen.getByRole("textbox", { name: "Message to Nora" })).toHaveValue(getPatientChatCopy(Language.EN).quickPrompts[1]);
        await screen.findByText(getPatientChatCopy(Language.EN).welcomeMessage);
        expect(MockWebSocket.instances[0].sent).toEqual([]);
    });

    it("uses the patient preference instead of the old chat picker and preserves original message language", async () => {
        window.localStorage.setItem("patient-portal.chat.language", "en-US");
        profile.preferredLanguage = Language.ES;
        fetchChatHistory.mockResolvedValue([{
            id: "original-en", patientId: "patient-1", role: ChatRole.USER,
            content: "My original English question", createdAt: "2026-04-17T10:00:00Z", language: Language.EN,
        }]);
        renderPage();
        expect(await screen.findByText("My original English question")).toHaveAttribute("lang", "en-US");
        expect(screen.getByText(/Idioma original: English/)).toBeInTheDocument();
        expect(screen.queryByRole("group", { name: "Chat language" })).not.toBeInTheDocument();
        expect(screen.queryByText(/^Online$/)).not.toBeInTheDocument();
        const sockets = MockWebSocket.instances.length;
        changePreferredLanguage(Language.EN);
        expect(screen.getByText("My original English question")).toBeInTheDocument();
        expect(MockWebSocket.instances).toHaveLength(sockets);
        expect(screen.getByText(/Original language: English/)).toBeInTheDocument();
    });

    it("plays the displayed welcome text and locale after the patient language changes", async () => {
        renderPage();
        await screen.findByText(getPatientChatCopy(Language.EN).welcomeMessage);
        changePreferredLanguage(Language.ES);
        expect(screen.getByText(getPatientChatCopy(Language.ES).welcomeMessage)).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Escuchar" }));
        const voiceSocket = MockWebSocket.instances[1];
        await act(async () => voiceSocket.emitOpen());
        expect(voiceSocket.sent.map((event) => JSON.parse(event))).toContainEqual({
            type: "tts_request", message_id: "welcome-message",
            text: getPatientChatCopy(Language.ES).welcomeMessage, language: Language.ES,
        });
        expect(store.getState().chat.messages[0]).toMatchObject({
            content: getPatientChatCopy(Language.EN).welcomeMessage, language: Language.EN,
        });
    });

    it("keeps historical assistant playback in the original language after an interface switch", async () => {
        fetchChatHistory.mockResolvedValue([{
            id: "original-assistant", patientId: "patient-1", role: ChatRole.ASSISTANT,
            content: "Original English reply", createdAt: "2026-04-17T10:00:00Z", language: Language.EN,
        }]);
        renderPage();
        await screen.findByText("Original English reply");
        changePreferredLanguage(Language.ES);
        fireEvent.click(screen.getByRole("button", { name: "Escuchar" }));
        const voiceSocket = MockWebSocket.instances[1];
        await act(async () => voiceSocket.emitOpen());
        expect(voiceSocket.sent.map((event) => JSON.parse(event))).toContainEqual({
            type: "tts_request", message_id: "original-assistant", text: "Original English reply", language: Language.EN,
        });
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

    describe("results cards", () => {
        const resultsAttachment = {
            type: "document_results",
            document_id: "doc-7",
            file_name: "labs-2026-10-01.pdf",
            title: { "en-US": "Lab report, October 1", "es-MX": "Reporte de laboratorio, 1 de octubre" },
            results: [
                {
                    kind: "lab_result", name: "Glucose", value: "98", unit: "mg/dL", reference_range: "70-99",
                    flag: null, flag_meaning: null, range_status: "within", panel: null, observed_at: null, page: 1, reviewed: false,
                },
                {
                    kind: "lab_result", name: "Potassium", value: "6.9", unit: "mmol/L", reference_range: "3.5-5.1",
                    flag: "HH", flag_meaning: "critical", range_status: "above", panel: null, observed_at: null, page: 1, reviewed: false,
                },
            ],
        };
        const reply = (id: string, attachments?: unknown) => ({
            audio_url: null,
            content: "Your report prints potassium as critical.\n\nSource: labs-2026-10-01.pdf, page 1",
            created_at: "2026-10-13T10:01:00Z",
            id,
            intent: "general",
            language: "en-US",
            patient_id: "patient-1",
            role: "assistant",
            ...(attachments === undefined ? {} : { attachments }),
        });

        it("renders the card on a live completed reply", async () => {
            renderPage();
            await screen.findByText(getPatientChatCopy(Language.EN).welcomeMessage);
            const socket = MockWebSocket.instances[0];
            await act(async () => {
                socket.emitOpen();
                socket.emitMessage({ type: "assistant_start" });
                socket.emitMessage({ type: "assistant_chunk", content: "Your report prints potassium as critical." });
            });
            expect(screen.queryByTestId("chat-results-card")).not.toBeInTheDocument();
            await act(async () => {
                socket.emitMessage({ type: "assistant_complete", message: reply("assistant-live", [resultsAttachment]) });
            });
            const card = await screen.findByRole("region", { name: "Lab report, October 1" });
            expect(within(card).getByText("Contact your care team today.")).toBeInTheDocument();
            expect(within(within(card).getByRole("list", { name: "Outside the report's range" })).getByText("Potassium")).toBeInTheDocument();
            expect(within(card).getByRole("button", { name: "Show 1 result in range" })).toHaveAttribute("aria-expanded", "false");
            expect(within(card).getByRole("link", { name: "See in Records" })).toHaveAttribute("href", "/records?document=doc-7");
            expect(screen.getByText(/Source: labs-2026-10-01\.pdf, page 1/)).toBeInTheDocument();
        });

        it("renders the card from chat history, in the app's Spanish, without changing older messages", async () => {
            profile.preferredLanguage = Language.ES;
            renderPage();
            await screen.findByText(getPatientChatCopy(Language.ES).welcomeMessage);
            const socket = MockWebSocket.instances[0];
            await act(async () => {
                socket.emitOpen();
                socket.emitMessage({
                    type: "chat_history",
                    messages: [
                        { ...reply("older"), content: "An older reply without a card." },
                        { ...reply("with-null"), content: "A reply with a null list.", attachments: null },
                        reply("with-card", [resultsAttachment]),
                    ],
                });
            });
            expect(await screen.findByText("An older reply without a card.")).toBeInTheDocument();
            expect(screen.getByText("A reply with a null list.")).toBeInTheDocument();
            const cards = screen.getAllByTestId("chat-results-card");
            expect(cards).toHaveLength(1);
            expect(within(cards[0]).getByText("Resultados de este reporte")).toBeInTheDocument();
            expect(within(cards[0]).getByText("Comunícate hoy con tu equipo de atención.")).toBeInTheDocument();
            expect(within(cards[0]).getByRole("button", { name: "Mostrar 1 resultado dentro del rango" })).toBeInTheDocument();
            // The title follows the message's own language; this reply was written in English.
            expect(within(cards[0]).getByRole("heading", { name: "Lab report, October 1" })).toHaveAttribute("lang", "en-US");
        });

        it("ignores a malformed or unknown attachment and still shows the reply", async () => {
            renderPage();
            await screen.findByText(getPatientChatCopy(Language.EN).welcomeMessage);
            const socket = MockWebSocket.instances[0];
            await act(async () => {
                socket.emitOpen();
                socket.emitMessage({
                    type: "assistant_complete",
                    message: reply("assistant-bad", [
                        { type: "medication_card", document_id: "doc-7" },
                        { ...resultsAttachment, results: [{ kind: "lab_result", name: "Potassium" }] },
                    ]),
                });
            });
            expect(await screen.findByText(/Your report prints potassium as critical\./)).toBeInTheDocument();
            expect(screen.queryByTestId("chat-results-card")).not.toBeInTheDocument();
            expect(screen.queryByText("Results from this report")).not.toBeInTheDocument();
        });
    });

    it("retains Enter-to-send while Shift+Enter and composition do not send", async () => {
        renderPage();
        await screen.findByText(/I can help explain results/i);
        const socket = MockWebSocket.instances[0];
        await act(async () => socket.emitOpen());
        const field = screen.getByRole("textbox");
        fireEvent.change(field, { target: { value: "Explain my plan" } });
        fireEvent.keyDown(field, { key: "Enter", shiftKey: true });
        fireEvent.keyDown(field, { key: "Enter", isComposing: true });
        expect(socket.sent).toHaveLength(0);
        fireEvent.keyDown(field, { key: "Enter" });
        await waitFor(() => expect(socket.sent).toHaveLength(1));
        expect(JSON.parse(socket.sent[0])).toMatchObject({ content: "Explain my plan", type: "user_message" });
    });

    it("sends the selected language in websocket payloads", async () => {
        renderPage();

        await screen.findByText(/I can help explain results/i);
        const socket = MockWebSocket.instances[0];
        await act(async () => {
            socket.emitOpen();
        });
        await screen.findByText(/^Connected$/);

        changePreferredLanguage(Language.ES);
        fireEvent.change(screen.getByPlaceholderText(/Escribe o habla/i), {
            target: { value: "Tengo mareos" },
        });
        const sendButton = screen.getByRole("button", { name: /send message|enviar mensaje/i });

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

    it("shows typing feedback as soon as a typed message is sent", async () => {
        renderPage();

        await screen.findByText(/I can help explain results/i);
        const socket = MockWebSocket.instances[0];
        await act(async () => {
            socket.emitOpen();
        });

        fireEvent.change(screen.getByPlaceholderText(/Type or speak/i), {
            target: { value: "What documents do you have on me?" },
        });
        fireEvent.click(screen.getByRole("button", { name: /send message|enviar mensaje/i }));

        expect(screen.getByRole("heading", { name: "Nora" })).toBeInTheDocument();
        expect(screen.getByText("AI care assistant")).toBeInTheDocument();
        expect(screen.getByText("Nora is typing...")).toBeInTheDocument();
        expect(screen.queryByText(/Maya/)).not.toBeInTheDocument();
    });

    it("keeps the assistant name consistent and localizes its identity and typing in Spanish", async () => {
        renderPage();
        await screen.findByText(/I can help explain results/i);
        const socket = MockWebSocket.instances[0];
        await act(async () => { socket.emitOpen(); });

        changePreferredLanguage(Language.ES);
        expect(screen.getByRole("heading", { name: "Nora" })).toBeInTheDocument();
        expect(screen.getByText("Asistente de cuidado con IA")).toBeInTheDocument();
        fireEvent.change(screen.getByPlaceholderText(/Escribe o habla/i), {
            target: { value: "Ayúdame a entender mis resultados" },
        });
        fireEvent.click(screen.getByRole("button", { name: /send message|enviar mensaje/i }));
        expect(screen.getByText("Nora está escribiendo...")).toBeInTheDocument();
        expect(screen.queryByText("Nora is typing...")).not.toBeInTheDocument();
        expect(screen.queryByText(/Maya/)).not.toBeInTheDocument();
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

    it("clears a prior conversation safety notice when starting a new chat", async () => {
        renderPage();
        await screen.findByText(/I can help explain results/i);
        const oldSocket = MockWebSocket.instances[0];
        await act(async () => {
            oldSocket.emitOpen();
            oldSocket.emitMessage({
                type: "assistant_complete",
                escalation_required: true,
                urgency: "urgent",
                message: {
                    audio_url: null,
                    content: "Please contact your care team today.",
                    created_at: "2026-04-17T10:01:00Z",
                    id: "assistant-urgent-old-session",
                    intent: "symptom",
                    language: "en",
                    patient_id: "patient-1",
                    role: "assistant",
                },
            });
        });
        expect(await screen.findByRole("alert")).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: "New chat" }));
        await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());

        await act(async () => {
            oldSocket.emitMessage({
                type: "escalation_recommended",
                urgency: "urgent",
                message: "Old session escalation",
                delivery_state: "delivered",
                clinicians_notified: 1,
            });
        });
        expect(screen.queryByRole("alert")).not.toBeInTheDocument();
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
        expect(screen.getByPlaceholderText(/Type or speak/i)).toBeInTheDocument();
        expect(screen.queryByRole("group", { name: "Chat language" })).not.toBeInTheDocument();
        // A question about a document starts its own conversation.
        expect(buildChatWebSocketUrl).toHaveBeenCalledWith(
            "patient-1",
            { documentId: "doc-1", sessionId: expect.stringMatching(/^chat-/) },
        );
        expect(replace).toHaveBeenCalledWith("/chat");
    });

    it("opens Nora with the document when navigation arrives before window.location updates", async () => {
        // In-app navigation from Records renders the chat page while window.location still
        // shows the previous page; the handoff must come from the router's search params.
        searchParamsValue = new URLSearchParams("document=doc-1");
        window.history.replaceState({}, "", "/records");
        storePendingChatDocumentContext({
            documentId: "doc-1",
            documentName: "Physical activity instructions",
            documentType: "other",
            preferredLanguage: Language.EN,
            provider: "Care team",
            suggestedQuestion: "Help me understand this document.",
            summary: "Walk after dinner.",
        });

        renderPage();

        expect(await screen.findByText(/Physical activity instructions/i)).toBeInTheDocument();
        expect(screen.getByDisplayValue(/Help me understand this document\./i)).toBeInTheDocument();
        expect(buildChatWebSocketUrl).toHaveBeenCalledWith("patient-1", {
            documentId: "doc-1", sessionId: expect.stringMatching(/^chat-/),
        });
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
            { documentId: "doc-2", sessionId: expect.stringMatching(/^(chat|day)-/) },
        );
        expect(replace).toHaveBeenCalledWith("/chat");
    });

    it("tells the server about a dismissal so a reconnect does not bring the document back", async () => {
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
        const sessionId = buildChatWebSocketUrl.mock.lastCall?.[1].sessionId;
        fireEvent.click(screen.getByRole("button", { name: /dismiss/i }));

        await waitFor(() => {
            expect(buildChatWebSocketUrl).toHaveBeenLastCalledWith(
                "patient-1",
                { documentId: null, documentDismissed: true, sessionId },
            );
        });
        expect(screen.queryByText(/Medication List\.pdf/i)).not.toBeInTheDocument();

        // The server has cleared the saved document, so the reconnected socket sends
        // only history; a later transient reconnect still carries the dismissal.
        const reconnected = MockWebSocket.instances.at(-1)!;
        await act(async () => {
            reconnected.emitOpen();
            reconnected.emitMessage({ type: "chat_history", messages: [] });
        });
        vi.useFakeTimers();
        const socketsBefore = MockWebSocket.instances.length;
        await act(async () => {
            reconnected.close();
            vi.advanceTimersByTime(1_000);
        });
        vi.useRealTimers();
        await waitFor(() => expect(MockWebSocket.instances.length).toBeGreaterThan(socketsBefore));
        expect(buildChatWebSocketUrl).toHaveBeenLastCalledWith(
            "patient-1",
            { documentId: null, documentDismissed: true, sessionId },
        );
        expect(screen.queryByText(/Medication List\.pdf/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/Record context attached/i)).not.toBeInTheDocument();
    });

    it("removes the document and says so when the server cannot read it any more", async () => {
        searchParamsValue = new URLSearchParams("document=doc-4");
        window.history.replaceState({}, "", "/chat?document=doc-4");
        storePendingChatDocumentContext({
            documentId: "doc-4",
            documentName: "Old Lab.pdf",
            documentType: "lab_report",
            preferredLanguage: Language.EN,
            provider: "Care team",
            suggestedQuestion: "Help me understand this lab report.",
            summary: "Old results.",
        });

        renderPage();

        expect(await screen.findByText(/Old Lab\.pdf/i)).toBeInTheDocument();
        const socket = MockWebSocket.instances[0];
        await act(async () => {
            socket.emitOpen();
            socket.emitMessage({ type: "chat_context_unavailable", context_type: "document" });
        });

        expect(screen.queryByText(/Old Lab\.pdf/i)).not.toBeInTheDocument();
        expect(await screen.findByText("This document isn't available anymore. You can keep asking about the rest of your record.")).toBeInTheDocument();
        // It stops asking for the missing document on the next connection.
        await waitFor(() => expect(buildChatWebSocketUrl).toHaveBeenLastCalledWith(
            "patient-1", { documentId: null, sessionId: expect.stringMatching(/^chat-/) },
        ));
    });

    it("shows the unavailable-document note in Spanish", async () => {
        profile.preferredLanguage = Language.ES;
        renderPage();
        const socket = MockWebSocket.instances[0];
        await act(async () => {
            socket.emitOpen();
            socket.emitMessage({ type: "chat_context_unavailable", context_type: "document" });
        });

        expect(await screen.findByText("Este documento ya no está disponible. Puedes seguir preguntando sobre el resto de tu expediente.")).toBeInTheDocument();
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

    it("keeps legacy clinician events out of human threads and shows appointment events in Nora", async () => {
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

        expect(screen.getByText(/Appointment request noted with Emily Smith/i)).toBeInTheDocument();
        expect(screen.queryByText(/Visit prep/i)).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Care team messages" }));
        expect(await screen.findByText("No conversations yet.")).toBeInTheDocument();
        expect(screen.queryByText(/Visit prep/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/Please bring your medication list/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/Appointment request noted with Emily Smith/i)).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Send message" })).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Nora · AI care assistant" }));
        expect(screen.queryByText(/Visit prep/i)).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Send message" })).toBeInTheDocument();
    });

    it("separates human conversations from Nora in Spanish", async () => {
        renderPage();
        await screen.findByText(/I can help explain results/i);
        changePreferredLanguage(Language.ES);
        fireEvent.click(screen.getByRole("button", { name: "Mensajes del equipo clínico" }));
        expect(screen.getByRole("heading", { name: "Mensajes del equipo clínico" })).toBeInTheDocument();
        expect(await screen.findByText("Todavía no hay conversaciones.")).toBeInTheDocument();
        expect(screen.queryByPlaceholderText(/Escribe o habla/i)).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Nora · Asistente de cuidado con IA" }));
        expect(screen.getByPlaceholderText(/Escribe o habla/i)).toBeInTheDocument();
    });

    it("never renders internal escalation alerts from an older backend", async () => {
        renderPage();
        await screen.findByText(/I can help explain results/i);
        await act(async () => {
            MockWebSocket.instances[0].emitMessage({
                type: "clinician_message",
                message: {
                    id: "internal-1", clinician_id: "clinician-1", patient_id: "patient-1",
                    channel: "in_app", subject: "Urgent patient chat escalation",
                    body: "Chat escalation flagged (urgent/general) for patient private-id. Latest message: test",
                    created_at: "2026-10-09T04:00:00Z",
                },
            });
        });
        expect(screen.queryByText(/private-id|Chat escalation flagged/i)).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Care team messages" }));
        expect(await screen.findByText("No conversations yet.")).toBeInTheDocument();
        expect(screen.queryByText(/Urgent patient chat escalation/i)).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: /Historical care-team messages/ })).not.toBeInTheDocument();
    });

    it("keeps genuine old human messages accessible in a read-only archive, separate from Nora and addressed threads", async () => {
        fetchChatHistory.mockResolvedValue([{
            id: "legacy-human", patientId: "patient-1", role: ChatRole.CLINICIAN,
            content: "Hi Morgan, please bring your medication list.",
            createdAt: "2026-04-17T10:00:00Z", language: Language.EN,
        }]);
        renderPage();
        expect(screen.getByRole("heading", { name: "Nora" })).toBeInTheDocument();
        expect(screen.queryByText(/Hi Morgan/)).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Care team messages" }));
        fireEvent.click(await screen.findByRole("button", { name: "Historical care-team messages (1)" }));
        expect(screen.getByText("Hi Morgan, please bring your medication list.")).toBeInTheDocument();
        expect(screen.getByText(/Read-only prior messages/)).toBeInTheDocument();
        expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Send message" })).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Nora · AI care assistant" }));
        expect(screen.queryByText(/Hi Morgan/)).not.toBeInTheDocument();
        changePreferredLanguage(Language.ES);
        fireEvent.click(screen.getByRole("button", { name: "Mensajes del equipo clínico" }));
        expect(screen.getByRole("button", { name: "Mensajes históricos del equipo clínico (1)" })).toBeInTheDocument();
        expect(screen.getByText(/Mensajes anteriores de solo lectura/)).toBeInTheDocument();
    });

    it("reconnects the chat websocket after a transient close", async () => {
        renderPage();

        await screen.findByText(/I can help explain results/i);
        const socket = MockWebSocket.instances[0];
        await act(async () => {
            socket.emitOpen();
            socket.close();
        });

        expect(await screen.findByText(/^Offline$/)).toBeInTheDocument();

        await waitFor(() => {
            expect(MockWebSocket.instances.length).toBe(2);
        }, { timeout: 1500 });
        await act(async () => {
            MockWebSocket.instances[1].emitOpen();
        });
        expect(await screen.findByText(/^Connected$/)).toBeInTheDocument();
    });

    it("stops retrying sockets that repeatedly open and immediately close", async () => {
        renderPage();
        await screen.findByText(/I can help explain results/i);
        vi.useFakeTimers();
        for (const delay of [800, 1600, 3200, 6400, 8000]) {
            const socket = MockWebSocket.instances.at(-1)!;
            await act(async () => { socket.emitOpen(); socket.close(); });
            await act(async () => { await vi.advanceTimersByTimeAsync(delay); });
        }
        expect(MockWebSocket.instances).toHaveLength(6);
        await act(async () => {
            const socket = MockWebSocket.instances.at(-1)!;
            socket.emitOpen(); socket.close();
            await vi.advanceTimersByTimeAsync(30000);
        });
        expect(MockWebSocket.instances).toHaveLength(6);
        expect(store.getState().chat.connectionStatus).toBe("disconnected");
        expect(store.getState().chat.error).toBe("Live chat is offline. Refresh the page to reconnect.");
    });

    it("restores the retry budget after a connection remains healthy", async () => {
        renderPage();
        await screen.findByText(/I can help explain results/i);
        vi.useFakeTimers();
        await act(async () => { MockWebSocket.instances[0].emitOpen(); MockWebSocket.instances[0].close(); });
        await act(async () => { await vi.advanceTimersByTimeAsync(800); });
        await act(async () => { MockWebSocket.instances[1].emitOpen(); await vi.advanceTimersByTimeAsync(5000); });
        await act(async () => { MockWebSocket.instances[1].close(); await vi.advanceTimersByTimeAsync(800); });
        expect(MockWebSocket.instances).toHaveLength(3);
    });

    it("keeps history and the reader's position while reconnecting and rehydrating", async () => {
        const history = [{ id: "earlier-reply", patientId: "patient-1", role: ChatRole.ASSISTANT,
            content: "Earlier conversation stays visible", language: Language.EN, createdAt: "2026-10-12T12:00:00Z" }];
        fetchChatHistory.mockResolvedValueOnce(history);
        // Recovery is deliberately pending so a collapse cannot be hidden by
        // an immediately resolved history request.
        let recover!: (value: typeof history) => void;
        fetchChatHistory.mockImplementationOnce(() => new Promise((resolve) => { recover = resolve; }));
        renderPage();
        await screen.findByText(history[0].content);
        const region = screen.getByRole("region", { name: "Nora conversation" });
        Object.defineProperties(region, { scrollHeight: { configurable: true, value: 2000 },
            clientHeight: { configurable: true, value: 500 } });
        region.scrollTop = 300;
        fireEvent.scroll(region);
        vi.mocked(region.scrollTo).mockClear();
        const socket = MockWebSocket.instances[0];
        await act(async () => { socket.emitOpen(); socket.close(); });
        await waitFor(() => expect(MockWebSocket.instances).toHaveLength(2), { timeout: 1500 });
        expect(screen.getByText(history[0].content)).toBeInTheDocument();
        expect(store.getState().chat.loading).toBe(false);
        await act(async () => {
            recover([...history]);
            MockWebSocket.instances[1].emitOpen();
            MockWebSocket.instances[1].emitMessage({ type: "chat_history", messages: [{
                id: history[0].id, patient_id: "patient-1", role: "assistant", content: history[0].content,
                language: Language.EN, created_at: history[0].createdAt,
            }] });
        });
        expect(region.scrollTo).not.toHaveBeenCalled();
        expect(region.scrollTop).toBe(300);
    });

    it.each([Language.EN, Language.ES])("follows streaming without animations only near the bottom in %s", async (locale) => {
        profile.preferredLanguage = locale;
        renderPage();
        await screen.findByText(getPatientChatCopy(locale).welcomeMessage);
        const region = screen.getByRole("region", { name: locale === Language.ES ? "Conversación con Nora" : "Nora conversation" });
        Object.defineProperties(region, { scrollHeight: { configurable: true, value: 2000 },
            clientHeight: { configurable: true, value: 500 } });
        region.scrollTop = 1500;
        fireEvent.scroll(region);
        vi.mocked(region.scrollTo).mockClear();
        const socket = MockWebSocket.instances[0];
        await act(async () => { socket.emitMessage({ type: "assistant_chunk", content: "A streamed " }); });
        expect(region.scrollTo).toHaveBeenLastCalledWith({ top: 2000, behavior: "instant" });
        region.scrollTop = 300;
        fireEvent.scroll(region);
        vi.mocked(region.scrollTo).mockClear();
        await act(async () => { socket.emitMessage({ type: "assistant_chunk", content: "reply" }); });
        expect(screen.getByText("A streamed reply")).toBeInTheDocument();
        expect(region.scrollTo).not.toHaveBeenCalled();
        region.scrollTop = 1490;
        fireEvent.scroll(region);
        await act(async () => { socket.emitMessage({ type: "assistant_chunk", content: " continues" }); });
        expect(region.scrollTo).toHaveBeenLastCalledWith({ top: 2000, behavior: "instant" });
    });

    it("starts a newly selected conversation at the bottom and ignores the previous socket", async () => {
        renderPage();
        await screen.findByText(/I can help explain results/i);
        const region = screen.getByRole("region", { name: "Nora conversation" });
        Object.defineProperties(region, { scrollHeight: { configurable: true, value: 2000 },
            clientHeight: { configurable: true, value: 500 } });
        region.scrollTop = 300;
        fireEvent.scroll(region);
        vi.mocked(region.scrollTo).mockClear();
        const oldSocket = MockWebSocket.instances[0];
        fetchChatHistory.mockResolvedValueOnce([{ id: "new-reply", patientId: "patient-1", role: ChatRole.ASSISTANT,
            content: "New conversation history", language: Language.EN, createdAt: "2026-10-12T12:00:00Z" }]);
        fireEvent.click(screen.getByRole("button", { name: "New chat" }));
        await screen.findByText("New conversation history");
        expect(region.scrollTo).toHaveBeenLastCalledWith({ top: 2000, behavior: "instant" });
        await act(async () => { oldSocket.emitMessage({ type: "chat_history", messages: [] }); });
        expect(screen.getByText("New conversation history")).toBeInTheDocument();
    });

    it("keeps recovered history when the reconnect REST request fails", async () => {
        fetchChatHistory.mockResolvedValueOnce([{ id: "kept-reply", patientId: "patient-1", role: ChatRole.ASSISTANT,
            content: "Keep this reply during recovery", language: Language.EN, createdAt: "2026-10-12T12:00:00Z" }]);
        fetchChatHistory.mockRejectedValueOnce(new Error("History unavailable"));
        renderPage();
        await screen.findByText("Keep this reply during recovery");
        await act(async () => { MockWebSocket.instances[0].close(); });
        await waitFor(() => expect(MockWebSocket.instances).toHaveLength(2), { timeout: 1500 });
        await waitFor(() => expect(store.getState().chat.error).toMatch(/Unable to load chat history/));
        expect(screen.getByText("Keep this reply during recovery")).toBeInTheDocument();
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
    it("opens today's conversation, starts a new one, and reopens a past one with its messages", async () => {
        fetchChatConversations.mockResolvedValue([
            { sessionId: "day-2026-10-01", title: "What is metformin for?", updatedAt: "2026-10-01T15:00:00Z" },
        ]);
        renderedPage = render(<Provider store={store}><ChatPage /></Provider>);
        const past = await screen.findByRole("button", { name: /What is metformin for\?/ });
        expect(screen.getByRole("heading", { name: "Past conversations with Nora" })).toBeInTheDocument();
        await waitFor(() => expect(fetchChatHistory).toHaveBeenLastCalledWith(
            "patient-1", "access-token", expect.stringMatching(/^day-\d{4}-\d{2}-\d{2}$/),
        ));

        fireEvent.click(past);
        await waitFor(() => expect(fetchChatHistory).toHaveBeenLastCalledWith("patient-1", "access-token", "day-2026-10-01"));
        expect(buildChatWebSocketUrl).toHaveBeenLastCalledWith("patient-1", { documentId: null, sessionId: "day-2026-10-01" });

        fireEvent.click(screen.getByRole("button", { name: "New chat" }));
        await waitFor(() => expect(buildChatWebSocketUrl).toHaveBeenLastCalledWith(
            "patient-1", { documentId: null, sessionId: expect.stringMatching(/^chat-/) },
        ));
    });
    it.each([
        ["en-US", "pending"], ["en-US", "unavailable"], ["en-US", "no_recipients"],
        ["es-MX", "pending"], ["es-MX", "unavailable"], ["es-MX", "no_recipients"],
    ] as const)("preserves emergency direction and honest %s %s delivery status", async (locale, status) => {
        profile.preferredLanguage = locale;
        renderPage();
        await waitFor(() => expect(MockWebSocket.instances.length).toBeGreaterThan(0));
        const socket = MockWebSocket.instances[0];
        const direction = locale === "es-MX"
            ? "Esto podría ser una emergencia. Llama al 911 ahora."
            : "This may be an emergency. Please call 911 now.";
        const copy = getPatientChatCopy(locale);
        await act(async () => {
            socket.emitOpen();
            socket.emitMessage({
                type: "assistant_start", urgency: "emergency", intent: "symptom",
            });
            socket.emitMessage({ type: "assistant_chunk", content: direction });
            socket.emitMessage({
                type: "assistant_complete", urgency: "emergency", escalation_required: true,
                persistence_status: status === "unavailable" ? "uncertain" : "saved",
                message: {
                    id: "safety-reply", patient_id: "patient-1", content: direction,
                    role: "assistant", language: locale, created_at: "2026-10-10T12:00:00Z",
                },
            });
        });
        const notice = screen.getByRole("alert");
        expect(notice).toHaveTextContent(direction);
        if (status === "unavailable") expect(notice).toHaveTextContent(copy.safetySaveUncertain);
        await act(async () => {
            socket.emitMessage({
                type: "escalation_recommended", urgency: "emergency", message: direction,
                delivery_state: status, clinicians_notified: 0,
            });
        });
        expect(notice).toHaveTextContent(direction);
        expect(notice).toHaveTextContent(status === "pending" ? copy.safetyAlertPending
            : status === "unavailable" ? copy.safetySaveUncertain : copy.safetyAlertNoRecipients);
        expect(notice).not.toHaveTextContent(copy.escalationNotice);
        expect(screen.queryByText(/Nora is typing|Nora está escribiendo/)).not.toBeInTheDocument();
    });

    describe("ADR follow-up mode", () => {
        const requestId = "11111111-1111-4111-8111-111111111111";
        const assessmentId = "22222222-2222-4222-8222-222222222222";
        const lastViewProps = () => followUpView.mock.calls.at(-1)?.[0];
        function renderFollowUp(query: string) {
            searchParamsValue = new URLSearchParams(query);
            renderedPage = render(<Provider store={store}><ChatPage /></Provider>);
        }
        it.each([
            ["request", `view=follow-up&request=${requestId}&assessment=${assessmentId}`, requestId, null],
            ["request only", `view=follow-up&request=${requestId}`, requestId, null],
            ["assessment only", `view=follow-up&assessment=${assessmentId}`, null, assessmentId],
            ["neither", "view=follow-up", null, null],
        ])("renders the follow-up view without a thread (%s)", (_name, query, expectedRequest, expectedAssessment) => {
            pending.count = 2;
            renderFollowUp(query);
            expect(screen.getByTestId("follow-up-view")).toBeInTheDocument();
            expect(lastViewProps()).toMatchObject({ locale: "en-US", requestId: expectedRequest, assessmentId: expectedAssessment });
            expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
            expect(screen.queryByRole("button", { name: /Nora ·/ })).not.toBeInTheDocument();
            expect(screen.queryByRole("heading", { name: "Nora AI" })).not.toBeInTheDocument();
            expect(screen.queryByRole("heading", { name: "Your care team" })).not.toBeInTheDocument();
            expect(screen.queryByRole("link", { name: /Questions from your care team/ })).not.toBeInTheDocument();
        });
        it.each([Language.EN, Language.ES])("shows the care-team notice, localized back button and focused heading (%s)", (locale) => {
            profile.preferredLanguage = locale;
            renderFollowUp(`view=follow-up&request=${requestId}`);
            const caution = locale === Language.ES
                ? "Estos mensajes no se supervisan continuamente. Para una emergencia, llama al 911."
                : "Messages are not continuously monitored. For an emergency, call 911.";
            expect(screen.getByText(caution)).toBeInTheDocument();
            expect(screen.queryByText(getChatControlsCopy(locale).caution)).not.toBeInTheDocument();
            expect(screen.getByRole("heading", { level: 1 })).toHaveFocus();
            expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(locale === Language.ES ? "Preguntas de tu equipo de atención" : "Questions from your care team");
            expect(lastViewProps()).toMatchObject({ locale });
            fireEvent.click(screen.getByRole("button", { name: locale === Language.ES ? "Volver a mensajes" : "Back to messages" }));
            expect(replace).toHaveBeenCalledWith("/chat?view=care-team");
        });
        it("keeps the bottom navigation hidden by marking the conversation open", () => {
            renderFollowUp(`view=follow-up&request=${requestId}`);
            expect(setConversationOpen).toHaveBeenLastCalledWith(true);
            renderedPage.unmount();
            expect(setConversationOpen).toHaveBeenLastCalledWith(false);
        });
        it("passes an undefined locale to the view until the profile has loaded", () => {
            profileState.loaded = false;
            renderFollowUp(`view=follow-up&assessment=${assessmentId}`);
            expect(lastViewProps()).toMatchObject({ locale: undefined, timeZone: undefined });
        });
        it("leaves follow-up mode through the view's own back action", () => {
            renderFollowUp("view=follow-up");
            lastViewProps().onBack();
            expect(replace).toHaveBeenCalledWith("/chat?view=care-team");
        });
        it("ignores request and assessment outside follow-up mode", () => {
            renderFollowUp(`request=${requestId}&assessment=${assessmentId}`);
            expect(screen.queryByTestId("follow-up-view")).not.toBeInTheDocument();
            expect(followUpView).not.toHaveBeenCalled();
        });
    });
    describe("ADR follow-up entry rows", () => {
        const rowName = (locale: Locale) => locale === Language.ES ? /Preguntas de tu equipo de atención/ : /Questions from your care team/;
        it("is absent from the inbox when nothing is pending", () => {
            renderedPage = render(<Provider store={store}><ChatPage /></Provider>);
            expect(screen.getByRole("heading", { name: "Nora AI" })).toBeInTheDocument();
            expect(screen.queryByRole("link", { name: rowName(Language.EN) })).not.toBeInTheDocument();
        });
        it("is absent while the pending count has not loaded", () => {
            pending.count = 2;
            pending.loaded = false;
            renderedPage = render(<Provider store={store}><ChatPage /></Provider>);
            expect(screen.queryByRole("link", { name: rowName(Language.EN) })).not.toBeInTheDocument();
        });
        it.each([
            [Language.EN, 1, "1 request is waiting for your answers"],
            [Language.EN, 2, "2 requests are waiting for your answers"],
            [Language.ES, 1, "1 solicitud espera tus respuestas"],
            [Language.ES, 2, "2 solicitudes esperan tus respuestas"],
        ])("shows the inbox row inside Care team messages for %s with %i pending", (locale, count, text) => {
            profile.preferredLanguage = locale;
            pending.count = count;
            renderedPage = render(<Provider store={store}><ChatPage /></Provider>);
            const careTeam = screen.getByRole("region", {
                name: getPatientChatCopy(locale).careTeamLabel,
            });
            const row = within(careTeam).getByRole("link", { name: rowName(locale) });
            expect(row).toHaveAttribute("href", "/chat?view=follow-up");
            expect(row).toHaveTextContent(text);
            expect(row).toHaveAttribute("lang", locale);
        });
        it("keeps the clinician request out of Nora and exposes it only in Care team messages", () => {
            pending.count = 1;
            renderedPage = render(<Provider store={store}><ChatPage /></Provider>);
            fireEvent.click(screen.getByRole("button", { name: /Nora ·/ }));
            expect(screen.getByRole("textbox", { name: "Message to Nora" })).toBeInTheDocument();
            expect(screen.queryByRole("link", { name: rowName(Language.EN) })).not.toBeInTheDocument();

            fireEvent.click(screen.getByRole("button", { name: "Care team messages" }));
            const careTeam = screen.getByRole("region", { name: "Care team messages" });
            expect(within(careTeam).getByRole("link", { name: rowName(Language.EN) }))
                .toHaveAttribute("href", "/chat?view=follow-up");
        });
    });
});
