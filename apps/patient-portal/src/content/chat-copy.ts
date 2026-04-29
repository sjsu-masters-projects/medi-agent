import { resolveLocaleResource, type Locale, type LocaleResourceMap } from "@/types";

interface PatientChatCopy {
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
        documentContextIntro: "Asking in",
        documentContextSuffix: ".",
        emptyStateIntro: "I can help with symptoms, results, and next steps. Try one of these prompts:",
        escalationNotice: "Urgent symptoms detected. Contact your care team today. If symptoms are severe, seek emergency care now.",
        inputPlaceholder: "Type or speak a message...",
        quickPrompts: [
            "Explain my recent results",
            "Should I worry about this symptom?",
            "Help me prepare questions for my doctor",
        ],
        welcomeMessage: "Hi. I can help explain results, track symptoms, and prepare questions for your doctor.",
    },
    "en-US": {
        documentContextIntro: "Asking in",
        documentContextSuffix: ".",
        emptyStateIntro: "I can help with symptoms, results, and next steps. Try one of these prompts:",
        escalationNotice: "Urgent symptoms detected. Contact your care team today. If symptoms are severe, seek emergency care now.",
        inputPlaceholder: "Type or speak a message...",
        quickPrompts: [
            "Explain my recent results",
            "Should I worry about this symptom?",
            "Help me prepare questions for my doctor",
        ],
        welcomeMessage: "Hi. I can help explain results, track symptoms, and prepare questions for your doctor.",
    },
    "es-MX": {
        documentContextIntro: "Consultando en",
        documentContextSuffix: ".",
        emptyStateIntro: "Puedo ayudarte con síntomas, resultados y próximos pasos. Prueba una de estas preguntas:",
        escalationNotice: "Se detectaron síntomas urgentes. Contacta a tu equipo clínico hoy. Si los síntomas son graves, busca atención de emergencia ahora.",
        inputPlaceholder: "Escribe o habla un mensaje...",
        quickPrompts: [
            "Explica mis resultados recientes",
            "¿Debo preocuparme por este síntoma?",
            "Ayúdame a preparar preguntas para mi médico",
        ],
        welcomeMessage: "Hola. Puedo ayudarte a entender resultados, seguir síntomas y preparar preguntas para tu médico.",
    },
};

export function getPatientChatCopy(locale: Locale): PatientChatCopy {
    return resolveLocaleResource(locale, PATIENT_CHAT_COPY);
}
