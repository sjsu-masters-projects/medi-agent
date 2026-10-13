/** Recovery credentials stay in memory and never enter the normal portal session. */
export function readRecoveryTokens(hash: string) {
    const values = new URLSearchParams(hash.replace(/^#/, ""));
    if (values.get("type") !== "recovery" || values.has("error")) return null;
    const access_token = values.get("access_token");
    const refresh_token = values.get("refresh_token");
    return access_token && refresh_token ? { access_token, refresh_token } : null;
}

/**
 * Scanner-safe links carry a one-time `token_hash` in the query. Opening the page
 * must not redeem it (mail scanners open links too); only an explicit click does.
 */
export function readRecoveryTokenHash(search: string) {
    const values = new URLSearchParams(search);
    const token_hash = values.get("token_hash");
    return values.get("type") === "recovery" && token_hash ? token_hash : null;
}

/** The query without recovery secrets, keeping `lang` and other harmless values. */
export function withoutRecoveryQuery(search: string) {
    const values = new URLSearchParams(search);
    values.delete("token_hash");
    values.delete("type");
    const rest = values.toString();
    return rest ? `?${rest}` : "";
}

export function recoveryCopy(locale: string) {
    return locale === "es-MX" ? {
        forgot: "¿Olvidaste tu contraseña?",
        intro: "Escribe el correo de tu cuenta para solicitar un enlace de recuperación.",
        email: "Correo electrónico", send: "Solicitar enlace", sending: "Solicitando…",
        sent: "Si existe una cuenta con ese correo, recibirás un enlace. Revisa también el correo no deseado.",
        failure: "No pudimos completar la solicitud. Inténtalo de nuevo.",
        reset: "Crea una nueva contraseña",
        resetIntro: "Usa al menos 8 caracteres. Después, inicia sesión de nuevo.",
        password: "Nueva contraseña", confirm: "Confirmar contraseña",
        mismatch: "Las contraseñas deben coincidir y tener entre 8 y 128 caracteres.",
        save: "Guardar contraseña", saving: "Guardando…", checking: "Verificando enlace…",
        continue: "Continuar para elegir una nueva contraseña",
        invalid: "El enlace no está disponible o venció. Solicita uno nuevo.",
        unavailable: "La recuperación no está configurada. Contacta al administrador del proyecto.",
        success: "Tu contraseña se actualizó. Inicia sesión con tu nueva contraseña.",
        back: "Volver a iniciar sesión", retry: "Solicitar otro enlace",
    } : {
        forgot: "Forgot your password?",
        intro: "Enter your account email to request a recovery link.",
        email: "Email address", send: "Request reset link", sending: "Requesting…",
        sent: "If an account exists for that email, you will receive a link. Check your spam folder too.",
        failure: "We could not complete the request. Please try again.",
        reset: "Choose a new password",
        resetIntro: "Use at least 8 characters. Afterwards, sign in again.",
        password: "New password", confirm: "Confirm password",
        mismatch: "Passwords must match and contain between 8 and 128 characters.",
        save: "Save password", saving: "Saving…", checking: "Checking recovery link…",
        continue: "Continue to choose a new password",
        invalid: "This link is unavailable or has expired. Request a new one.",
        unavailable: "Password recovery is not configured. Contact the project administrator.",
        success: "Your password was updated. Sign in with your new password.",
        back: "Back to sign in", retry: "Request another link",
    };
}
