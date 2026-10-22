import { normalizeLocale, resolveLocaleResource, type Locale, type LocaleResourceMap } from "@/types";

/**
 * PLAN-002 patient wording: care-team owners, the Today filter, the upload picker and
 * condition privacy. Every es-MX string here is a DRAFT pending bilingual review
 * (LOC-001); the list is kept in `.agent/specs/plan-002-care-plans-per-care-team.md`
 * and none of it may be marked approved before that review.
 */
const english = {
    locale: "en-US" as Locale,
    and: "and",
    // Today / plan details
    filterLabel: "Filter by care team",
    filterAll: "All",
    filterUnowned: "No longer on your care team",
    filterEmpty: "Nothing for this care team today.",
    filterEmptyAction: "Show all",
    unownedNotice: (name: string | null) =>
        name
            ? `Prescribed by ${name}, no longer on your care team. Ask your care team before changing it.`
            : "Prescribed by a clinician who is no longer on your care team. Ask your care team before changing it.",
    contactClinicTitle: "Contact your clinic",
    contactClinicBody:
        "Some of your activities were prescribed by a clinician who is no longer on your care team, and you have no active care team right now. Please contact your clinic before changing any of them. Your reminders continue.",
    planGroupLabel: (owner: string) => `Care plan from ${owner}`,
    planGroupVersion: (version: number, date: string | null) => (date ? `Version ${version} · approved ${date}` : `Version ${version}`),
    // Upload routing
    uploadTitle: "Which care team is this for?",
    uploadHelp: "The care team you choose will review this document.",
    uploadFile: (name: string) => `File: ${name}`,
    uploadNotSure: "Not sure",
    uploadNotSureHint: "Your care teams will decide who reviews it.",
    uploadSingleHint: "This document will go to your care team below.",
    uploadRequired: "Choose a care team, or “Not sure”, to continue.",
    uploadConfirm: "Upload document",
    uploadCancel: "Cancel",
    uploadLoading: "Checking your care teams…",
    uploadOptionsError: "We could not load your care teams. Try again.",
    uploadRetry: "Try again",
    // Condition privacy
    conditionsTitle: "Health conditions",
    conditionsIntro: "Only the care team that recorded a private condition sees it. Medications and allergies are always shared for your safety.",
    conditionsLoadError: "Your health conditions could not be loaded.",
    conditionsRetry: "Try again",
    keepPrivate: "Keep private",
    keepPrivateFor: (name: string) => `Keep ${name} private`,
    keepPrivateHelp: "Only the care team that recorded this sees it. Medications and allergies are always shared for your safety.",
    recordedBy: (owner: string) => `Recorded by ${owner}`,
    privateConfirmTitle: "Keep this condition private?",
    privateConfirmBody: "Only the care team that recorded it will see it. Your other care teams will see that some conditions are kept private, but not which ones.",
    sharedConfirmTitle: "Share this condition again?",
    sharedConfirmBody: "Your other care teams will be able to see it. Medications and allergies are always shared for your safety.",
    confirm: "Confirm",
    cancel: "Cancel",
    saving: "Saving…",
    privacySaved: (name: string, privateNow: boolean) => (privateNow ? `${name} is now private.` : `${name} is shared with your care teams.`),
    privacyError: "We could not save that change. Your setting is back to what it was.",
    close: "Close",
};

export type CareTeamCopy = typeof english;

