import type {
  CareConversation,
  CareConversationMessage,
  ConversationMessagePage,
  ConversationRecipient,
} from "../types/care-conversations";

interface ConversationTransport {
  get<T>(path: string, options: { token: string; signal?: AbortSignal }): Promise<T>;
  post<T>(path: string, body: unknown, options: { token: string; signal?: AbortSignal }): Promise<T>;
}

const root = "/api/v1/care-conversations";

export function createConversationService(api: ConversationTransport) {
  return {
    recipients: (token: string, signal?: AbortSignal) =>
      api.get<ConversationRecipient[]>(`${root}/recipients`, { token, signal }),
    list: (token: string, signal?: AbortSignal) =>
      api.get<CareConversation[]>(`${root}/`, { token, signal }),
    open: (token: string, recipientId: string) =>
      api.post<CareConversation>(`${root}/`, { recipient_id: recipientId }, { token }),
    messages: (token: string, id: string, before?: string, signal?: AbortSignal) =>
      api.get<ConversationMessagePage>(
        `${root}/${encodeURIComponent(id)}/messages?limit=50${before ? `&before=${encodeURIComponent(before)}` : ""}`,
        { token, signal },
      ),
    send: (token: string, id: string, body: string, clientMessageId: string) =>
      api.post<CareConversationMessage>(
        `${root}/${encodeURIComponent(id)}/messages`,
        { body: body.trim(), client_message_id: clientMessageId },
        { token },
      ),
    read: (token: string, id: string, lastMessageId: string) =>
      api.post<{ read_at: string }>(
        `${root}/${encodeURIComponent(id)}/read`,
        { last_message_id: lastMessageId },
        { token },
      ),
  };
}

export type ConversationService = ReturnType<typeof createConversationService>;

export function conversationAccessDenied(error: unknown): boolean {
  const status = typeof error === "object" && error !== null && "status" in error
    ? error.status : null;
  return status === 401 || status === 403 || status === 404;
}

export function conversationSendFailure(error: unknown): "uncertain" | "mismatch" | "invalid" {
  if (typeof error !== "object" || error === null || !("status" in error) || error.status !== 422)
    return "uncertain";
  const details = "details" in error ? error.details : null;
  const envelope = typeof details === "object" && details !== null && "error" in details ? details.error : null;
  const code = typeof envelope === "object" && envelope !== null && "code" in envelope ? envelope.code : null;
  return code === "MESSAGE_IDEMPOTENCY_MISMATCH" ? "mismatch" : "invalid";
}

export function mergeConversationMessages(
  current: CareConversationMessage[], incoming: CareConversationMessage[],
): CareConversationMessage[] {
  return [...new Map([...current, ...incoming].map((message) => [message.id, message])).values()]
    .sort((a, b) => {
      const timestampOrder = Date.parse(a.created_at) - Date.parse(b.created_at);
      const fraction = (timestamp: string) => (timestamp.match(/\.(\d+)/)?.[1] ?? "").padEnd(9, "0");
      return timestampOrder || fraction(a.created_at).localeCompare(fraction(b.created_at)) || a.id.localeCompare(b.id);
    });
}

export function getConversationCopy(locale: string) {
  return locale === "es-MX" ? {
    recipient: "Elegir destinatario", choose: "Selecciona una persona", open: "Abrir conversación",
    threads: "Conversaciones", empty: "Todavía no hay conversaciones.", noRecipients: "No hay destinatarios vinculados disponibles.",
    select: "Elige una conversación o un destinatario para comenzar.", loading: "Cargando…", refresh: "Actualizar",
    retry: "Reintentar", older: "Cargar mensajes anteriores", message: "Mensaje", send: "Enviar mensaje", sending: "Enviando…",
    uncertain: "No se pudo confirmar el envío. Tu mensaje se conserva; reintenta el mismo envío para evitar duplicados.",
    loadError: "No se pudo cargar la conversación. Intenta de nuevo.", denied: "Esta conversación no está disponible. Actualiza las conversaciones.",
    readError: "No se pudo actualizar el contador de mensajes no leídos. Intenta actualizar.",
    savedRefreshError: "Mensaje guardado. No se pudo actualizar la conversación; actualiza para ver los mensajes recientes.",
    noMessages: "Todavía no hay mensajes.", unread: "sin leer", notice: "Estos mensajes no se supervisan continuamente. Para una emergencia, llama al 911.",
    locked: "Reintenta el envío pendiente antes de editar este mensaje.",
    mismatch: "El reintento fue rechazado porque no coincide con el envío original. El mensaje anterior puede ya existir. Actualiza y revisa el historial antes de preparar otro envío.",
    invalid: "El mensaje fue rechazado. Tu texto se conserva; revísalo o edítalo antes de volver a enviarlo.",
    prepareNew: "Preparar un nuevo envío", confirmNew: "Confirmar: preparar un nuevo envío", cancel: "Cancelar",
    confirmWarning: "El mensaje anterior puede ya existir. Preparar un nuevo envío permite crear otro mensaje y podría duplicarlo. Esta acción no lo envía.",
  } : {
    recipient: "Choose recipient", choose: "Select a person", open: "Open conversation",
    threads: "Conversations", empty: "No conversations yet.", noRecipients: "No linked recipients available.",
    select: "Choose a conversation or a recipient to begin.", loading: "Loading…", refresh: "Refresh",
    retry: "Retry", older: "Load older messages", message: "Message", send: "Send message", sending: "Sending…",
    uncertain: "Send could not be confirmed. Your message is preserved; retry the same send to avoid duplicates.",
    loadError: "Could not load the conversation. Please try again.", denied: "This conversation is unavailable. Refresh conversations.",
    readError: "Could not update the unread count. Try refreshing.",
    savedRefreshError: "Message saved. Could not refresh the conversation; refresh to see recent messages.",
    noMessages: "No messages yet.", unread: "unread", notice: "Messages are not continuously monitored. For an emergency, call 911.",
    locked: "Retry the pending send before editing this message.",
    mismatch: "The retry was rejected because it does not match the original send. The previous message may already exist. Refresh and review the history before preparing a new send.",
    invalid: "The message was rejected. Your text is preserved; review or edit it before sending again.",
    prepareNew: "Prepare a new send", confirmNew: "Confirm: prepare a new send", cancel: "Cancel",
    confirmWarning: "The previous message may already exist. Preparing a new send permits another message and could duplicate it. This action does not send it.",
  };
}

export function conversationRoleLabel(role: string, locale: string): string {
  const spanish = locale === "es-MX";
  const labels: Record<string, [string, string]> = {
    patient: ["Patient", "Paciente"], clinician: ["Clinician", "Profesional clínico"],
    physician: ["Physician", "Médico"], doctor: ["Physician", "Médico"],
    nurse: ["Nurse", "Enfermería"], pharmacist: ["Pharmacist", "Farmacéutico"],
    nurse_practitioner: ["Nurse practitioner", "Profesional de enfermería de práctica avanzada"],
    physician_assistant: ["Physician assistant", "Asistente médico"],
    registered_nurse: ["Registered nurse", "Personal de enfermería titulado"],
  };
  return labels[role]?.[spanish ? 1 : 0] ?? (spanish ? "Equipo clínico" : "Care team");
}
