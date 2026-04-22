import {
    DocumentType,
    isSpanishLocale,
    normalizeLocale,
    type Locale,
    type DocumentType as DocumentTypeValue,
} from "@/types";

const CHAT_DOCUMENT_CONTEXT_PREFIX = "patient-portal.chat.document-context";
const DOCUMENT_TYPES = new Set<DocumentTypeValue>(Object.values(DocumentType));

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

export function buildDocumentChatHref(documentId: string): string {
    return `/chat?document=${encodeURIComponent(documentId)}`;
}

export function buildSuggestedDocumentQuestion(
    context: Pick<
        PendingChatDocumentContext,
        "documentName" | "documentType" | "provider" | "preferredLanguage"
    >,
): string {
    const descriptor = context.provider
        ? `${context.documentType.replaceAll("_", " ")} from ${context.provider}`
        : context.documentType.replaceAll("_", " ");

    if (isSpanishLocale(context.preferredLanguage)) {
        return `Ayúdame a entender mi ${descriptor} llamado "${context.documentName}" y dime qué debo preguntar a mi médico.`;
    }

    return `Help me understand my ${descriptor} called "${context.documentName}" and what questions I should ask my doctor.`;
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
            preferredLanguage: normalizeLocale(parsed.preferredLanguage),
        };
    } catch {
        return null;
    }
}
