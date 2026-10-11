export const emailPreferenceCopy = {
  "en-US": {
    title: "Email preferences", help: "Optional notices are separate from in-app notifications. Verify your account mailbox before enabling them.",
    synthetic: "This demo login address cannot receive email. In-app notifications still work.",
    loading: "Loading email preferences…", unavailable: "Email preferences are unavailable. Please try again.",
    verify: "Send verification code", queued: "Verification requested. Check your inbox; delivery may take a few minutes.",
    wait: "Please wait a minute before requesting another code.", code: "Six-digit code", confirm: "Verify email",
    invalid: "The code is invalid or expired. Request a new code.", verified: "Email verified", save: "Save email preferences",
    saved: "Email preferences saved.", retry: "Try again", busy: "Please wait…",
    messages: "Unread care-team messages", appointments: "Appointment offers and updates",
    care_plans: "Approved care-plan updates", records: "Records requiring my attention", reviews: "Shared review work",
    privacy: "Emails omit health details. Replies to email are not monitored. Account recovery is not disabled by these preferences.",
  },
  "es-MX": {
    title: "Preferencias de correo", help: "Los avisos opcionales son independientes de las notificaciones en la app. Verifica el correo de tu cuenta antes de activarlos.",
    synthetic: "Esta dirección de demostración no puede recibir correos. Las notificaciones en la app siguen funcionando.",
    loading: "Cargando preferencias de correo…", unavailable: "Las preferencias de correo no están disponibles. Inténtalo de nuevo.",
    verify: "Enviar código de verificación", queued: "Se solicitó la verificación. Revisa tu correo; puede tardar unos minutos.",
    wait: "Espera un minuto antes de solicitar otro código.", code: "Código de seis dígitos", confirm: "Verificar correo",
    invalid: "El código no es válido o ya caducó. Solicita uno nuevo.", verified: "Correo verificado", save: "Guardar preferencias de correo",
    saved: "Preferencias de correo guardadas.", retry: "Intentar de nuevo", busy: "Espera…",
    messages: "Mensajes no leídos del equipo de atención", appointments: "Propuestas y cambios de citas",
    care_plans: "Actualizaciones aprobadas del plan", records: "Registros que requieren mi atención", reviews: "Revisiones pendientes",
    privacy: "Los correos no incluyen información de salud. Las respuestas por correo no se supervisan. Estas preferencias no desactivan la recuperación de la cuenta.",
  },
} as const;
export type EmailPreferenceKey = "messages" | "appointments" | "care_plans" | "records" | "reviews";
export interface EmailPreferenceState {
  email: string; verified: boolean; synthetic: boolean;
  preferences: Record<EmailPreferenceKey, boolean>;
}
