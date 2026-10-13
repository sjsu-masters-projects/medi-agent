/** Recovery credentials stay in memory and never enter the normal portal session. */
export function readRecoveryTokens(hash: string) {
    const values = new URLSearchParams(hash.replace(/^#/, ""));
    if (values.get("type") !== "recovery" || values.has("error")) return null;
    const access_token = values.get("access_token");
    const refresh_token = values.get("refresh_token");
    return access_token && refresh_token ? { access_token, refresh_token } : null;
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
        invalid: "This link is unavailable or has expired. Request a new one.",
        unavailable: "Password recovery is not configured. Contact the project administrator.",
        success: "Your password was updated. Sign in with your new password.",
        back: "Back to sign in", retry: "Request another link",
    };
}
