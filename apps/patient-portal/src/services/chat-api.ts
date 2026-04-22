import { api } from "@/services/api";
import { normalizeLocale, type ChatMessage, type ChatRole, type Locale } from "@/types";

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

export type ChatSocketEvent =
    | AssistantChunkEvent
    | AssistantCompleteEvent
    | AssistantStartEvent
    | ChatErrorEvent
    | ChatHistoryEvent
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

export async function fetchChatHistory(patientId: string, token: string): Promise<ChatMessage[]> {
    const response = await api.get<ChatMessageApi[]>(`/api/v1/chat/history/${patientId}`, {
        token,
    });

    return response.map(mapChatMessageFromApi);
}

export function buildChatWebSocketUrl(patientId: string, token: string): string {
    const backendBaseUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
    const parsed = new URL(backendBaseUrl);
    parsed.protocol = parsed.protocol === "https:" ? "wss:" : "ws:";
    parsed.pathname = `/ws/chat/${patientId}`;
    parsed.search = "";
    parsed.searchParams.set("token", token);
    return parsed.toString();
}

export function isChatSocketEvent(value: unknown): value is ChatSocketEvent {
    if (!value || typeof value !== "object") {
        return false;
    }

    const eventType = (value as { type?: unknown }).type;
    return typeof eventType === "string";
}
