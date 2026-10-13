import type { DocumentResult } from "@/services/documents";

/**
 * Results of one document, attached by the server under a Nora reply that cited it.
 *
 * Every value comes from the facts extracted from (and checked against) that document,
 * never from the reply text.
 */
export interface ChatDocumentResultsAttachment {
    type: "document_results";
    documentId: string;
    fileName: string | null;
    title: Partial<Record<"en-US" | "es-MX", string>>;
    results: DocumentResult[];
}

export type ChatAttachment = ChatDocumentResultsAttachment;
