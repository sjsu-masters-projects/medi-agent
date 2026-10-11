import {
    DocumentType,
    getDocumentTypeLabel,
    normalizeLocale,
    resolveLocaleResource,
    type Locale,
    type LocaleResourceMap,
    type DocumentType as DocumentTypeValue,
} from "@/types";

const CHAT_DOCUMENT_CONTEXT_PREFIX = "patient-portal.chat.document-context";
const DOCUMENT_TYPES = new Set<DocumentTypeValue>(Object.values(DocumentType));
const DOCUMENT_QUESTION_TEMPLATES: LocaleResourceMap<string> = {
    default: 'Explain my {descriptor} "{documentName}" in simple words, and what I should ask my care team.',
    "en-US": 'Explain my {descriptor} "{documentName}" in simple words, and what I should ask my care team.',
    "es-MX": 'Explícame con palabras sencillas mi {descriptor} "{documentName}" y qué debo preguntarle a mi equipo de atención.',
};

export interface PendingChatDocumentContext {
    documentId: string;
    documentName: string;
    documentType: DocumentTypeValue;
    provider?: string;
    summary?: string;
    preferredLanguage: Locale;
    suggestedQuestion: string;
}

function getSessionStorage(): Storage | null {
    if (typeof window === "undefined") {
        return null;
    }

    return window.sessionStorage;
}

function buildStorageKey(documentId: string): string {
    return `${CHAT_DOCUMENT_CONTEXT_PREFIX}.${documentId}`;
}

function isDocumentType(value: unknown): value is DocumentTypeValue {
    return typeof value === "string" && DOCUMENT_TYPES.has(value as DocumentTypeValue);
}

export function normalizeChatDocumentType(value: unknown): DocumentTypeValue {
    return isDocumentType(value) ? value : DocumentType.OTHER;
}

export function buildDocumentChatHref(documentId: string): string {
    return `/chat?document=${encodeURIComponent(documentId)}`;
}

export function buildSuggestedDocumentQuestion(
    context: Pick<
        PendingChatDocumentContext,
        "documentName" | "documentType" | "provider" | "preferredLanguage"
    >,
): string {
    // The source label is shown on the context card; splicing it into the sentence put
    // English ("from Care team") into Spanish questions.
    const descriptor = getDocumentTypeLabel(context.documentType, context.preferredLanguage).toLocaleLowerCase(context.preferredLanguage);
    const template = resolveLocaleResource(
        context.preferredLanguage,
        DOCUMENT_QUESTION_TEMPLATES,
    );
    return template
        .replace("{descriptor}", descriptor)
        .replace("{documentName}", context.documentName);
}

export function storePendingChatDocumentContext(
    context: PendingChatDocumentContext,
): void {
    getSessionStorage()?.setItem(buildStorageKey(context.documentId), JSON.stringify(context));
}

export function consumePendingChatDocumentContext(
    documentId: string | null | undefined,
): PendingChatDocumentContext | null {
    if (!documentId) {
        return null;
    }

    const storage = getSessionStorage();
    const raw = storage?.getItem(buildStorageKey(documentId));
    if (!raw) {
        return null;
    }

    storage?.removeItem(buildStorageKey(documentId));

    try {
        const parsed = JSON.parse(raw) as PendingChatDocumentContext;
        if (
            typeof parsed.documentId !== "string"
            || typeof parsed.documentName !== "string"
            || !isDocumentType(parsed.documentType)
            || typeof parsed.preferredLanguage !== "string"
            || typeof parsed.suggestedQuestion !== "string"
        ) {
            return null;
        }
        return {
            ...parsed,
            documentType: normalizeChatDocumentType(parsed.documentType),
            preferredLanguage: normalizeLocale(parsed.preferredLanguage),
        };
    } catch {
        return null;
    }
}
