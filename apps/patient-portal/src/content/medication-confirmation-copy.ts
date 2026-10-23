import type { MedicationAnswer, MedicationAnswerErrorClass } from "@/services/medication-confirmations";
import { resolveLocaleResource, type Locale, type LocaleResourceMap } from "@/types";

// es-MX wording reviewed under LOC-001-R (model-assisted meaning-and-safety review, closure addendum).

export interface MedicationConfirmationCopy {
  eyebrow: string;
  from: (clinician: string, specialty: string | null) => string;
  /** `description` is the medicine as recorded, for example "Metformin 500 mg twice daily". */
  question: (description: string) => string;
  answers: Record<MedicationAnswer, string>;
  changedLabel: string;
  changedHint: string;
  characters: (used: number, max: number) => string;
  privacy: string;
  send: string;
  sending: string;
  thanks: string;
  thanksDetail: string;
  errors: Record<MedicationAnswerErrorClass, string>;
  /** Accessible name of the group of answers. */
  group: (medicine: string) => string;
}

const english: MedicationConfirmationCopy = {
  eyebrow: "A question about your medicine",
  from: (clinician, specialty) => (specialty ? `From ${clinician}, ${specialty}` : `From ${clinician}`),
  question: (description) => `Are you still taking ${description}?`,
  answers: {
    yes: "Yes",
    stopped: "No, I stopped",
    changed: "It changed",
    unsure: "Not sure",
  },
  changedLabel: "What changed?",
  changedHint: "For example, a different amount or time of day.",
  characters: (used, max) => `${used} of ${max} characters`,
  privacy:
    "Your answer goes to your care team. It does not change your medicines or your reminders. Keep taking your medicines as prescribed until your care team tells you otherwise.",
  send: "Send answer",
  sending: "Sending…",
  thanks: "Thank you",
  thanksDetail: "Your care team will see your answer.",
  errors: {
    answered: "This question was already answered.",
    expired: "This question has expired. Your care team can ask again.",
    notFound: "This question is no longer available.",
    unavailable: "We could not send your answer. Check your connection and try again.",
    other: "We could not send your answer. Try again in a moment.",
  },
  group: (medicine) => `Your answer about ${medicine}`,
};

const spanish: MedicationConfirmationCopy = {
  eyebrow: "Una pregunta sobre tu medicamento",
  from: (clinician, specialty) => (specialty ? `De ${clinician}, ${specialty}` : `De ${clinician}`),
  question: (description) => `¿Sigues tomando ${description}?`,
  answers: {
    yes: "Sí",
    stopped: "No, lo dejé",
    changed: "Cambió",
    unsure: "No lo sé",
  },
  changedLabel: "¿Qué cambió?",
  changedHint: "Por ejemplo, otra cantidad u otra hora del día.",
  characters: (used, max) => `${used} de ${max} caracteres`,
  privacy:
    "Tu respuesta llega a tu equipo de atención. No cambia tus medicamentos ni tus recordatorios. Sigue tomando tus medicamentos como te los recetaron hasta que tu equipo de atención te indique otra cosa.",
  send: "Enviar respuesta",
  sending: "Enviando…",
  thanks: "Gracias",
  thanksDetail: "Tu equipo de atención verá tu respuesta.",
  errors: {
    answered: "Esta pregunta ya se respondió.",
    expired: "Esta pregunta venció. Tu equipo de atención puede volver a preguntar.",
    notFound: "Esta pregunta ya no está disponible.",
    unavailable: "No pudimos enviar tu respuesta. Revisa tu conexión e inténtalo de nuevo.",
    other: "No pudimos enviar tu respuesta. Inténtalo de nuevo en un momento.",
  },
  group: (medicine) => `Tu respuesta sobre ${medicine}`,
};

const resources: LocaleResourceMap<MedicationConfirmationCopy> = {
  default: english,
  "en-US": english,
  "es-MX": spanish,
};

export function getMedicationConfirmationCopy(locale: Locale): MedicationConfirmationCopy {
  return resolveLocaleResource(locale, resources);
}

/** "Metformin 500 mg twice daily": name, dose, then the cadence in the patient's language. */
export function describeMedicine(
  question: {
    medicationName: string;
    dosage: string | null;
    frequency: string | null;
    frequencyLabelEn: string | null;
    frequencyLabelEs: string | null;
  },
  locale: Locale,
): string {
  const label = locale === "es-MX" ? question.frequencyLabelEs : question.frequencyLabelEn;
  // A reviewed label reads mid-sentence in lower case; an unrecognised phrase stays as written.
  const cadence = label ? label.charAt(0).toLowerCase() + label.slice(1) : question.frequency;
  return [question.medicationName, question.dosage, cadence]
    .map((part) => (part ?? "").trim())
    .filter(Boolean)
    .join(" ");
}
