import type { Locale } from "@/types";

// New Spanish wording is a draft pending LOC-001 review.
const english = {
  heading: "My symptoms",
  loading: "Loading your symptom reports…",
  errorTitle: "Could not load your symptoms",
  errorDetail: "Your reports are safe. Try again in a moment.",
  emptyTitle: "No confirmed symptom reports yet",
  emptyDetail:
    "When you confirm a symptom report with Nora, it will appear here with what happened next.",
  more: "Showing your most recent reports.",
  severity: (value: number | null) =>
    value === null ? "Severity not given" : `Severity ${value} of 10`,
  rowLabel: (symptom: string, severity: string, date: string) =>
    `${symptom}, ${severity}, ${date}`,
  status: {
    reported: "Reported",
    shared: "Sent to your care team",
    reviewed: "Reviewed",
  },
  detailTitle: "Symptom report",
  back: "Back to symptoms",
  notFoundTitle: "Report not found",
  notFoundDetail: "This report is not available to you.",
  answers: "What you confirmed",
  answersNote: "Shown as you confirmed it, in the language you used.",
  noAnswers: "No answers were saved with this report.",
  whenReported: "Confirmed",
  onset: "Started",
  duration: "Lasted",
  progress: "What happened next",
  events: {
    reported: "You confirmed this report",
    shared_with_care_team: "Sent to your care team",
    flagged_urgent: "Marked for urgent review by your care team",
    reviewed: (name: string | null) =>
      name ? `Reviewed by ${name}` : "Reviewed by your care team",
  },
  disclaimer:
    "This is a record of what you reported. It is not a diagnosis. In an emergency, call 911.",
  retry: "Try again",
};

type Copy = typeof english;

const spanish: Copy = {
  heading: "Mis síntomas",
  loading: "Cargando tus reportes de síntomas…",
  errorTitle: "No se pudieron cargar tus síntomas",
  errorDetail: "Tus reportes están a salvo. Intenta de nuevo en un momento.",
  emptyTitle: "Aún no hay reportes de síntomas confirmados",
  emptyDetail:
    "Cuando confirmes un reporte de síntomas con Nora, aparecerá aquí con lo que sucedió después.",
  more: "Se muestran tus reportes más recientes.",
  severity: (value) =>
    value === null ? "Intensidad no indicada" : `Intensidad ${value} de 10`,
  rowLabel: (symptom, severity, date) => `${symptom}, ${severity}, ${date}`,
  status: {
    reported: "Reportado",
    shared: "Enviado a tu equipo de atención",
    reviewed: "Revisado",
  },
  detailTitle: "Reporte de síntoma",
  back: "Volver a síntomas",
  notFoundTitle: "Reporte no encontrado",
  notFoundDetail: "Este reporte no está disponible para ti.",
  answers: "Lo que confirmaste",
  answersNote: "Se muestra como lo confirmaste, en el idioma que usaste.",
  noAnswers: "No se guardaron respuestas con este reporte.",
  whenReported: "Confirmado",
  onset: "Empezó",
  duration: "Duró",
  progress: "Qué pasó después",
  events: {
    reported: "Confirmaste este reporte",
    shared_with_care_team: "Enviado a tu equipo de atención",
    flagged_urgent: "Tu equipo de atención lo marcó para revisión urgente",
    reviewed: (name) =>
      name ? `Revisado por ${name}` : "Revisado por tu equipo de atención",
  },
  disclaimer:
    "Este es un registro de lo que reportaste. No es un diagnóstico. En una emergencia, llama al 911.",
  retry: "Intentar de nuevo",
};

export function getSymptomHistoryCopy(locale: Locale): Copy {
  return locale === "es-MX" ? spanish : english;
}

export function formatSymptomTime(value: string, locale: Locale, timezone: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const options: Intl.DateTimeFormatOptions = {
    dateStyle: "medium",
    timeStyle: "short",
  };
  try {
    return new Intl.DateTimeFormat(locale, { ...options, timeZone: timezone }).format(date);
  } catch {
    return new Intl.DateTimeFormat(locale, { ...options, timeZone: "UTC" }).format(date);
  }
}
