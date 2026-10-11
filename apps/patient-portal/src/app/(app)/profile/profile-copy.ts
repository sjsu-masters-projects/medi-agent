import { Gender, type Locale } from "@/types";

const en = {
    title: "Profile",
    subtitle: "Manage your account and linked clinics.",
    loadTitle: "Unable to load your profile",
    loadError: "We couldn’t load your account. Please try again.",
    retry: "Try again",
    onboarding:
        "No active care team is linked yet. Open the clinic connection sheet to enter your clinic’s invite code.",
    patientAccount: "Patient account",
    details: "Profile details",
    personal: "Personal information",
    editing: "Editing",
    editProfile: "Edit profile",
    edit: "Edit",
    firstName: "First name",
    lastName: "Last name",
    language: "Preferred language",
    languageHelp:
        "Saving this changes the app language. Your care plan and Today list switch too, because your care team approves them in English and Spanish.",
    gender: "Gender",
    optional: "(optional)",
    unspecified: "Not specified",
    dob: "Date of birth",
    dobLocked: "Your date of birth links your health records, so only your care team can change it. Message them if it is wrong.",
    timezone: "Timezone",
    save: "Save changes",
    saving: "Saving...",
    cancel: "Cancel",
    saved: "Profile updated successfully.",
    saveError:
        "We couldn’t confirm your changes were saved. Refresh to check your profile before trying again.",
    reminders: "Reminders",
    reminderTitle: "Medication and task reminder times",
    reminderHelp: "Choose the exact times and days you want reminders sent.",
    patientControlled: "Patient controlled",
    manageReminders: "Manage reminders",
    connected: "Connected clinics",
    teams: "Care teams",
    active: "Linked",
    inactive: "Inactive",
    transferred: "Transferred",
    unknownStatus: "Status unavailable",
    teamFallback: "Care team",
    noTeams: "No care teams linked yet",
    noTeamsHelp:
        "Add a clinic invite code to connect your account with a care team.",
    messages: "Message your care team",
    messageHelp:
        "Choose a linked clinician in Chat to send a human message. Messages are not continuously monitored. Call 911 for an emergency.",
    joinAnother: "Join another clinic",
    connectClinic: "Connect your clinic",
    addTeam: "Add care team access",
    joinHelp:
        "Enter the code your clinic shared with you to link its care team to your account.",
    inviteCode: "Clinic invite code",
    inviteHelp: "Use the code provided by your clinic.",
    enterCode: "Enter a clinic invite code to continue.",
    joining: "Joining clinic...",
    join: "Join clinic",
    joined: "Clinic linked successfully. Your new care team is now available.",
    joinError:
        "We couldn’t confirm the clinic was linked. Refresh to check your care team before trying again.",
    invalidCode: "Invalid or expired invite code",
    account: "Account",
    signOutTitle: "Sign out safely",
    signOutHelp:
        "Use this if you are on a shared phone or finished reviewing your care plan.",
    signOut: "Sign out",
};

const es: typeof en = {
    title: "Perfil",
    subtitle: "Administra tu cuenta y las clínicas vinculadas.",
    loadTitle: "No se pudo cargar tu perfil",
    loadError: "No pudimos cargar tu cuenta. Inténtalo de nuevo.",
    retry: "Intentar de nuevo",
    onboarding:
        "Aún no tienes un equipo de atención activo vinculado. Abre el formulario para conectar una clínica e ingresar su código de invitación.",
    patientAccount: "Cuenta del paciente",
    details: "Detalles del perfil",
    personal: "Información personal",
    editing: "Editando",
    editProfile: "Editar perfil",
    edit: "Editar",
    firstName: "Nombre",
    lastName: "Apellidos",
    language: "Idioma preferido",
    languageHelp:
        "Al guardarlo cambia el idioma de la aplicación. Tu plan de atención y tus actividades de hoy también cambian, porque tu equipo de atención los aprueba en inglés y en español.",
    gender: "Género",
    optional: "(opcional)",
    unspecified: "Sin especificar",
    dob: "Fecha de nacimiento",
    dobLocked: "Tu fecha de nacimiento vincula tus expedientes médicos, por eso solo tu equipo de atención puede cambiarla. Escríbeles si no es correcta.",
    timezone: "Zona horaria",
    save: "Guardar cambios",
    saving: "Guardando...",
    cancel: "Cancelar",
    saved: "Tu perfil se actualizó correctamente.",
    saveError:
        "No pudimos confirmar que se guardaron tus cambios. Actualiza la página para revisar tu perfil antes de volver a intentarlo.",
    reminders: "Recordatorios",
    reminderTitle: "Horarios de recordatorios de medicamentos y tareas",
    reminderHelp:
        "Elige las horas y los días en que deseas recibir recordatorios.",
    patientControlled: "Tú eliges",
    manageReminders: "Administrar recordatorios",
    connected: "Clínicas vinculadas",
    teams: "Equipos de atención",
    active: "Vinculado",
    inactive: "Inactivo",
    transferred: "Transferido",
    unknownStatus: "Estado no disponible",
    teamFallback: "Equipo de atención",
    noTeams: "Aún no hay equipos de atención vinculados",
    noTeamsHelp:
        "Agrega el código de una clínica para vincular tu cuenta con un equipo de atención.",
    messages: "Enviar mensaje a tu equipo",
    messageHelp:
        "Elige un profesional vinculado en Chat para enviar un mensaje a una persona. Los mensajes no se monitorean continuamente. En una emergencia, llama al 911.",
    joinAnother: "Vincular otra clínica",
    connectClinic: "Conectar tu clínica",
    addTeam: "Agregar acceso a un equipo",
    joinHelp:
        "Ingresa el código que te compartió tu clínica para vincular su equipo de atención con tu cuenta.",
    inviteCode: "Código de invitación de la clínica",
    inviteHelp: "Usa el código que te proporcionó tu clínica.",
    enterCode: "Ingresa un código de invitación de la clínica para continuar.",
    joining: "Vinculando clínica...",
    join: "Vincular clínica",
    joined: "La clínica se vinculó correctamente. Tu nuevo equipo de atención ya está disponible.",
    joinError:
        "No pudimos confirmar que se vinculó la clínica. Actualiza la página para revisar tu equipo antes de volver a intentarlo.",
    invalidCode: "El código de invitación no es válido o ya venció",
    account: "Cuenta",
    signOutTitle: "Cerrar sesión de forma segura",
    signOutHelp:
        "Usa esta opción si compartes tu teléfono o ya terminaste de revisar tu plan de atención.",
    signOut: "Cerrar sesión",
};

export function profileCopy(locale: Locale) {
    return locale === "es-MX" ? es : en;
}

export function profileGenderLabels(locale: Locale): Record<string, string> {
    return {
        [Gender.FEMALE]: locale === "es-MX" ? "Femenino" : "Female",
        [Gender.MALE]: locale === "es-MX" ? "Masculino" : "Male",
        [Gender.OTHER]: locale === "es-MX" ? "Otro" : "Other",
        [Gender.PREFER_NOT_TO_SAY]:
            locale === "es-MX" ? "Prefiero no decirlo" : "Prefer not to say",
    };
}
