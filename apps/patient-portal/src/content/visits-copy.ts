import {
  resolveLocaleResource,
  type Locale,
  type LocaleResourceMap,
} from "@/types";

const english = {
  minutes: "min",
  preparationNotes: "Preparation notes",
  upcomingSummary: { one: "upcoming visit", other: "upcoming visits" },
  types: {
    follow_up: "Follow-up",
    initial: "First visit",
    routine: "Routine check",
    urgent: "Urgent",
    pre_op: "Pre-operative",
  },
  offerTitle: "Your clinician offered these times",
  choose: "Choose this time",
  offerDecline: {
    label: "Reason for declining (optional)",
    placeholder: "Let your care team know why",
    confirm: "Decline offer",
  },
  declineOffer: "Decline these times",
  differentTimes: "Request different times",
  title: "Visits",
  subtitle: "Review and confirm appointments from your care team.",
  loading: "Loading your visits...",
  loadingSettings: "Loading your visit settings...",
  loadError: "Could not load your visits",
  loadErrorDetail: "Please try loading your visits again.",
  actionError:
    "Could not update this visit. Refresh your visits and try again.",
  conflictError:
    "This time overlaps another booked visit. Choose another time or ask your care team for different times.",
  expiredError:
    "This offer has expired. Refresh your visits to see the available times.",
  unavailableError:
    "This appointment is no longer available. Refresh your visits before trying again.",
  pastError:
    "This appointment time has passed. Refresh your visits and choose a future time.",
  availableUntil: "Available until",
  responseSavedRefreshError:
    "Your response was saved, but the latest visits could not be loaded. Refresh your visits to check the full offer.",
  expiredDetail:
    "This time is no longer available. Your care team can offer new times.",
  retry: "Try again",
  refreshVisits: "Refresh visits",
  fallback: "Your saved timezone is unavailable. Times are shown in UTC.",
  emptyTitle: "No visits yet",
  emptyDetail:
    "When your clinician proposes a visit, it will appear here for you to accept, decline, or request a different time.",
  proposed: "Awaiting your response",
  upcoming: "Upcoming",
  waiting: "Waiting on your care team",
  past: "Past & other",
  with: "With",
  note: "Your note:",
  accept: "Accept",
  decline: "Decline",
  cancel: "Cancel",
  cancelVisit: "Cancel visit",
  back: "Back",
  request: "Request a different time",
  invalidDate: "Appointment time unavailable",
  statuses: {
    withdrawn: "Withdrawn",
    expired: "Expired",
    proposed: "Proposed",
    confirmed: "Confirmed",
    scheduled: "Scheduled",
    declined: "Declined",
    alternative_requested: "Change requested",
    cancelled: "Cancelled",
    completed: "Completed",
    no_show: "Missed",
  },
  compose: {
    request_alternative: {
      label: "What times work better? (optional)",
      placeholder: "e.g. mornings, or after next week",
      confirm: "Send request",
    },
    cancel: {
      label: "Reason for cancelling (optional)",
      placeholder: "Let your care team know why",
      confirm: "Confirm cancellation",
    },
  },
};
export type VisitsCopy = typeof english;
const spanish: VisitsCopy = {
  minutes: "min",
  preparationNotes: "Notas de preparación",
  upcomingSummary: { one: "próxima cita", other: "próximas citas" },
  types: {
    follow_up: "Seguimiento",
    initial: "Primera consulta",
    routine: "Revisión de rutina",
    urgent: "Urgente",
    pre_op: "Preoperatoria",
  },
  offerTitle: "Tu equipo de atención ofreció estos horarios",
  choose: "Elegir este horario",
  offerDecline: {
    label: "Motivo del rechazo (opcional)",
    placeholder: "Explica el motivo a tu equipo de atención",
    confirm: "Rechazar propuesta",
  },
  declineOffer: "Rechazar estos horarios",
  differentTimes: "Solicitar otros horarios",
  title: "Citas",
  subtitle: "Revisa y confirma las citas propuestas por tu equipo de atención.",
  loading: "Cargando tus citas...",
  loadingSettings: "Cargando la configuración de tus citas...",
  loadError: "No se pudieron cargar tus citas",
  loadErrorDetail: "Intenta cargar tus citas de nuevo.",
  actionError:
    "No se pudo actualizar esta cita. Actualiza tus citas e inténtalo de nuevo.",
  conflictError:
    "Este horario se empalma con otra cita programada. Elige otro horario o solicita otros horarios a tu equipo de atención.",
  expiredError:
    "Esta propuesta venció. Actualiza tus citas para ver los horarios disponibles.",
  unavailableError:
    "Esta cita ya no está disponible. Actualiza tus citas antes de intentarlo de nuevo.",
  pastError:
    "El horario de esta cita ya pasó. Actualiza tus citas y elige un horario futuro.",
  availableUntil: "Disponible hasta",
  responseSavedRefreshError:
    "Tu respuesta se guardó, pero no se pudieron cargar las citas más recientes. Actualiza tus citas para revisar la propuesta completa.",
  expiredDetail:
    "Este horario ya no está disponible. Tu equipo de atención puede ofrecer nuevos horarios.",
  retry: "Intentar de nuevo",
  refreshVisits: "Actualizar citas",
  fallback:
    "Tu zona horaria guardada no está disponible. Los horarios se muestran en UTC.",
  emptyTitle: "Aún no tienes citas",
  emptyDetail:
    "Cuando tu equipo de atención proponga una cita, aparecerá aquí para que la aceptes, la rechaces o solicites otro horario.",
  proposed: "Esperando tu respuesta",
  upcoming: "Próximas citas",
  waiting: "Esperando a tu equipo de atención",
  past: "Citas pasadas y otras",
  with: "Con",
  note: "Tu nota:",
  accept: "Aceptar",
  decline: "Rechazar",
  cancel: "Cancelar",
  cancelVisit: "Cancelar cita",
  back: "Volver",
  request: "Solicitar otro horario",
  invalidDate: "Horario de la cita no disponible",
  statuses: {
    withdrawn: "Retirada",
    expired: "Vencida",
    proposed: "Propuesta",
    confirmed: "Confirmada",
    scheduled: "Programada",
    declined: "Rechazada",
    alternative_requested: "Cambio solicitado",
    cancelled: "Cancelada",
    completed: "Completada",
    no_show: "No asististe",
  },
  compose: {
    request_alternative: {
      label: "¿Qué horarios te convienen más? (opcional)",
      placeholder:
        "Por ejemplo, por las mañanas o después de la próxima semana",
      confirm: "Enviar solicitud",
    },
    cancel: {
      label: "Motivo de la cancelación (opcional)",
      placeholder: "Explica el motivo a tu equipo de atención",
      confirm: "Confirmar cancelación",
    },
  },
};
const resources: LocaleResourceMap<VisitsCopy> = {
  default: english,
  "en-US": english,
  "es-MX": spanish,
};
export function getVisitsCopy(locale: Locale): VisitsCopy {
  return resolveLocaleResource(locale, resources);
}

export function formatUpcomingVisitCount(
  count: number,
  locale: Locale,
): string {
  const copy = getVisitsCopy(locale);
  const label =
    count === 1 ? copy.upcomingSummary.one : copy.upcomingSummary.other;
  return `${new Intl.NumberFormat(locale).format(count)} ${label}.`;
}

export function resolveVisitsTimezone(value: string | undefined): {
  timezone: string;
  fallback: boolean;
} {
  if (value?.trim()) {
    try {
      new Intl.DateTimeFormat("en-US", { timeZone: value });
      return { timezone: value, fallback: false };
    } catch {
      /* Invalid saved zones must never fall back to the browser's timezone. */
    }
  }
  return { timezone: "UTC", fallback: true };
}

export function formatVisitTime(
  value: string,
  locale: Locale,
  timezone: string,
): string | null {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return null;
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "full",
    timeStyle: "short",
    timeZone: timezone,
  }).format(date);
}
