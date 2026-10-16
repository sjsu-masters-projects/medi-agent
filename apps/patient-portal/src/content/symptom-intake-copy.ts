import { resolveLocaleResource, type Locale, type LocaleResourceMap } from "@/types";

const en = {
    title: "Draft — not submitted", start: "Start a symptom draft", intro: "Form answers remain private until you confirm. Your initial Nora message remains in chat history.",
    loading: "Loading your draft…", unavailable: "Guided intake is unavailable. Reload the saved state to check any prior action.",
    error: "We could not verify this action. Reload the saved state before retrying.", reload: "Reload saved state", retry: "Retry the same action",
    save: "Save answer", unknown: "I don’t know", declined: "Prefer not to answer", edit: "Edit", review: "Review before sharing", cancel: "Cancel draft",
    confirm: "Confirm and share with my care team", consent: "I reviewed this preview and want to share it with my care team.",
    reported: "What you reported", context: "Relevant information from your record", summary: "Summary for your care team", emptyContext: "No relevant record context was used.",
    saved: "Report saved for care-team review", cancelled: "Draft cancelled. Your chat history was not deleted.",
    interrupted: "Intake interrupted for safety", pending: "The safety save could not be verified.",
    timezone: "Saved patient timezone", fallback: "UTC fallback — saved timezone unavailable", progress: "Questions resolved", value: "Your answer",
    yes: "Yes", no: "No", productConcern: "I am concerned about a medicine or other product", name: "Product name", strength: "Strength", dose: "Dose", route: "Route",
    indication: "Reason for use", startDate: "Started (your words)", stop: "Stopped (your words)", change: "Changed (your words)",
    states: { answered: "Answered", unknown: "Unknown", declined: "Declined", not_asked: "Not asked", not_applicable: "Not applicable" },
};
const es: typeof en = {
    title: "Borrador — no enviado", start: "Iniciar un borrador de síntomas", intro: "Las respuestas del formulario son privadas hasta que confirmes. Tu mensaje inicial a Nora permanece en el historial del chat.",
    loading: "Cargando tu borrador…", unavailable: "La captura guiada no está disponible. Carga el estado guardado para verificar una acción anterior.",
    error: "No pudimos verificar esta acción. Vuelve a cargar el estado guardado antes de reintentar.", reload: "Cargar el estado guardado", retry: "Reintentar la misma acción",
    save: "Guardar respuesta", unknown: "No sé", declined: "Prefiero no responder", edit: "Editar", review: "Revisar antes de compartir", cancel: "Cancelar borrador",
    confirm: "Confirmar y compartir con mi equipo clínico", consent: "Revisé esta vista previa y quiero compartirla con mi equipo clínico.",
    reported: "Lo que reportaste", context: "Información relevante de tu expediente", summary: "Resumen para tu equipo clínico", emptyContext: "No se usó información relevante del expediente.",
    saved: "Informe guardado para revisión del equipo clínico", cancelled: "Borrador cancelado. No se eliminó tu historial del chat.",
    interrupted: "Captura interrumpida por seguridad", pending: "No se pudo verificar el guardado de seguridad.",
    timezone: "Zona horaria guardada del paciente", fallback: "Se usa UTC porque la zona horaria guardada no está disponible", progress: "Preguntas resueltas", value: "Tu respuesta",
    yes: "Sí", no: "No", productConcern: "Me preocupa algún medicamento u otro producto", name: "Nombre del producto", strength: "Concentración", dose: "Dosis", route: "Vía",
    indication: "Motivo de uso", startDate: "Inicio (tus palabras)", stop: "Suspensión (tus palabras)", change: "Cambio (tus palabras)",
    states: { answered: "Respondida", unknown: "No sé", declined: "Prefiero no responder", not_asked: "No preguntada", not_applicable: "No aplica" },
};
const copy: LocaleResourceMap<typeof en> = { default: en, "en-US": en, "es-MX": es };
export const getSymptomIntakeCopy = (locale: Locale) => resolveLocaleResource(locale, copy);

export function intakeErrorCopy(code: string, locale: Locale) {
    const es = locale === "es-MX";
    if (code === "INTAKE_RECOVERY_UNAVAILABLE") return es
        ? "No pudimos cargar los borradores de síntomas. Vuelve a cargar para intentar de nuevo."
        : "We could not load symptom drafts. Reload to try again.";
    if (code === "INTAKE_LIBRARY_UNAVAILABLE") return getSymptomIntakeCopy(locale).unavailable;
    if (["INTAKE_REVISION_CONFLICT", "INTAKE_MUTATION_CONFLICT", "INTAKE_PREVIEW_STALE"].includes(code)) return es
        ? "El borrador cambió. Carga el estado guardado y revisa una nueva vista previa."
        : "The draft changed. Reload the saved state and review a new preview.";
    if (code === "INTAKE_TERMINAL") return es ? "Esta captura ya terminó. Carga el estado guardado." : "This intake has ended. Reload the saved state.";
    if (code === "INTAKE_ANSWER_INVALID") return es ? "Revisa tu respuesta e intenta de nuevo." : "Check your answer and try again.";
    return getSymptomIntakeCopy(locale).error;
}
export function intakeValueCopy(value: unknown, locale: Locale): string {
    const copy = getSymptomIntakeCopy(locale);
    if (typeof value === "boolean") return value ? copy.yes : copy.no;
    if (value && typeof value === "object") {
        const labels: Record<string, string> = { concern: copy.productConcern, name: copy.name, strength: copy.strength,
            dose: copy.dose, route: copy.route, indication: copy.indication, start: copy.startDate, stop: copy.stop, change: copy.change };
        return Object.entries(value).map(([key, item]) => `${labels[key] ?? key}: ${intakeValueCopy(item, locale)}`).join("; ");
    }
    return String(value ?? "");
}
