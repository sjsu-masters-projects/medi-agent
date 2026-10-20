import type {
  CareConversation,
  CareConversationMessage,
  ConfirmedTranslation,
  ConversationMessagePage,
  ConversationPreviewResult,
  ConversationRecipient,
  MessageTranslationResult,
} from "../types/care-conversations";

interface ConversationTransport {
  get<T>(path: string, options: { token: string; signal?: AbortSignal }): Promise<T>;
  post<T>(path: string, body: unknown, options: { token: string; signal?: AbortSignal }): Promise<T>;
}

const root = "/api/v1/care-conversations";

export function createConversationService(api: ConversationTransport) {
  return {
    // `clinicId` is a clinician-only filter on the clinic of the care-team link.
    recipients: (token: string, signal?: AbortSignal, clinicId?: string | null) =>
      api.get<ConversationRecipient[]>(
        `${root}/recipients${clinicId ? `?clinic_id=${encodeURIComponent(clinicId)}` : ""}`,
        { token, signal },
      ),
    list: (token: string, signal?: AbortSignal, clinicId?: string | null) =>
      api.get<CareConversation[]>(
        `${root}/${clinicId ? `?clinic_id=${encodeURIComponent(clinicId)}` : ""}`,
        { token, signal },
      ),
    open: (token: string, recipientId: string) =>
      api.post<CareConversation>(`${root}/`, { recipient_id: recipientId }, { token }),
    messages: (token: string, id: string, before?: string, signal?: AbortSignal) =>
      api.get<ConversationMessagePage>(
        `${root}/${encodeURIComponent(id)}/messages?limit=50${before ? `&before=${encodeURIComponent(before)}` : ""}`,
        { token, signal },
      ),
    // `confirmedTranslation` is the previewed wording a clinician approved (LOC-003); the
    // server re-checks it against the message body and stores it as the message's translation.
    send: (
      token: string,
      id: string,
      body: string,
      clientMessageId: string,
      carePlanItemId?: string,
      confirmedTranslation?: ConfirmedTranslation | null,
    ) =>
      api.post<CareConversationMessage>(
        `${root}/${encodeURIComponent(id)}/messages`,
        {
          body: body.trim(),
          client_message_id: clientMessageId,
          ...(carePlanItemId ? { care_plan_item_id: carePlanItemId } : {}),
          ...(confirmedTranslation ? { confirmed_translation: confirmedTranslation } : {}),
        },
        { token },
      ),
    reviewActivity: (token: string, id: string, messageId: string) =>
      api.post<{ patient_id: string; plan_id: string; item_id: string }>(
        `${root}/${encodeURIComponent(id)}/messages/${encodeURIComponent(messageId)}/activity-review`,
        {}, { token },
      ),
    // LOC-003: what the patient will receive for an unsent reply, with its English
    // back-translation. Clinician-only, and nothing is stored.
    preview: (token: string, id: string, body: string, signal?: AbortSignal) =>
      api.post<ConversationPreviewResult>(
        `${root}/${encodeURIComponent(id)}/messages/preview`,
        { body },
        { token, signal },
      ),
    // Translates ONE message into the viewer's language (stored once on the server).
    translate: (token: string, id: string, messageId: string, signal?: AbortSignal) =>
      api.post<MessageTranslationResult>(
        `${root}/${encodeURIComponent(id)}/messages/${encodeURIComponent(messageId)}/translation`,
        {},
        { token, signal },
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

export function conversationSendFailure(error: unknown): "uncertain" | "mismatch" | "invalid" | "activityUnavailable" {
  if (typeof error !== "object" || error === null || !("status" in error) || error.status !== 422)
    return "uncertain";
  const details = "details" in error ? error.details : null;
  const envelope = typeof details === "object" && details !== null && "error" in details ? details.error : null;
  const code = typeof envelope === "object" && envelope !== null && "code" in envelope ? envelope.code : null;
  if (code === "ACTIVITY_CONTEXT_UNAVAILABLE") return "activityUnavailable";
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

export const MAX_PARALLEL_TRANSLATIONS = 3;

/** The least a message must be for its pending translation to be requested. */
export interface TranslatablePending {
  id: string;
  translation_pending?: boolean;
}

/**
 * Ask for the translation of every pending message that has not been requested yet, at most
 * `limit` at a time. Each result (or failure: the original simply stays) is reported through
 * `apply` as it arrives; nothing here blocks reading, typing or sending.
 *
 * Generic over the result type so the same queue serves care-team messages and the Nora
 * transcript in the clinician's Chat tab (LOC-003), which translate through different
 * endpoints but follow the same rule: a read never calls the model.
 */
export async function requestPendingTranslations<
  Result,
  Message extends TranslatablePending = CareConversationMessage,
>(
  messages: Message[],
  requested: Set<string>,
  translate: (messageId: string) => Promise<Result>,
  apply: (messageId: string, result: Result | null) => void,
  isActive: () => boolean,
  limit: number = MAX_PARALLEL_TRANSLATIONS,
): Promise<void> {
  const queue = messages.filter((message) => message.translation_pending && !requested.has(message.id));
  for (const message of queue) requested.add(message.id);
  const worker = async () => {
    for (let message = queue.shift(); message; message = queue.shift()) {
      let result: Result | null = null;
      try {
        result = await translate(message.id);
      } catch {
        result = null; // the original stays; a later read asks again once the server allows
      }
      if (!isActive()) return;
      apply(message.id, result);
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, queue.length) }, worker));
}

/** Fold a translation result into a message; a missing result just clears the pending marker. */
export function applyTranslationResult(
  message: CareConversationMessage,
  result: MessageTranslationResult | null,
): CareConversationMessage {
  if (!result?.translation) return { ...message, translation_pending: false };
  return {
    ...message,
    translation: result.translation,
    translation_locale: result.translation_locale,
    translation_guard_passed: result.translation_guard_passed,
    translation_model_id: result.translation_model_id,
    translation_pending: false,
  };
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
    activityUnavailable: "La actividad adjunta ya no está disponible. Conservamos tu texto. Quita la actividad o vuelve a cargar las actividades antes de enviar.",
    prepareNew: "Preparar un nuevo envío", confirmNew: "Confirmar: preparar un nuevo envío", cancel: "Cancelar",
    confirmWarning: "El mensaje anterior puede ya existir. Preparar un nuevo envío permite crear otro mensaje y podría duplicarlo. Esta acción no lo envía.",
    translatedFromEnglish: "Traducido del inglés", translatedFromSpanish: "Traducido del español",
    showOriginal: "Ver original", showTranslation: "Ver traducción", translationUncertain: "las cifras pueden diferir",
    translationUnavailable: "Traducción automática no disponible para este mensaje",
    activityAsk: "Preguntar sobre una actividad del plan",
    activityAttachedButton: (title: string) => `Actividad adjunta: ${title}`,
    activityLabel: "Actividad sobre la que preguntas (opcional)",
    activityLoading: "Cargando actividades…",
    activityNone: "Sin actividad adjunta",
    activityPreviouslyAttached: "Actividad adjunta anteriormente",
    activityLoadError: "No se pudieron cargar las actividades.",
    activityRetry: "Reintentar actividades",
    activityExplanation: "Tu mensaje no cambia el plan ni los recordatorios. Tu equipo debe revisar y aprobar cualquier cambio.",
    activityLocked: "La actividad no se puede cambiar mientras se confirma o reintenta este mensaje.",
    activityAttached: "Actividad del plan adjunta",
    activityNotCurrent: "Esta actividad ya no pertenece al plan actual.",
    // Draft for LOC-001 review, not approved wording.
    translating: "Traduciendo…",
    // LOC-003 item 5, patient side. Drafts for LOC-001 review, NOT approved wording.
    aboutTranslation: "Acerca de esta traducción",
    aboutTranslationTitle: "Esta traducción es automática",
    translationMayErr: "La hizo una computadora, no una persona, y puede tener errores.",
    translationModel: (model: string) => `La hizo el modelo ${model}.`,
    translationModelUnknown: "No se registró qué modelo la hizo.",
    translationOriginalIsRecord: "El mensaje original es el que cuenta. Tu equipo de atención lee el original, no la traducción.",
    translationGuards: "Revisamos que los números, las dosis y los nombres de los medicamentos sean iguales en los dos idiomas. Si algo no coincide, no mostramos la traducción.",
    translationAsk: "Si algo no te queda claro, pregúntale a tu equipo de atención.",
    close: "Cerrar",
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
    activityUnavailable: "The attached activity is no longer available. Your text is preserved. Remove it or reload activities before sending.",
    prepareNew: "Prepare a new send", confirmNew: "Confirm: prepare a new send", cancel: "Cancel",
    confirmWarning: "The previous message may already exist. Preparing a new send permits another message and could duplicate it. This action does not send it.",
    translatedFromEnglish: "Translated from English", translatedFromSpanish: "Translated from Spanish",
    showOriginal: "Show original", showTranslation: "Show translation", translationUncertain: "numbers may differ",
    translationUnavailable: "Automatic translation unavailable for this message",
    activityAsk: "Ask about a plan activity",
    activityAttachedButton: (title: string) => `Attached activity: ${title}`,
    activityLabel: "Activity you are asking about (optional)",
    activityLoading: "Loading activities…",
    activityNone: "No activity attached",
    activityPreviouslyAttached: "Previously attached activity",
    activityLoadError: "Activities could not be loaded.",
    activityRetry: "Retry loading activities",
    activityExplanation: "Your message does not change the plan or reminders. Your care team must review and approve any change.",
    activityLocked: "The activity cannot be changed while this message is being confirmed or retried.",
    activityAttached: "Attached plan activity",
    activityNotCurrent: "This activity is no longer part of the current plan.",
    translating: "Translating…",
    // LOC-003 item 5, patient side.
    aboutTranslation: "About this translation",
    aboutTranslationTitle: "This translation is automatic",
    translationMayErr: "A computer made it, not a person, and it may contain errors.",
    translationModel: (model: string) => `It was made by the ${model} model.`,
    translationModelUnknown: "Which model made it was not recorded.",
    translationOriginalIsRecord: "The original message is the one that counts. Your care team reads the original, not the translation.",
    translationGuards: "We check that numbers, doses and medication names are the same in both languages. If something does not match, we do not show the translation.",
    translationAsk: "If anything is unclear, ask your care team.",
    close: "Close",
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
