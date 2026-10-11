import { api } from "@/services/api";
import {
    normalizeLocale,
    type ChatMessage,
    type ChatRole,
    type DocumentType,
    type Locale,
} from "@/types";

export interface ChatMessageApi {
    id: string;
    patient_id: string;
    content: string;
    role: ChatRole;
    intent?: string | null;
    language: Locale;
    audio_url?: string | null;
    created_at: string;
}

export interface AssistantCompleteEvent {
    type: "assistant_complete";
    message: ChatMessageApi;
    intent?: string;
    urgency?: string;
    escalation_required?: boolean;
}

export interface AssistantStartEvent {
    type: "assistant_start";
    intent?: string;
    urgency?: string;
}

export interface AssistantChunkEvent {
    type: "assistant_chunk";
    content: string;
}

export interface ChatHistoryEvent {
    type: "chat_history";
    messages: ChatMessageApi[];
}

export interface ChatDocumentContextApi {
    id?: string | null;
    file_name?: string | null;
    document_type?: DocumentType | string | null;
    summary?: string | null;
    parse_status?: string | null;
}

export interface ChatContextLoadedEvent {
    type: "chat_context_loaded";
    context_type: "document";
    document: ChatDocumentContextApi;
}

export interface UserMessageSavedEvent {
    type: "user_message_saved";
    message: ChatMessageApi;
}

export interface ChatErrorEvent {
    type: "error";
    code?: string;
    message?: string;
}

export interface EscalationRecommendedEvent {
    type: "escalation_recommended";
    message: string;
}

export interface ClinicianMessageApi {
    id: string;
    clinician_id: string;
    patient_id: string;
    channel: "in_app" | "email";
    subject?: string | null;
    body: string;
    is_read?: boolean;
    created_at: string;
}

export interface ClinicianMessageEvent {
    type: "clinician_message";
    message: ClinicianMessageApi;
}

export interface AppointmentProposalApi {
    proposal_id: string;
    patient_id: string;
    care_team_id?: string | null;
    clinician_name?: string | null;
    reason?: string | null;
    next_step: string;
}

export interface AppointmentProposalEvent {
    type: "appointment_proposal";
    proposal: AppointmentProposalApi;
}

export interface AppointmentCreatedEvent {
    type: "appointment_created";
    appointment: {
        id: string;
        scheduled_at: string;
        clinician_name?: string | null;
        location?: string | null;
        reason?: string | null;
    };
}

export type ChatSocketEvent =
    | AppointmentCreatedEvent
    | AppointmentProposalEvent
    | AssistantChunkEvent
    | AssistantCompleteEvent
    | AssistantStartEvent
    | ChatContextLoadedEvent
    | ChatErrorEvent
    | ChatHistoryEvent
    | ClinicianMessageEvent
    | EscalationRecommendedEvent
    | UserMessageSavedEvent
    | { type: "pong" };

export function mapChatMessageFromApi(message: ChatMessageApi): ChatMessage {
    return {
        audioUrl: message.audio_url ?? undefined,
        content: message.content,
        createdAt: message.created_at,
        id: message.id,
        intent: message.intent ?? undefined,
        language: normalizeLocale(message.language),
        patientId: message.patient_id,
        role: message.role,
    };
}

export function isInternalChatAlert(message: ClinicianMessageApi): boolean {
    return message.subject === "Urgent patient chat escalation"
        && message.body.startsWith("Chat escalation flagged (");
}

export function mapClinicianMessageFromApi(message: ClinicianMessageApi): ChatMessage {
    const subject = typeof message.subject === "string" && message.subject.trim()
        ? `${message.subject.trim()}\n\n`
        : "";
    return {
        content: `${subject}${message.body}`,
        createdAt: message.created_at,
        id: `clinician-message-${message.id}`,
        language: normalizeLocale(undefined),
        patientId: message.patient_id,
        role: "clinician" as ChatRole,
    };
}

export async function fetchChatHistory(
    patientId: string,
    token: string,
    sessionId?: string,
): Promise<ChatMessage[]> {
    const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
    const response = await api.get<ChatMessageApi[]>(`/api/v1/chat/history/${patientId}${query}`, {
        token,
    });

    return response.map(mapChatMessageFromApi);
}

export interface ChatConversationApi {
    session_id: string;
    title: string;
    turn_count: number;
    created_at: string;
    updated_at: string;
}

export interface ChatConversationSummary {
    sessionId: string;
    title: string;
    updatedAt: string;
}

/** The patient's conversations with Nora, most recent first. */
export async function fetchChatConversations(
    patientId: string,
    token: string,
): Promise<ChatConversationSummary[]> {
    const response = await api.get<ChatConversationApi[]>(
        `/api/v1/chat/conversations/${patientId}`,
        { token },
    );
    return response.map((row) => ({
        sessionId: row.session_id,
        title: row.title,
        updatedAt: row.updated_at,
    }));
}

/** Each day starts a new conversation with Nora, named after the local date. */
export function todayConversationId(now: Date = new Date()): string {
    const pad = (value: number) => String(value).padStart(2, "0");
    return `day-${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

/** A conversation started with "New chat", or from a document in Records. */
export function newConversationId(): string {
    const random = Math.random().toString(36).slice(2, 8);
    return `chat-${Date.now().toString(36)}${random}`;
}

export interface ChatWebSocketOptions {
    documentId?: string | null;
    sessionId?: string | null;
}

/**
 * Build the chat socket URL. The access token is deliberately not a parameter here:
 * it travels as a subprotocol (see `socketAuthProtocols`), because a URL is logged by the
 * server and a session token in the access log is a credential anyone with log access can
 * reuse.
 */
export function buildChatWebSocketUrl(
    patientId: string,
    options: ChatWebSocketOptions = {},
): string {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
    const parsed = new URL(backendBaseUrl);
    parsed.protocol = parsed.protocol === "https:" ? "wss:" : "ws:";
    parsed.pathname = `/ws/chat/${patientId}`;
    parsed.search = "";

    const documentId = options.documentId?.trim();
    if (documentId) {
        parsed.searchParams.set("context", `doc:${documentId}`);
    }

    const sessionId = options.sessionId?.trim();
    if (sessionId) {
        parsed.searchParams.set("session_id", sessionId);
    }

    return parsed.toString();
}

export function isChatSocketEvent(value: unknown): value is ChatSocketEvent {
    if (!value || typeof value !== "object") {
        return false;
    }

    const eventType = (value as { type?: unknown }).type;
    return typeof eventType === "string";
}
