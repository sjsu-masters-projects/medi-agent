import {
  resolveLocaleResource,
  type Locale,
  type LocaleResourceMap,
} from "@/types";

export const CARE_ASSISTANT_NAME = "Nora";

interface PatientChatCopy {
  careTeamLabel: string;
  careTeamIntro: string;
  careTeamEmpty: string;
  historicalCareTeamLabel: string;
  historicalCareTeamIntro: string;
  assistantDescription: string;
  typingMessage: string;
  documentContextIntro: string;
  documentContextSuffix: string;
  emptyStateIntro: string;
  escalationNotice: string;
  inputPlaceholder: string;
  quickPrompts: string[];
  welcomeMessage: string;
}

const PATIENT_CHAT_COPY: LocaleResourceMap<PatientChatCopy> = {
  default: {
    careTeamLabel: "Care team messages",
    careTeamIntro: "Choose a linked clinician to exchange messages, separate from your AI conversation.",
    careTeamEmpty: "No care-team messages yet.",
    historicalCareTeamLabel: "Historical care-team messages",
    historicalCareTeamIntro: "Read-only prior messages. Sender and recipient routing is not available for these records. They are separate from addressed conversations and cannot be replied to here.",
    assistantDescription: "AI care assistant",
    typingMessage: `${CARE_ASSISTANT_NAME} is typing...`,
    documentContextIntro: "Asking in",
    documentContextSuffix: ".",
    emptyStateIntro:
      "I can help with symptoms, results, and next steps. Try one of these prompts:",
    escalationNotice:
      "Urgent symptoms detected. Contact your care team today. If symptoms are severe, seek emergency care now.",
    inputPlaceholder: "Type or speak a message...",
    quickPrompts: [
      "Explain my recent results",
      "Should I worry about this symptom?",
      "Help me prepare questions for my doctor",
    ],
    welcomeMessage:
      "Hi. I can help explain results, track symptoms, and prepare questions for your doctor.",
  },
  "en-US": {
    careTeamLabel: "Care team messages",
    careTeamIntro: "Choose a linked clinician to exchange messages, separate from your AI conversation.",
    careTeamEmpty: "No care-team messages yet.",
    historicalCareTeamLabel: "Historical care-team messages",
    historicalCareTeamIntro: "Read-only prior messages. Sender and recipient routing is not available for these records. They are separate from addressed conversations and cannot be replied to here.",
    assistantDescription: "AI care assistant",
    typingMessage: `${CARE_ASSISTANT_NAME} is typing...`,
    documentContextIntro: "Asking in",
    documentContextSuffix: ".",
    emptyStateIntro:
      "I can help with symptoms, results, and next steps. Try one of these prompts:",
    escalationNotice:
      "Urgent symptoms detected. Contact your care team today. If symptoms are severe, seek emergency care now.",
    inputPlaceholder: "Type or speak a message...",
    quickPrompts: [
      "Explain my recent results",
      "Should I worry about this symptom?",
      "Help me prepare questions for my doctor",
    ],
    welcomeMessage:
      "Hi. I can help explain results, track symptoms, and prepare questions for your doctor.",
  },
  "es-MX": {
    careTeamLabel: "Mensajes del equipo clínico",
    careTeamIntro: "Elige a un profesional clínico vinculado para intercambiar mensajes, separados de tu conversación con IA.",
    careTeamEmpty: "Todavía no hay mensajes de tu equipo clínico.",
    historicalCareTeamLabel: "Mensajes históricos del equipo clínico",
    historicalCareTeamIntro: "Mensajes anteriores de solo lectura. Estos registros no incluyen información sobre quién envió o recibió el mensaje. Están separados de las conversaciones dirigidas y no se pueden responder aquí.",
    assistantDescription: "Asistente de cuidado con IA",
    typingMessage: `${CARE_ASSISTANT_NAME} está escribiendo...`,
    documentContextIntro: "Consultando en",
    documentContextSuffix: ".",
    emptyStateIntro:
      "Puedo ayudarte con síntomas, resultados y próximos pasos. Prueba una de estas preguntas:",
    escalationNotice:
      "Se detectaron síntomas urgentes. Contacta a tu equipo clínico hoy. Si los síntomas son graves, busca atención de emergencia ahora.",
    inputPlaceholder: "Escribe o habla un mensaje...",
    quickPrompts: [
      "Explica mis resultados recientes",
      "¿Debo preocuparme por este síntoma?",
      "Ayúdame a preparar preguntas para mi médico",
    ],
    welcomeMessage:
      "Hola. Puedo ayudarte a entender resultados, seguir síntomas y preparar preguntas para tu médico.",
  },
};

