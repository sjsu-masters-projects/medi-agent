import { resolveLocaleResource, type Locale, type LocaleResourceMap } from "@/types";

// es-MX wording reviewed under LOC-001-R (model-assisted meaning-and-safety review, closure addendum).
const en = {
    offerPrompt: "Would you like me to note this for your care team? I’ll ask a few quick questions here.", offerYes: "Yes, let’s do it", offerNo: "Not now",
    privateTag: "Private until you confirm", offerStarting: "Opening your private note…",
    title: "Draft — not submitted", start: "Start a symptom draft", intro: "Your answers here remain private until you confirm. Your initial Nora message remains in chat history.",
    answerPrompt: "Type or speak your answer below. You can say “not sure” or “skip”.",
    suggestion: "From your message", useSuggestion: "Use this answer", detailEntry: "Enter detailed fields instead",
    listen: "Listen", reviewFirst: "Review the summary, then use the confirmation controls to share. A spoken reply cannot submit it.",
    productReported: "Products reported by you — unverified; not added to your medication list",
    recordSource: "Approved record source", excerptSource: "Source document", pendingAnswer: "Your answer — not yet verified as saved",
    editReply: "Edit this response", existingDraft: "You have an unfinished draft in this conversation. Continue or cancel it before starting another.",
    urgentReview: "Your high-severity answer has been queued for care-team review. This does not mean someone has read it. Messages are not continuously monitored.",
    loading: "Loading your draft…", unavailable: "Guided intake is unavailable. Reload the saved state to check any prior action.",
    error: "We could not verify this action. Reload the saved state before retrying.", reload: "Reload saved state", retry: "Retry the same action",
    save: "Save answer", unknown: "I don’t know", declined: "Prefer not to answer", edit: "Edit", review: "Review before sharing", cancel: "Cancel draft",
    confirm: "Confirm and share with my care team", consent: "I reviewed this preview and want to share it with my care team.",
    reported: "What you reported", context: "Relevant information from your record", summary: "Summary for your care team", emptyContext: "No relevant record context was used.",
    saved: "Report saved for care-team review", cancelled: "Draft cancelled. Your chat history was not deleted.",
    interrupted: "Intake interrupted for safety", pending: "The safety save could not be verified.",
    // UX-007 wording (timezone, fallback, recordDetail, factLabels): es-MX drafts pending LOC-001 review.
    timezone: "Times use", fallback: "Your saved time zone is unavailable. Times are shown in UTC.", progress: "Questions resolved", value: "Your answer",
    recordDetail: "Record detail",
    factFieldLabels: { name: "Name", test_name: "Test", amount: "Amount", value: "Result", unit: "Unit", reference_range: "Report range", flag: "Report flag", observed_at: "Date measured", dose: "Dose", dosage: "Dose", frequency: "How often", route: "How taken", instructions: "Instructions", description: "Description", status: "Status", start_date: "Start date", end_date: "End date", allergen: "Allergen", reaction: "Reaction", severity: "Severity", notes: "Notes", systolic: "Systolic pressure", diastolic: "Diastolic pressure" } as Record<string, string>,
    factLabels: { medication: "Medicine", dose: "Dose", allergy: "Allergy", condition: "Condition", lab_result: "Test result", vital_sign: "Measurement", immunization: "Vaccine", procedure: "Procedure", appointment: "Appointment", instruction: "Instruction", obligation: "Instruction" } as Record<string, string>,
    yes: "Yes", no: "No", productConcern: "I am concerned about a medicine or other product", name: "Product name", strength: "Strength", dose: "Dose", route: "Route",
    indication: "Reason for use", startDate: "Started (your words)", stop: "Stopped (your words)", change: "Changed (your words)",
    states: { answered: "Answered", unknown: "Unknown", declined: "Declined", not_asked: "Not asked", not_applicable: "Not applicable" },
};
const es: typeof en = {
    offerPrompt: "¿Quieres que lo anote para tu equipo de atención? Te haré unas preguntas rápidas aquí.", offerYes: "Sí, hagámoslo", offerNo: "Ahora no",
    privateTag: "Privado hasta que confirmes", offerStarting: "Abriendo tu nota privada…",
    title: "Borrador — no enviado", start: "Iniciar un borrador de síntomas", intro: "Tus respuestas aquí son privadas hasta que confirmes. Tu mensaje inicial a Nora permanece en el historial del chat.",
    answerPrompt: "Escribe o di tu respuesta abajo. Puedes decir “no sé” o “prefiero no responder”.",
    suggestion: "De tu mensaje", useSuggestion: "Usar esta respuesta", detailEntry: "Ingresar campos detallados",
    listen: "Escuchar", reviewFirst: "Revisa el resumen y usa los controles de confirmación para compartirlo. Una respuesta hablada no lo envía.",
    productReported: "Productos reportados por ti — sin verificar; no se agregaron a tu lista de medicamentos",
    recordSource: "Fuente aprobada del expediente", excerptSource: "Documento fuente", pendingAnswer: "Tu respuesta — aún no confirmamos que se guardó",
    editReply: "Editar esta respuesta", existingDraft: "Tienes un borrador sin terminar en esta conversación. Continúalo o cancélalo antes de iniciar otro.",
    urgentReview: "Tu respuesta de alta intensidad está en espera de revisión por tu equipo de atención. Esto no significa que alguien la haya leído. Los mensajes no se supervisan continuamente.",
    loading: "Cargando tu borrador…", unavailable: "La captura guiada no está disponible. Vuelve a cargar el estado guardado para verificar una acción anterior.",
    error: "No pudimos verificar esta acción. Vuelve a cargar el estado guardado antes de reintentar.", reload: "Volver a cargar el estado guardado", retry: "Reintentar la misma acción",
    save: "Guardar respuesta", unknown: "No sé", declined: "Prefiero no responder", edit: "Editar", review: "Revisar antes de compartir", cancel: "Cancelar borrador",
    confirm: "Confirmar y compartir con mi equipo clínico", consent: "Revisé esta vista previa y quiero compartirla con mi equipo clínico.",
    reported: "Lo que reportaste", context: "Información relevante de tu expediente", summary: "Resumen para tu equipo clínico", emptyContext: "No se usó información relevante del expediente.",
    saved: "Reporte guardado para revisión del equipo clínico", cancelled: "Borrador cancelado. No se eliminó tu historial del chat.",
    interrupted: "Captura interrumpida por seguridad", pending: "No se pudo verificar el guardado de seguridad.",
    timezone: "Los horarios usan", fallback: "Tu zona horaria guardada no está disponible. Los horarios se muestran en UTC.", progress: "Preguntas resueltas", value: "Tu respuesta",
    recordDetail: "Dato del expediente",
    factFieldLabels: { name: "Nombre", test_name: "Prueba", amount: "Cantidad", value: "Resultado", unit: "Unidad", reference_range: "Rango del informe", flag: "Marca del informe", observed_at: "Fecha de medición", dose: "Dosis", dosage: "Dosis", frequency: "Frecuencia", route: "Vía de administración", instructions: "Indicaciones", description: "Descripción", status: "Estado", start_date: "Fecha de inicio", end_date: "Fecha de término", allergen: "Alérgeno", reaction: "Reacción", severity: "Intensidad", notes: "Notas", systolic: "Presión sistólica", diastolic: "Presión diastólica" },
    factLabels: { medication: "Medicamento", dose: "Dosis", allergy: "Alergia", condition: "Condición", lab_result: "Resultado de prueba", vital_sign: "Medición", immunization: "Vacuna", procedure: "Procedimiento", appointment: "Cita", instruction: "Indicación", obligation: "Indicación" },
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
        ? "El borrador cambió. Vuelve a cargar el estado guardado y revisa una nueva vista previa."
        : "The draft changed. Reload the saved state and review a new preview.";
    if (code === "INTAKE_TERMINAL") return es ? "Esta captura ya terminó. Vuelve a cargar el estado guardado." : "This intake has ended. Reload the saved state.";
    if (code === "INTAKE_ANSWER_INVALID") return es ? "Revisa tu respuesta e intenta de nuevo." : "Check your answer and try again.";
    if (code === "INTAKE_REPLY_AMBIGUOUS") return es ? "No pude interpretar esa respuesta. Di un número del 1 al 10 para intensidad, o el nombre del producto si corresponde. También puedes decir no sé o prefiero no responder." : "I could not interpret that answer. Use a number from 1 to 10 for severity, or name the product when asked. You can also say not sure or skip.";
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

const yes = new Set(["yes", "yeah", "yep", "sure", "ok", "okay", "yes please", "please", "yes lets do it", "lets do it", "sure lets do it",
    "si", "claro", "vale", "por favor", "si por favor", "si hagamoslo", "hagamoslo", "adelante"]);
const no = new Set(["no", "nope", "not now", "no thanks", "no thank you", "later", "ahora no", "no gracias", "por ahora no", "no por ahora"]);
function normalizeReply(text: string) {
    return text.toLocaleLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/['’]/g, "").replace(/[^a-z0-9\s]/g, " ").replace(/\s+/g, " ").trim();
}
/** A short typed or spoken answer to the symptom-note offer; anything longer is an ordinary message. */
export function offerAnswer(text: string): "yes" | "no" | null {
    const normalized = normalizeReply(text);
    return yes.has(normalized) ? "yes" : no.has(normalized) ? "no" : null;
}
