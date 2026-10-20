import { resolveVisitsTimezone } from "@/content/visits-copy";
import type {
  PatientADRAnswer,
  PatientADRQuestion,
} from "@/services/adr-follow-up";
import {
  resolveLocaleResource,
  type Locale,
  type LocaleResourceMap,
} from "@/types";

interface QuestionCopy {
  /** Short label used in the review summary and the answered summary. */
  label: string;
  /** Full question shown as the fieldset legend. */
  prompt: string;
  /** Label of the description field shown after "Yes" or "No". */
  evidencePrompt: string;
}

interface StateCopy {
  title: string;
  detail: string;
}

export interface ADRFollowUpCopy {
  eyebrow: string;
  heading: (symptom: string) => string;
  reportedWith: (medication: string) => string;
  careTeamMessage: string;
  caution: string;
  questions: Record<PatientADRQuestion, QuestionCopy>;
  answers: Record<PatientADRAnswer, string>;
  characters: (used: number, max: number) => string;
  reviewAnswers: string;
  reviewHeading: string;
  confirm: string;
  send: string;
  sending: string;
  edit: string;
  unsentNote: string;
  sent: string;
  states: {
    loading: string;
    empty: StateCopy;
    error: StateCopy;
    notFound: StateCopy;
    answered: StateCopy & {
      yourAnswers: string;
      answeredOn: (date: string) => string;
    };
    closed: StateCopy;
    openNewer: string;
    retry: string;
  };
  errors: {
    closed: string;
    notFound: string;
    unavailable: string;
    other: string;
  };
  entry: {
    title: string;
    detail: (count: number) => string;
  };
  recent: {
    toggle: (count: number) => string;
    answered: string;
    closed: string;
  };
  back: string;
}

// en-US keeps the wording of the original follow-up panel, including the
// strings that tests select on ("Yes", "No", "I’m not sure", "Review answers",
// "Send to care team", "Edit").
const EN: ADRFollowUpCopy = {
  eyebrow: "Care team follow-up",
  heading: (symptom) => `Reported symptom (original wording): “${symptom}”`,
  reportedWith: (medication) => `Medication name as recorded: ${medication}.`,
  careTeamMessage: "Message from your care team",
  caution:
    "Answer only from what has already happened. Do not restart, stop, or change a medicine just to answer these questions.",
  questions: {
    reappeared_on_rechallenge: {
      label: "What happened after a past restart",
      prompt:
        "Before this request, did the same symptom return after you had already restarted this medicine? Do not restart it to answer.",
      evidencePrompt: "Describe what happened and when.",
    },
    dose_response: {
      label: "What happened after a past dose change",
      prompt:
        "Before this request, did the symptom change after a clinician-directed dose change? Do not change your dose to answer.",
      evidencePrompt: "Describe the dose change and what happened.",
    },
    similar_previous_reaction: {
      label: "A similar past reaction",
      prompt: "Have you had the same symptom with this medicine before?",
      evidencePrompt: "Describe the earlier reaction and when it happened.",
    },
  },
  answers: {
    yes: "Yes",
    no: "No",
    do_not_know: "I’m not sure",
  },
  characters: (used, max) => `${used} of ${max} characters`,
  reviewAnswers: "Review answers",
  reviewHeading: "Review before sending",
  confirm:
    "I confirm these answers describe what already happened. I was not asked to change or restart a medicine.",
  send: "Send to care team",
  sending: "Sending…",
  edit: "Edit",
  unsentNote:
    "Answers are saved only when you send them. If you leave or reload this page first, they will be lost.",
  sent: "Your answers were sent to your care team.",
  states: {
    loading: "Loading your care team’s questions…",
    empty: {
      title: "No questions right now",
      detail:
        "When your care team asks about a symptom you reported, the questions will appear here.",
    },
    error: {
      title: "Could not load your care team’s questions",
      detail: "Check your connection and try again.",
    },
    notFound: {
      title: "Request not found",
      detail:
        "This request isn’t available. The link may be incorrect or out of date.",
    },
    answered: {
      title: "Answers sent",
      detail:
        "Your care team has your answers. You don’t need to do anything else.",
      yourAnswers: "Your answers",
      answeredOn: (date) => `Answered on ${date}`,
    },
    closed: {
      title: "This request is closed",
      detail:
        "Your care team closed or replaced this request. No answer is needed.",
    },
    openNewer: "Open the newer request",
    retry: "Try again",
  },
  errors: {
    closed:
      "This request is no longer waiting for answers. Nothing new was sent.",
    notFound: "We couldn’t find this request. Nothing was sent.",
    unavailable:
      "We couldn’t reach your care team right now. Your answers are still here. Try again in a moment.",
    other: "We couldn’t save these answers. Nothing was sent. Try again.",
  },
  entry: {
    title: "Questions from your care team",
    detail: (count) =>
      count === 1
        ? "1 request is waiting for your answers"
        : `${count} requests are waiting for your answers`,
  },
  recent: {
    toggle: (count) => `Recent requests (${count})`,
    answered: "Answered",
    closed: "Closed",
  },
  back: "Back to messages",
};

