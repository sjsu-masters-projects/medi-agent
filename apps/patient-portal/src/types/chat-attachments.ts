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

/**
 * Set by the server when the patient's own message describes a reportable, non-emergency
 * symptom or possible side effect. It only asks; nothing is drafted until the patient says yes.
 */
export interface ChatSymptomOfferAttachment {
    type: "symptom_intake_offer";
    /** The patient's message the private note would be about. */
    sourceMessageId: string;
}

export type ChatAttachment = ChatDocumentResultsAttachment | ChatSymptomOfferAttachment;
