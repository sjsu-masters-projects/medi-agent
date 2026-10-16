import { normalizeLocale, resolveLocaleResource, type Locale, type LocaleResourceMap } from "@/types";

const english = {
    locale: "en-US" as Locale,
    writtenIn: (content: Locale): string => content === "es-MX" ? "Written in Spanish by your care team" : "Written in English by your care team",
    today: "Today", hello: "Hi there", greeting: (name: string) => `Hi, ${name}`,
    progress: "Daily progress", completed: (done: number, total: number) => `${done} of ${total} tasks completed`,
    progressHelp: "About this progress", progressDetail: "Completed activities out of the activities shown for today, including upcoming ones. It is not a health score.",
    refresh: "Refresh schedule", refreshing: "Refreshing schedule…", loading: "Loading today's activities…",
    streak: (days: number) => `${days}-day streak`, schedule: "Today's schedule",
    count: (count: number) => `${count} tasks`, setup: "Set reminder times",
    setupDetail: "Some care-plan items still need your preferred days and times.",
    setTime: "Set reminder time", anyTime: "Any time", now: "Now",
    approved: "Care-team approved", details: "Care plan details",
    planDetail: (version: number) => `Approved care plan, version ${version}`,
    planVersion: (version: number) => `Version ${version}`,
    categories: { medication: "medication", movement: "movement", nutrition: "nutrition", hydration: "hydration", monitoring: "monitoring", follow_up: "follow up", other: "other" },
    stale: "Schedule may be stale", loadError: "Could not load schedule", retry: "Try again",
    empty: "Nothing scheduled", emptyDetail: "Your clinicians have not assigned anything for today.",
    symptom: "Report a symptom", symptomDetail: "Describe how you feel with Nora, your AI care assistant.",
    barrier: "I couldn't do this", barrierTitle: "I couldn’t do this",
    barrierDetail: "Choose what got in the way. Your care team can use this to follow up.",
    barriers: { side_effects: "Side effects", cost: "Cost", access: "Access", schedule: "Schedule", confusion: "Confusion", other: "Other (please describe)" },
    saving: "Saving…", send: "Send to care team", close: "Close modal",
    statuses: { skipped: "Barrier reported", missed: "Missed", active: "Due now", available: "Available", upcoming: "upcoming", completed: "completed" },
    taken: "Mark as Taken", done: "Mark as Done", prescription: "Take as prescribed.",
    approvedBy: (name: string) => `Care plan approved by ${name}`, prescribedBy: (name: string) => `Prescribed by ${name}`,
    activity: { custom: "Care activity", diet: "Nutrition activity", exercise: "Movement activity", hydration: "Hydration activity", monitoring: "Health check", follow_up: "Follow-up activity" },
    types: { custom: "Care", diet: "Diet", exercise: "Move", hydration: "Hydration", monitoring: "Check", follow_up: "Follow-up" },
};

export type TodayCopy = typeof english;
const spanish: TodayCopy = {
    locale: "es-MX",
    writtenIn: (content) => content === "en-US" ? "Escrito en inglés por tu equipo de atención" : "Escrito en español por tu equipo de atención",
    today: "Hoy", hello: "Hola", greeting: (name) => `Hola, ${name}`,
    progress: "Progreso diario", completed: (done, total) => `${done} de ${total} tareas completadas`,
    progressHelp: "Sobre este progreso", progressDetail: "Actividades completadas de las que se muestran hoy, incluidas las próximas. No es una calificación de salud.",
    refresh: "Actualizar actividades", refreshing: "Actualizando actividades…", loading: "Cargando las actividades de hoy…",
    streak: (days) => `Racha de ${days} días`, schedule: "Actividades de hoy",
    count: (count) => `${count} ${count === 1 ? "tarea" : "tareas"}`, setup: "Configurar horarios de recordatorios",
    setupDetail: "Algunas actividades de tu plan de atención aún necesitan tus días y horarios preferidos.",
    setTime: "Configurar horario del recordatorio", anyTime: "En cualquier momento", now: "Ahora",
    approved: "Aprobado por tu equipo de atención", details: "Detalles del plan de atención",
    planDetail: (version) => `Plan de atención aprobado, versión ${version}`,
    planVersion: (version) => `Versión ${version}`,
    categories: { medication: "medicamento", movement: "movimiento", nutrition: "nutrición", hydration: "hidratación", monitoring: "monitoreo", follow_up: "seguimiento", other: "otra actividad" },
    stale: "Las actividades pueden estar desactualizadas", loadError: "No se pudieron cargar las actividades", retry: "Intentar de nuevo",
    empty: "No hay actividades programadas", emptyDetail: "Tu equipo de atención no ha asignado actividades para hoy.",
    symptom: "Reportar un síntoma", symptomDetail: "Describe cómo te sientes con Nora, tu asistente de atención con IA.",
    barrier: "No pude hacer esto", barrierTitle: "No pude hacer esto",
    barrierDetail: "Elige qué te lo impidió. Tu equipo de atención puede usar esta información para dar seguimiento.",
    barriers: { side_effects: "Efectos secundarios", cost: "Costo", access: "Acceso", schedule: "Horario", confusion: "Confusión", other: "Otro (describe el motivo)" },
    saving: "Guardando…", send: "Enviar al equipo de atención", close: "Cerrar ventana",
    statuses: { skipped: "Dificultad reportada", missed: "No realizada", active: "Para ahora", available: "Disponible", upcoming: "Próxima", completed: "Completada" },
    taken: "Marcar como tomado", done: "Marcar como completada", prescription: "Toma según la receta.",
    approvedBy: (name) => `Plan de atención aprobado por ${name}`, prescribedBy: (name) => `Recetado por ${name}`,
    activity: { custom: "Actividad de atención", diet: "Actividad de nutrición", exercise: "Actividad de movimiento", hydration: "Actividad de hidratación", monitoring: "Control de salud", follow_up: "Actividad de seguimiento" },
    types: { custom: "Atención", diet: "Nutrición", exercise: "Movimiento", hydration: "Hidratación", monitoring: "Control", follow_up: "Seguimiento" },
};
const resources: LocaleResourceMap<TodayCopy> = { default: english, "en-US": english, "es-MX": spanish };
export function getTodayCopy(locale?: Locale): TodayCopy {
    return resolveLocaleResource(normalizeLocale(locale), resources);
}

export function getTaskStatusLabel(status: "active" | "upcoming" | "completed" | "missed" | "skipped", time: string, copy: TodayCopy): string {
    return status === "active" && !time ? copy.statuses.available : copy.statuses[status];
}

export function getCarePlanCategoryLabel(category: string, copy: TodayCopy): string {
    return Object.prototype.hasOwnProperty.call(copy.categories, category)
        ? copy.categories[category as keyof TodayCopy["categories"]]
        : copy.activity.custom;
}