const spanish: CareTeamCopy = {
    locale: "es-MX",
    and: "y",
    filterLabel: "Filtrar por equipo de atención",
    filterAll: "Todas",
    filterUnowned: "Ya no está en tu equipo de atención",
    filterEmpty: "No hay nada de este equipo de atención hoy.",
    filterEmptyAction: "Mostrar todas",
    unownedNotice: (name) =>
        name
            ? `Recetado por ${name}, que ya no está en tu equipo de atención. Consulta con tu equipo de atención antes de cambiarlo.`
            : "Recetado por un clínico que ya no está en tu equipo de atención. Consulta con tu equipo de atención antes de cambiarlo.",
    contactClinicTitle: "Comunícate con tu clínica",
    contactClinicBody:
        "Algunas de tus actividades fueron recetadas por un clínico que ya no está en tu equipo de atención, y ahora no tienes un equipo de atención activo. Comunícate con tu clínica antes de cambiar cualquiera de ellas. Tus recordatorios continúan.",
    planGroupLabel: (owner) => `Plan de atención de ${owner}`,
    planGroupVersion: (version, date) => (date ? `Versión ${version} · aprobado el ${date}` : `Versión ${version}`),
    uploadTitle: "¿Para qué equipo de atención es esto?",
    uploadHelp: "El equipo de atención que elijas revisará este documento.",
    uploadFile: (name) => `Archivo: ${name}`,
    uploadNotSure: "No estoy seguro",
    uploadNotSureHint: "Tus equipos de atención decidirán quién lo revisa.",
    uploadSingleHint: "Este documento irá a tu equipo de atención que aparece abajo.",
    uploadRequired: "Elige un equipo de atención, o “No estoy seguro”, para continuar.",
    uploadConfirm: "Subir documento",
    uploadCancel: "Cancelar",
    uploadLoading: "Revisando tus equipos de atención…",
    uploadOptionsError: "No pudimos cargar tus equipos de atención. Intenta de nuevo.",
    uploadRetry: "Intentar de nuevo",
    conditionsTitle: "Condiciones de salud",
    conditionsIntro: "Solo el equipo de atención que registró una condición privada la ve. Los medicamentos y las alergias siempre se comparten por tu seguridad.",
    conditionsLoadError: "No se pudieron cargar tus condiciones de salud.",
    conditionsRetry: "Intentar de nuevo",
    keepPrivate: "Mantener privada",
    keepPrivateFor: (name) => `Mantener privada: ${name}`,
    keepPrivateHelp: "Solo el equipo de atención que la registró la ve. Los medicamentos y las alergias siempre se comparten por tu seguridad.",
    recordedBy: (owner) => `Registrada por ${owner}`,
    privateConfirmTitle: "¿Mantener esta condición privada?",
    privateConfirmBody: "Solo el equipo de atención que la registró la verá. Tus otros equipos de atención verán que algunas condiciones se mantienen privadas, pero no cuáles.",
    sharedConfirmTitle: "¿Volver a compartir esta condición?",
    sharedConfirmBody: "Tus otros equipos de atención podrán verla. Los medicamentos y las alergias siempre se comparten por tu seguridad.",
    confirm: "Confirmar",
    cancel: "Cancelar",
    saving: "Guardando…",
    privacySaved: (name, privateNow) => (privateNow ? `${name} ahora es privada.` : `${name} se comparte con tus equipos de atención.`),
    privacyError: "No pudimos guardar ese cambio. Tu ajuste volvió a como estaba.",
    close: "Cerrar",
};

const resources: LocaleResourceMap<CareTeamCopy> = { default: english, "en-US": english, "es-MX": spanish };

export function getCareTeamCopy(locale?: Locale): CareTeamCopy {
    return resolveLocaleResource(normalizeLocale(locale), resources);
}

/** The owner parts the API sends; the portal composes the label so each locale joins its own way. */
export interface OwnerParts {
    specialty: string | null;
    clinician_name: string | null;
    clinic_name: string | null;
}

/** "Cardiology · Dr. Elena Park · Cedar Grove"; missing parts are skipped, never replaced by a guess. */
export function ownerLabel(owner: OwnerParts): string {
    return [owner.specialty, owner.clinician_name, owner.clinic_name].filter((part): part is string => Boolean(part && part.trim())).join(" · ");
}

/** "Cardiology · Dr. Park and Orthopaedics · Dr. Lee": a combined entry names every owner. */
export function combinedOwnerLabel(owners: OwnerParts[], copy: CareTeamCopy): string {
    return owners.map((owner) => ownerLabel(owner)).filter(Boolean).join(` ${copy.and} `);
}
