import { DocumentType, type Document } from "@/types";

export interface DocumentApiRecord {
    id: string;
    patient_id: string;
    uploaded_by: string;
    uploaded_by_role: Document["uploadedByRole"];
    document_type: DocumentType;
    file_name: string;
    file_url: string;
    mime_type: string;
    preview_url?: string | null;
    preview_mime_type?: string | null;
    preview_status?: string | null;
    file_size_bytes: number;
    parsed: boolean;
    ai_summary?: string | null;
    parse_status?: Document["parseStatus"];
    parse_failure_code?: string | null;
    parse_attempts?: number;
    source_clinic?: string | null;
    visibility: Document["visibility"];
    created_at: string;
}

/** Render persisted legacy summaries as text even if an older model used Markdown. */
export function normalizePatientSummary(value: string | null | undefined): string | undefined {
  if (!value) {
    return undefined;
  }

  const normalized = value
    .replaceAll("```", "")
    .replace(/[\*_`]+/g, "")
    .replace(/^\s*#{1,6}\s*/gm, "")
    .split(/\r?\n/)
    .map((line) => line.trim().replace(/\s+/g, " "))
    .filter(Boolean)
    .join("\n\n")
    .trim();
  return normalized || undefined;
}

export function inferDocumentType(file: File): DocumentType {
    // A filename or browser MIME value is not clinical evidence. The ingestion worker
    // classifies source content separately, and clinicians can review that provenance.
    void file;
    return DocumentType.OTHER;
}
