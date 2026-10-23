import { resolveLocaleResource, type Locale, type LocaleResourceMap } from "@/types";

// Sources-line wording is a draft pending LOC-001 bilingual approval; it is not approved copy.
const en = {
    summary: "Sources",
    loading: "Loading sources…",
    failed: "Sources could not be loaded. Close and open to try again.",
    page: (pages: number[]) => (pages.length === 1 ? `page ${pages[0]}` : `pages ${pages.join(", ")}`),
    record: "Your health record in this app",
    untitled: "Document",
};

const esMX: typeof en = {
    summary: "Fuentes",
    loading: "Cargando fuentes…",
    failed: "No se pudieron cargar las fuentes. Cierra y vuelve a abrir para intentarlo otra vez.",
    page: (pages: number[]) => (pages.length === 1 ? `página ${pages[0]}` : `páginas ${pages.join(", ")}`),
    record: "Tu expediente de salud en esta app",
    untitled: "Documento",
};

const resources: LocaleResourceMap<typeof en> = { default: en, "en-US": en, "es-MX": esMX };

export function getReplySourcesCopy(locale: Locale) {
    return resolveLocaleResource(locale, resources);
}