// es-MX uses the second-person "tú" register of existing patient copy
// ("tu equipo de atención"). Pending review by a Spanish-fluent reviewer (D9).
const ES: ADRFollowUpCopy = {
  eyebrow: "Seguimiento de tu equipo de atención",
  heading: (symptom) => `Síntoma reportado (texto original): «${symptom}»`,
  reportedWith: (medication) => `Medicamento (nombre registrado): ${medication}.`,
  careTeamMessage: "Mensaje de tu equipo de atención",
  caution:
    "Responde solo con lo que ya pasó. No reinicies, suspendas ni cambies un medicamento solo para responder estas preguntas.",
  questions: {
    reappeared_on_rechallenge: {
      label: "Qué pasó al reiniciarlo antes",
      prompt:
        "Antes de esta solicitud, ¿el mismo síntoma volvió después de que ya habías reiniciado este medicamento? No lo reinicies para responder.",
      evidencePrompt: "Describe qué pasó y cuándo.",
    },
    dose_response: {
      label: "Qué pasó tras un cambio de dosis anterior",
      prompt:
        "Antes de esta solicitud, ¿el síntoma cambió después de un cambio de dosis indicado por tu profesional de salud? No cambies tu dosis para responder.",
      evidencePrompt: "Describe el cambio de dosis y qué pasó.",
    },
    similar_previous_reaction: {
      label: "Una reacción similar anterior",
      prompt: "¿Has tenido antes el mismo síntoma con este medicamento?",
      evidencePrompt: "Describe la reacción anterior y cuándo ocurrió.",
    },
  },
  answers: {
    yes: "Sí",
    no: "No",
    do_not_know: "No sé",
  },
  characters: (used, max) => `${used} de ${max} caracteres`,
  reviewAnswers: "Revisar respuestas",
  reviewHeading: "Revisa antes de enviar",
  confirm:
    "Confirmo que estas respuestas describen lo que ya pasó. No se me pidió cambiar ni reiniciar ningún medicamento.",
  send: "Enviar al equipo de atención",
  sending: "Enviando…",
  edit: "Editar",
  unsentNote:
    "Tus respuestas solo se guardan cuando las envías. Si sales o recargas esta página antes, se perderán.",
  sent: "Tus respuestas se enviaron a tu equipo de atención.",
  states: {
    loading: "Cargando las preguntas de tu equipo de atención…",
    empty: {
      title: "No hay preguntas por ahora",
      detail:
        "Cuando tu equipo de atención te pregunte sobre un síntoma que reportaste, las preguntas aparecerán aquí.",
    },
    error: {
      title: "No se pudieron cargar las preguntas de tu equipo de atención",
      detail: "Revisa tu conexión e inténtalo de nuevo.",
    },
    notFound: {
      title: "No encontramos esta solicitud",
      detail:
        "Esta solicitud no está disponible. Es posible que el enlace sea incorrecto o ya no esté vigente.",
    },
    answered: {
      title: "Respuestas enviadas",
      detail:
        "Tu equipo de atención ya tiene tus respuestas. No necesitas hacer nada más.",
      yourAnswers: "Tus respuestas",
      answeredOn: (date) => `Respondiste el ${date}`,
    },
    closed: {
      title: "Esta solicitud está cerrada",
      detail:
        "Tu equipo de atención cerró o reemplazó esta solicitud. No necesitas responder.",
    },
    openNewer: "Abrir la solicitud más reciente",
    retry: "Intentar de nuevo",
  },
  errors: {
    closed:
      "Esta solicitud ya no espera respuestas. No se envió nada nuevo.",
    notFound: "No encontramos esta solicitud. No se envió nada.",
    unavailable:
      "No pudimos comunicarnos con tu equipo de atención en este momento. Tus respuestas siguen aquí. Inténtalo de nuevo en un momento.",
    other:
      "No pudimos guardar estas respuestas. No se envió nada. Inténtalo de nuevo.",
  },
  entry: {
    title: "Preguntas de tu equipo de atención",
    detail: (count) =>
      count === 1
        ? "1 solicitud espera tus respuestas"
        : `${count} solicitudes esperan tus respuestas`,
  },
  recent: {
    toggle: (count) => `Solicitudes recientes (${count})`,
    answered: "Respondida",
    closed: "Cerrada",
  },
  back: "Volver a mensajes",
};

const resources: LocaleResourceMap<ADRFollowUpCopy> = {
  default: EN,
  "en-US": EN,
  "es-MX": ES,
};

/** Unsupported or missing locales resolve to `DEFAULT_LOCALE` (en-US). */
export function getADRFollowUpCopy(locale: Locale): ADRFollowUpCopy {
  return resolveLocaleResource(locale, resources);
}

/**
 * Formats a follow-up date (for example `responded_at`) as a long calendar
 * date in the patient's saved timezone. An invalid or missing timezone falls
 * back to UTC, never to the browser's zone. Returns null for invalid input.
 */
export function formatFollowUpDate(
  iso: string,
  locale: Locale,
  timeZone: string | undefined,
): string | null {
  const date = new Date(iso);
  if (!iso || !Number.isFinite(date.getTime())) return null;
  const { timezone } = resolveVisitsTimezone(timeZone);
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "long",
    timeZone: timezone,
  }).format(date);
}
