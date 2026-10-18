import { api } from "@/services/api";
import { toDocumentResult, type DocumentResult } from "@/services/documents";
import {
    normalizeLocale,
    type ChatAttachment,
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
    /** Server-built cards under the message; missing or null on older messages. */
    attachments?: unknown[] | null;
}

export interface ChatTurnApi {
    client_message_id: string;
    status: "processing" | "completed" | "failed" | "interrupted";
    retryable: boolean;
    attempt: number;
    failure_code?: string | null;
    document_id: string | null;
    user_message?: ChatMessageApi;
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

/** The conversation's document could not be read: deleted, or not the patient's. */
export interface ChatContextUnavailableEvent {
    type: "chat_context_unavailable";
    context_type: "document";
}

export interface UserMessageSavedEvent {
    type: "user_message_saved";
    message: ChatMessageApi;
}

export interface ChatErrorEvent {
    type: "error";
    code?: string;
    message?: string;
    client_message_id?: string;
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
    | { type: "chat_turn"; turn: ChatTurnApi }
    | { type: "chat_turns"; turns: ChatTurnApi[] }
    | AppointmentCreatedEvent
    | AppointmentProposalEvent
    | AssistantChunkEvent
    | AssistantCompleteEvent
    | AssistantStartEvent
    | ChatContextLoadedEvent
    | ChatContextUnavailableEvent
    | ChatErrorEvent
    | ChatHistoryEvent
    | ClinicianMessageEvent
    | EscalationRecommendedEvent
    | UserMessageSavedEvent
    | { type: "pong" };

function optionalText(value: unknown): string | null {
    return typeof value === "string" && value.trim() ? value : null;
}

/**
 * Keep a well-formed document-results card; anything else is not shown.
 *
 * Rows are validated exactly like Records validates them. A card left with no valid
 * rows, or an attachment type this portal does not know, is dropped.
 */
function toChatAttachment(item: unknown): ChatAttachment | null {
    if (typeof item !== "object" || item === null) {
        return null;
    }
    const raw = item as Record<string, unknown>;
    const documentId = optionalText(raw.document_id);
    if (raw.type !== "document_results" || !documentId || !Array.isArray(raw.results)) {
        return null;
    }
    const results = raw.results
        .map(toDocumentResult)
        .filter((result): result is DocumentResult => result !== null);
    if (!results.length) {
        return null;
    }
    const rawTitle = typeof raw.title === "object" && raw.title !== null
        ? raw.title as Record<string, unknown>
        : {};
    const title: Partial<Record<"en-US" | "es-MX", string>> = {};
    for (const locale of ["en-US", "es-MX"] as const) {
        const text = optionalText(rawTitle[locale]);
        if (text) title[locale] = text;
    }
    return {
        type: "document_results",
        documentId,
        fileName: optionalText(raw.file_name),
        title,
        results,
    };
}

export function mapChatAttachmentsFromApi(value: unknown): ChatAttachment[] {
    if (!Array.isArray(value)) {
        return [];
    }
    return value
        .map(toChatAttachment)
        .filter((attachment): attachment is ChatAttachment => attachment !== null);
}

export function mapChatMessageFromApi(message: ChatMessageApi): ChatMessage {
    const attachments = mapChatAttachmentsFromApi(message.attachments);
    return {
        audioUrl: message.audio_url ?? undefined,
        content: message.content,
        createdAt: message.created_at,
        id: message.id,
        intent: message.intent ?? undefined,
        language: normalizeLocale(message.language),
        patientId: message.patient_id,
        role: message.role,
        // Only set when there is a card, so a message without one is unchanged.
        ...(attachments.length ? { attachments } : {}),
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

/**
 * A conversation started with "New chat", or from a document in Records. The id is
 * unguessable (a random UUID), although the server also scopes every conversation to
 * the signed-in patient.
 */
export function newConversationId(): string {
    return `chat-${crypto.randomUUID()}`;
}

export interface ChatWebSocketOptions {
    durableTurns?: boolean;
    documentId?: string | null;
    /** The patient dismissed this conversation's document; the server clears it. */
    documentDismissed?: boolean;
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
    if (options.durableTurns) parsed.searchParams.set("turn_protocol", "1");

    const documentId = options.documentId?.trim();
    if (documentId) {
        parsed.searchParams.set("context", `doc:${documentId}`);
    } else if (options.documentDismissed) {
        parsed.searchParams.set("context", "none");
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
