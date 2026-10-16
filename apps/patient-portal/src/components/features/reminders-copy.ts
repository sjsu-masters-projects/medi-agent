import type { Locale } from "@/types";

// Administrative schedule guidance only; clinical titles, frequency and instructions stay as received.
const spanish: Record<string, string> = {
  "Ask your care team to clarify the frequency before setting routine reminders.":
    "Pide a tu equipo de atención que aclare la frecuencia antes de configurar recordatorios con horario fijo.",
  "As-needed items should not create automatic reminders by default.":
    "Las indicaciones de uso según sea necesario no deben tener recordatorios automáticos de horario fijo.",
  "Follow the activity-based instruction. It does not specify a routine clock-time schedule.":
    "Sigue las instrucciones relacionadas con la actividad. No indican un horario fijo.",
  "Use three evenly spaced reminder times that fit the prescribed interval.":
    "Elige tres horas de recordatorio con intervalos iguales que coincidan con el intervalo indicado.",
  "Keep the days stated in your care instructions; choose the reminder time.":
    "Conserva los días indicados en tu plan de atención y elige la hora del recordatorio.",
  "Choose breakfast and dinner reminder times that match your routine.":
    "Elige horas de recordatorio para el desayuno y la cena que coincidan con tu rutina.",
  "Choose which three days of the week to receive this reminder.":
    "Elige los tres días de la semana en que deseas recibir este recordatorio.",
  "Choose the day of week and time that best fits the weekly plan.":
    "Elige el día de la semana y la hora que coincidan con el plan semanal.",
  "Set breakfast, lunch, and dinner reminder times that match your routine.":
    "Elige horas de recordatorio para el desayuno, la comida y la cena que coincidan con tu rutina.",
  "Set three reminder times across the day.":
    "Elige tres horas de recordatorio durante el día.",
  "Set two reminder times, usually one earlier and one later in the day.":
    "Elige dos horas de recordatorio, por lo general una más temprano y otra más tarde.",
  "Choose the time you usually wind down for the night.":
    "Elige la hora a la que sueles prepararte para dormir.",
  "Choose the time you usually start your morning.":
    "Elige la hora a la que sueles empezar tu mañana.",
  "Choose one daily reminder time.": "Elige una hora de recordatorio diaria.",
  "Choose the exact days and times you want reminder nudges.":
    "Elige los días y las horas de tus recordatorios.",
  "Reminder Settings": "Recordatorios",
  "Unable to load reminder settings": "No se pudieron cargar los recordatorios",
  Timezone: "Zona horaria",
  "Your local schedule": "Tu horario local",
  "Reminder times are interpreted in this timezone.":
    "Esta zona horaria se usa para los recordatorios nuevos. Los recordatorios guardados conservan su zona horaria.",
  "Profile timezone": "Zona horaria del perfil",
  "Saving timezone...": "Guardando zona horaria...",
  "Save timezone": "Guardar zona horaria",
  Medication: "Medicamento",
  "Care activity": "Actividad de cuidado",
  "Review old reminder": "Revisar recordatorio anterior",
  Configured: "Configurado",
  Paused: "En pausa",
  "No routine reminder": "Sin recordatorio de horario fijo",
  "Not set": "Sin configurar",
  "Edit reminder": "Editar recordatorio",
  "Set reminder": "Configurar recordatorio",
  Days: "Días",
  "Reminder times": "Horas de recordatorio",
  "Add time": "Agregar hora",
  Remove: "Quitar",
  "Saving...": "Guardando...",
  "Save reminder schedule": "Guardar recordatorio",
  Cancel: "Cancelar",
  "Clear schedule": "Eliminar recordatorio",
  "Written in Spanish by your care team": "Escrito en español por tu equipo de atención",
  "Written in English by your care team": "Escrito en inglés por tu equipo de atención",
  "Advanced settings": "Ajustes de zona horaria",
  "Reminder timezone:": "Zona horaria del recordatorio:",
  "Timezone updated.": "Zona horaria actualizada.",
  "Try again": "Intentar de nuevo",
  "Refresh reminders": "Actualizar recordatorios",
  "Refreshing...": "Actualizando...",
  "Schedule help": "Ayuda con el horario",
  "No reminders to set": "No hay recordatorios para configurar",
  "Reminders will appear here when your care team adds eligible medications or activities.":
    "Los recordatorios aparecerán aquí cuando tu equipo de atención agregue medicamentos o actividades con un horario definido.",
  "We could not load your reminders. Please try again.":
    "No pudimos cargar tus recordatorios. Inténtalo de nuevo.",
  "We could not confirm your change. Refresh reminders before trying again. Your entered choices are kept here.":
    "No pudimos confirmar el cambio. Actualiza los recordatorios antes de intentarlo de nuevo. Tus opciones ingresadas se conservan aquí.",
  "This item stays available in Today. Routine clock-time reminders require a clear care-team instruction.":
    "Esta actividad sigue disponible en Hoy. Para configurar recordatorios con horario fijo se necesitan instrucciones claras de tu equipo de atención.",
  "Choose times that match the instruction above, including meal or activity timing. These are reminders, not changes to your care plan.":
    "Elige horas que coincidan con las instrucciones, incluidos los horarios de comidas o actividades. Estos recordatorios no cambian tu plan de atención.",
  "Follow the instruction above. Ask your care team if the timing is unclear.":
    "Sigue las instrucciones de arriba. Consulta a tu equipo de atención si el horario no está claro.",
};

export function remindersCopy(locale: Locale, text: string): string {
  return locale === "es-MX" ? (spanish[text] ?? text) : text;
}

export function reminderDayLabel(locale: Locale, day: string): string {
  const days: Record<string, string> = {
    monday: "lun",
    tuesday: "mar",
    wednesday: "mié",
    thursday: "jue",
    friday: "vie",
    saturday: "sáb",
    sunday: "dom",
  };
  return locale === "es-MX" ? (days[day] ?? "") : day.slice(0, 3);
}