export function getPatientChatCopy(locale: Locale): PatientChatCopy {
  return resolveLocaleResource(locale, PATIENT_CHAT_COPY);
}

/** PAT-001-A interface wording; es-MX candidates are tracked for bilingual review. */
export function getChatRecoveryCopy(locale: Locale) {
  return locale === "es-MX" ? {
    interrupted: "La respuesta quedó incompleta",
    uncertain: "Es posible que se haya registrado una acción. No la repetiremos automáticamente. Si necesitas ayuda, contacta a tu equipo de atención.",
    // DRAFT es-MX, pending bilingual review.
    leaveAndReturn: "Puedes salir; la respuesta aparecerá aquí.",
    safeRetry: "Puedes reintentar el mismo mensaje sin enviarlo dos veces.",
    noRetry: "No volveremos a ejecutar este mensaje. Puedes continuar con una pregunta nueva.",
    retry: "Reintentar mensaje",
    leaveUnfinished: "Dejar esta respuesta incompleta",
    reconnectBeforeRetry: "Vuelve a conectar el chat para reintentar este mensaje.",
    waitBeforeRetry: "Espera a que termine la respuesta en curso antes de reintentar este mensaje.",
    busy: "Ya hay una respuesta en curso en esta conversación, posiblemente en otra pestaña. Estamos recuperándola. Tu nuevo mensaje sigue en el cuadro de texto.",
    expired: "Esa respuesta tardó demasiado y no se guardó. Tu mensaje está guardado: usa Reintentar mensaje más abajo.",
    unavailable: "Nora no está disponible en este momento. No se enviará ningún mensaje hasta que el chat vuelva a conectarse. Puedes reintentar la conexión.",
    reconnect: "Volver a conectar",
    replyUnavailable: "La respuesta de esta conversación ya no está disponible. No la volveremos a ejecutar. Puedes continuar con una pregunta nueva.",
  } : {
    interrupted: "The reply was interrupted",
    uncertain: "An action may already have been recorded. We will not repeat it automatically. Contact your care team if you need help.",
    leaveAndReturn: "You can leave; the reply will appear here.",
    safeRetry: "You can retry the same message without sending it twice.",
    noRetry: "We will not rerun this message. You can continue with a new question.",
    retry: "Retry message",
    leaveUnfinished: "Leave this reply unfinished",
    reconnectBeforeRetry: "Reconnect chat before retrying this message.",
    waitBeforeRetry: "Wait for the reply in progress to finish before retrying this message.",
    busy: "A reply is already in progress in this conversation, possibly in another tab. We are recovering it. Your new message is still in the composer.",
    expired: "That reply took too long and was not kept. Your message is saved: use Retry message below.",
    unavailable: "Nora is temporarily unavailable. No message will be sent until chat reconnects. You can retry the connection.",
    reconnect: "Reconnect chat",
    replyUnavailable: "The reply for this message is no longer available. We will not rerun it. You can continue with a new question.",
  };
}

