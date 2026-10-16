export const emailPreferenceCopy = {
  "en-US": {
    title: "Email notices",
    statusVerified: "Verified", statusUnverified: "Not verified", statusSynthetic: "Email unavailable",
    synthetic: "Demo accounts can't receive email. In-app notifications stay on.",
    unverifiedHelp: "Verify this address to turn on email notices.",
    codeHelp: "Enter the 6-digit code we sent.",
    recoveryNote: "These choices don't affect account recovery emails.",
    loading: "Loading email notices…", unavailable: "Email notices are unavailable. Please try again.",
    verify: "Send code", resend: "Send a new code",
    queued: "Code requested. Check your inbox; it may take a few minutes.",
    wait: "Please wait a minute before requesting another code.",
    limit: "You have requested several codes today. Try again tomorrow, or use the newest code you received.",
    notAvailable: "Email notices aren't available yet. In-app notifications still work.",
    code: "Six-digit code", confirm: "Verify",
    invalid: "The code is invalid or expired. Request a new code.", verified: "Email verified", save: "Save notices",
    saved: "Email notices saved.", retry: "Try again", busy: "Please wait…",
    messages: "Unread care-team messages", appointments: "Appointment offers and updates",
    care_plans: "Approved care-plan updates", records: "Records requiring my attention", reviews: "Shared review work",
    privacy: "No health details in emails. Replies aren't read.",
  },
  "es-MX": {
    title: "Avisos por correo",
    statusVerified: "Verificado", statusUnverified: "Sin verificar", statusSynthetic: "Correo no disponible",
    synthetic: "Las cuentas de demostración no reciben correos. Las notificaciones en la app siguen activas.",
    unverifiedHelp: "Verifica este correo para activar los avisos.",
    codeHelp: "Escribe el código de 6 dígitos que te enviamos.",
    recoveryNote: "Estas opciones no afectan los correos de recuperación de cuenta.",
    loading: "Cargando avisos por correo…", unavailable: "Los avisos por correo no están disponibles. Inténtalo de nuevo.",
    verify: "Enviar código", resend: "Enviar otro código",
    queued: "Código solicitado. Revisa tu correo; puede tardar unos minutos.",
    wait: "Espera un minuto antes de solicitar otro código.",
    limit: "Ya solicitaste varios códigos hoy. Inténtalo mañana o usa el código más reciente que recibiste.",
    notAvailable: "Los avisos por correo aún no están disponibles. Las notificaciones en la app siguen funcionando.",
    code: "Código de seis dígitos", confirm: "Verificar",
    invalid: "El código no es válido o ya caducó. Solicita uno nuevo.", verified: "Correo verificado", save: "Guardar avisos",
    saved: "Avisos por correo guardados.", retry: "Intentar de nuevo", busy: "Espera…",
    messages: "Mensajes no leídos del equipo de atención", appointments: "Propuestas y cambios de citas",
    care_plans: "Actualizaciones aprobadas del plan", records: "Registros que requieren mi atención", reviews: "Revisiones pendientes",
    privacy: "Los correos no incluyen datos de salud. Las respuestas no se leen.",
  },
} as const;
export type EmailPreferenceKey = "messages" | "appointments" | "care_plans" | "records" | "reviews";
export interface EmailPreferenceState {
  email: string; verified: boolean; synthetic: boolean;
  preferences: Record<EmailPreferenceKey, boolean>;
  /** False until the server's email setup is installed. */
  available?: boolean;
}
export type VerificationRequestStatus = "queued" | "wait" | "limit" | "synthetic";

export function verificationNotice(
  copy: { queued: string; wait: string; limit: string; synthetic: string },
  status: string,
): string {
  return status === "wait" ? copy.wait : status === "limit" ? copy.limit : status === "synthetic" ? copy.synthetic : copy.queued;
}
