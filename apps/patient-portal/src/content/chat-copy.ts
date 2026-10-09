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
    careTeamIntro: "Messages from your clinic, separate from your AI conversation. To reply, contact your clinic directly.",
    careTeamEmpty: "No care-team messages yet.",
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
    careTeamIntro: "Messages from your clinic, separate from your AI conversation. To reply, contact your clinic directly.",
    careTeamEmpty: "No care-team messages yet.",
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
    careTeamIntro: "Mensajes de tu clínica, separados de tu conversación con IA. Para responder, comunícate directamente con tu clínica.",
    careTeamEmpty: "Todavía no hay mensajes de tu equipo clínico.",
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