export function getChatControlsCopy(locale: Locale) {
  return locale === "es-MX" ? {
    connection: { idle: "Sin conexión", connected: "Conectado", connecting: "Conectando…", disconnected: "Sin conexión", error: "Problema de conexión", reconnecting: "Reconectando…" },
    caution: "Nora es una IA y puede equivocarse. No cambies tu tratamiento sin consultar a tu equipo clínico. Para una emergencia, llama al 911.",
    loading: "Cargando conversación…", recordContext: "Registro adjunto", dismiss: "Cerrar", message: "Mensaje para Nora", send: "Enviar mensaje",
    documentUnavailable: "Este documento no está disponible o cambió. Desvincúlalo antes de hacer una pregunta sobre el resto de tu expediente.",
    speak: "Toca para hablar", stopVoice: "Detener grabación de voz", interrupt: "Interrumpir y hablar", listening: "Escuchando…", transcribing: "Transcribiendo…",
    handsFreeOn: "Manos libres: activado", handsFreeOff: "Activar manos libres", autoPlay: "Las respuestas de voz se reproducirán automáticamente.",
    chatError: "No se pudo cargar o completar la conversación. Revisa la conexión y vuelve a intentarlo.", voiceError: "No se pudo completar la función de voz. Puedes escribir tu mensaje.",
    original: "Idioma original", originalUnknown: "Mensaje original · idioma no registrado", live: "Respuesta en curso", listen: "Escuchar",
    humanOriginal: "Los mensajes se muestran tal como se escribieron, sin traducción automática.",
    profileRequired: "Necesitamos cargar tu idioma preferido antes de enviar. Si tarda demasiado, vuelve a abrir Chat.",
  } : {
    connection: { idle: "Offline", connected: "Connected", connecting: "Connecting…", disconnected: "Offline", error: "Connection issue", reconnecting: "Reconnecting…" },
    caution: "Nora is AI and can make mistakes. Check with your care team before changing treatment. For an emergency, call 911.",
    loading: "Loading conversation…", recordContext: "Record context attached", dismiss: "Dismiss", message: "Message to Nora", send: "Send message",
    documentUnavailable: "This document is unavailable or has changed. Dismiss it before asking about the rest of your record.",
    speak: "Tap to speak", stopVoice: "Stop voice recording", interrupt: "Interrupt and speak", listening: "Listening…", transcribing: "Transcribing…",
    handsFreeOn: "Hands-free mode is on. Tap to turn off.", handsFreeOff: "Turn on hands-free mode", autoPlay: "Voice replies will play automatically.",
    chatError: "Could not load or complete the conversation. Check your connection and try again.", voiceError: "Could not complete the voice action. You can type your message.",
    original: "Original language", originalUnknown: "Original message · language not recorded", live: "Live response", listen: "Listen",
    humanOriginal: "Messages appear as written, without automatic translation.",
    profileRequired: "Your preferred language needs to load before sending. If this takes too long, reopen Chat.",
  };
}

/** Interface copy for a results card under a Nora reply. Names and values stay as printed. */
export function getChatResultsCopy(locale: Locale) {
  return locale === "es-MX" ? {
    eyebrow: "Resultados de este reporte",
    fallbackTitle: "Tu reporte",
    criticalContact: "Comunícate hoy con tu equipo de atención.",
    criticalEmergency: "Llama al 911 si tienes dolor de pecho, palpitaciones o dificultad para respirar.",
    outOfRange: "Fuera del rango del reporte",
    allWithinRange: "Todos los resultados están dentro de los rangos del reporte.",
    showInRange: (count: number) => count === 1 ? "Mostrar 1 resultado dentro del rango" : `Mostrar ${count} resultados dentro del rango`,
    hideInRange: "Ocultar resultados dentro del rango",
    showMeasurements: (count: number) => count === 1 ? "Mostrar 1 medición" : `Mostrar ${count} mediciones`,
    hideMeasurements: "Ocultar mediciones",
    inRange: "Dentro del rango",
    measurements: "Mediciones",
    notReviewed: "Leído automáticamente · aún no revisado por tu equipo de atención",
    reviewed: "Revisado por tu equipo de atención",
    seeInRecords: "Ver en Registros",
  } : {
    eyebrow: "Results from this report",
    fallbackTitle: "Your report",
    criticalContact: "Contact your care team today.",
    criticalEmergency: "Call 911 if you have chest pain, palpitations or trouble breathing.",
    outOfRange: "Outside the report's range",
    allWithinRange: "All results are within the report's ranges.",
    showInRange: (count: number) => count === 1 ? "Show 1 result in range" : `Show ${count} results in range`,
    hideInRange: "Hide results in range",
    showMeasurements: (count: number) => count === 1 ? "Show 1 measurement" : `Show ${count} measurements`,
    hideMeasurements: "Hide measurements",
    inRange: "In range",
    measurements: "Measurements",
    notReviewed: "Read automatically · not yet reviewed by your care team",
    reviewed: "Reviewed by your care team",
    seeInRecords: "See in Records",
  };
}
