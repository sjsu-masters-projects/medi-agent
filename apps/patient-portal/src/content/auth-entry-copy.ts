import { normalizeLocale, type Locale } from "@/types";
import { GUEST_LOCALE_STORAGE_KEY, isAuthEntryPath, readLocaleCookie, supportedPatientLocale } from "@/content/patient-locale";

export { GUEST_LOCALE_STORAGE_KEY } from "@/content/patient-locale";

export function getSignupErrorKey(error: unknown): "accountExists" | "failure" {
  if (typeof error !== "object" || error === null || !("status" in error) || error.status !== 422 || !("details" in error)) return "failure";
  const details = error.details;
  if (typeof details !== "object" || details === null || !("error" in details)) return "failure";
  const envelope = details.error;
  if (typeof envelope !== "object" || envelope === null) return "failure";
  // Signup's business validation uses a generic code; match its specific duplicate detail.
  return "code" in envelope && envelope.code === "VALIDATION_ERROR"
    && "message" in envelope && envelope.message === "Signup failed — email is already registered"
    ? "accountExists" : "failure";
}

export function getAuthEntryCopy(locale: Locale) {
  return locale === "es-MX" ? {
    language: "Idioma", welcome: "Bienvenido de nuevo", loginIntro: "Tu espacio para el plan de cuidado de hoy, tus registros y los mensajes de tu equipo clínico.",
    companion: "Tu espacio de cuidado", signInHeading: "Inicia sesión", signInIntro: "Accede a tu cuenta de paciente.", email: "Correo electrónico", password: "Contraseña",
    showPassword: "Mostrar contraseña", hidePassword: "Ocultar contraseña", showConfirm: "Mostrar confirmación de contraseña", hideConfirm: "Ocultar confirmación de contraseña",
    signingIn: "Iniciando sesión…", signIn: "Iniciar sesión", newHere: "¿Primera vez en MediAgent Care?", newIntro: "Recibe recordatorios y novedades de tu equipo clínico.", createOne: "Crear cuenta",
    expired: "Tu sesión expiró. Inicia sesión de nuevo.", unauthorized: "Ya no tienes acceso a este portal. Inicia sesión de nuevo.", loggedOut: "Cerraste sesión.", inactivity: "Cerraste sesión por un periodo de inactividad.", clinicianAccount: "Esta cuenta pertenece a un profesional clínico. Usa el portal clínico.",
    signup: "MediAgent Care", join: "Crea tu cuenta", signupIntro: "Consulta tu plan de cuidado, configura recordatorios y mantente en contacto con tu equipo clínico.", inviteLater: "Después de crear tu cuenta, conecta tu clínica con su código de invitación en el paso 4.",
    firstName: "Nombre", lastName: "Apellido", dateOfBirth: "Fecha de nacimiento", confirmPassword: "Confirmar contraseña", createAccount: "Crear cuenta", creating: "Creando cuenta…", already: "¿Ya tienes una cuenta?", mismatch: "Las contraseñas no coinciden.", wrongSignup: "No se pudo crear una cuenta de paciente.",
    step: "Paso", of: "de", completeProfile: "Completa tu perfil", profileIntro: "Estos datos nos ayudan a personalizar tus recordatorios y conectarte con tu clínica.",
    personal: "Datos personales", aboutYou: "Cuéntanos sobre ti", preferences: "Preferencias", communication: "Elige tus preferencias de comunicación", preferredLanguage: "Idioma preferido", timezone: "Zona horaria", gender: "Género (opcional)",
    preferNot: "Prefiero no decirlo", male: "Masculino", female: "Femenino", other: "Otro", medical: "Información médica", medicalHeading: "Tu clínica revisa tu información médica", medicalIntro: "Después de conectarte con tu clínica, puedes subir registros para revisión en la sección Registros. La configuración no guarda alergias ni padecimientos.",
    joinClinic: "Conectar clínica", connect: "Conecta a tu equipo clínico", invite: "Código de invitación de la clínica", inviteRequiredIntro: "Necesitas este código para terminar la configuración y conectarte con tu equipo clínico.",
    back: "Atrás", next: "Siguiente", saving: "Guardando…", finish: "Terminar configuración", namesRequired: "El nombre y el apellido son obligatorios.", genderInvalid: "Elige una opción de género válida.", inviteRequired: "El código de invitación de la clínica es obligatorio para completar la configuración.",
    failure: "No se pudo completar la solicitud. Revisa tus datos y vuelve a intentarlo.", invalidLogin: "El correo o la contraseña no son correctos. Revísalos e intenta de nuevo.", accountExists: "Ya existe una cuenta con este correo. Intenta iniciar sesión.", inviteInvalid: "No se pudo usar el código de invitación. Confírmalo con tu clínica e intenta de nuevo.",
  } : {
    language: "Language", welcome: "Welcome back", loginIntro: "Your space for today's care plan, records, and messages from your care team.",
    companion: "Your care workspace", signInHeading: "Sign in securely", signInIntro: "Access your patient account.", email: "Email address", password: "Password",
    showPassword: "Show password", hidePassword: "Hide password", showConfirm: "Show confirm password", hideConfirm: "Hide confirm password",
    signingIn: "Signing in...", signIn: "Sign in", newHere: "New to MediAgent Care?", newIntro: "Get reminders and clinician updates.", createOne: "Create one",
    expired: "Your session expired. Please sign in again.", unauthorized: "You no longer have access to this portal. Please sign in again.", loggedOut: "You have been logged out.", inactivity: "You were signed out after a period of inactivity.", clinicianAccount: "This login belongs to a clinician account. Use the clinician portal.",
    signup: "MediAgent Care", join: "Create your account", signupIntro: "See your care plan, manage reminders, and stay in touch with your care team.", inviteLater: "After creating your account, connect your clinic with its invite code in step 4.",
    firstName: "First name", lastName: "Last name", dateOfBirth: "Date of birth", confirmPassword: "Confirm password", createAccount: "Create account", creating: "Creating account...", already: "Already have an account?", mismatch: "Passwords do not match.", wrongSignup: "Signup did not create a patient account.",
    step: "Step", of: "of", completeProfile: "Complete your profile", profileIntro: "These details help personalize reminders and connect you to your clinic.",
    personal: "Personal info", aboutYou: "Tell us about yourself", preferences: "Preferences", communication: "Set your communication basics", preferredLanguage: "Preferred language", timezone: "Timezone", gender: "Gender (optional)",
    preferNot: "Prefer not to say", male: "Male", female: "Female", other: "Other", medical: "Medical info", medicalHeading: "Your clinic reviews your medical information", medicalIntro: "Once connected to your clinic, you can upload records for review in Records. Setup does not save allergies or conditions.",
    joinClinic: "Join clinic", connect: "Connect your care team", invite: "Clinic invite code", inviteRequiredIntro: "This code is required to finish setup and connect your clinic care team.",
    back: "Back", next: "Next", saving: "Saving...", finish: "Finish setup", namesRequired: "First name and last name are required.", genderInvalid: "Please choose a valid gender option.", inviteRequired: "Clinic invite code is required to complete onboarding.",
    failure: "Could not complete the request. Check your details and try again.", invalidLogin: "The email or password is incorrect. Check them and try again.", accountExists: "An account with this email already exists. Try signing in.", inviteInvalid: "Could not use this invite code. Confirm it with your clinic and try again.",
  };
}

export function authEntryLocale(): Locale {
  if (typeof window === "undefined") return "en-US";
  try {
    return (isAuthEntryPath(window.location.pathname) ? supportedPatientLocale(new URLSearchParams(window.location.search).get("lang")) : null) ?? readLocaleCookie()
      ?? normalizeLocale(window.localStorage.getItem(GUEST_LOCALE_STORAGE_KEY) ?? window.navigator.language);
  } catch {
    return normalizeLocale(window.navigator.language);
  }
}
