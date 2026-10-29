import { DocumentType, type Document, type Locale } from "@/types";
import { api } from "./api";

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
    display_title?: Partial<Record<"en-US" | "es-MX", string>> | null;
    parse_status?: Document["parseStatus"];
    parse_failure_code?: string | null;
    parse_attempts?: number;
    summary_status?: string | null;
    summary_failure_code?: string | null;
    source_clinic?: string | null;
    review_status?: Document["reviewStatus"] | null;
    reviewed_at?: string | null;
    visibility: Document["visibility"];
    created_at: string;
}

export const EXPLANATION_KINDS = [
    "overview",
    "medicines",
    "results",
    "conditions",
    "allergies",
    "instructions",
    "questions",
] as const;
export type ExplanationKind = (typeof EXPLANATION_KINDS)[number];
export interface ExplanationSection {
    kind: ExplanationKind;
    items: string[];
}
export interface DocumentExplanation {
    language: Locale;
    summary: string;
    sections: ExplanationSection[];
}

/** Refuse an older server's unstructured or mismatched-language response. */
export function readDocumentExplanation(
    value: unknown,
    locale: Locale,
): DocumentExplanation | null {
    if (!value || typeof value !== "object") return null;
    const response = value as Record<string, unknown>;
    if (
        response.available !== true ||
        response.language !== locale ||
        !Array.isArray(response.sections) ||
        !response.sections.length ||
        response.sections.length > EXPLANATION_KINDS.length
    )
        return null;
    const sections: ExplanationSection[] = [];
    for (const candidate of response.sections) {
        if (!candidate || typeof candidate !== "object") return null;
        const section = candidate as Record<string, unknown>;
        if (
            !EXPLANATION_KINDS.includes(section.kind as ExplanationKind) ||
            !Array.isArray(section.items) ||
            !section.items.length ||
            section.items.length > 20 ||
            section.items.some(
                (item) =>
                    typeof item !== "string" ||
                    !item.trim() ||
                    item.length > 2000,
            )
        )
            return null;
        if (sections.some((item) => item.kind === section.kind)) return null;
        sections.push({
            kind: section.kind as ExplanationKind,
            items: section.items as string[],
        });
    }
    // Speech and chat use exactly the same text as the visible sections.
    const summary = sections.flatMap((section) => section.items).join("\n\n");
    if (summary.length > 16000 || summary !== response.summary) return null;
    return { language: locale, summary, sections };
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

export type DocumentResultFlagMeaning = "high" | "low" | "abnormal" | "critical" | "unrecognized";
export type DocumentResultRangeStatus = "below" | "within" | "above";

/** One test result or measurement read from a document, with values exactly as printed. */
export interface DocumentResult {
    kind: "lab_result" | "vital_sign";
    name: string;
    value: string;
    unit: string | null;
    reference_range: string | null;
    flag: string | null;
    /** The report's own flag, restated; never derived from the value. */
    flag_meaning: DocumentResultFlagMeaning | null;
    /** The report's own printed range, restated; never derived in this app. */
    range_status: DocumentResultRangeStatus | null;
    panel: string | null;
    observed_at: string | null;
    page: number | null;
    reviewed: boolean;
}

const FLAG_MEANINGS = new Set<string>(["high", "low", "abnormal", "critical", "unrecognized"]);
const RANGE_STATUSES = new Set<string>(["below", "within", "above"]);

function optionalText(value: unknown): string | null {
    return typeof value === "string" && value.trim() ? value : null;
}

/** Keep only well-formed rows; an unknown flag or range value is treated as absent. */
export function toDocumentResult(item: unknown): DocumentResult | null {
    if (typeof item !== "object" || item === null) {
        return null;
    }
    const row = item as Record<string, unknown>;
    if (row.kind !== "lab_result" && row.kind !== "vital_sign") {
        return null;
    }
    const name = optionalText(row.name);
    const value = optionalText(row.value);
    if (!name || !value) {
        return null;
    }
    const flagMeaning = typeof row.flag_meaning === "string" && FLAG_MEANINGS.has(row.flag_meaning)
        ? (row.flag_meaning as DocumentResultFlagMeaning)
        : null;
    const rangeStatus = typeof row.range_status === "string" && RANGE_STATUSES.has(row.range_status)
        ? (row.range_status as DocumentResultRangeStatus)
        : null;
    return {
        kind: row.kind,
        name,
        value,
        unit: optionalText(row.unit),
        reference_range: optionalText(row.reference_range),
        flag: optionalText(row.flag),
        flag_meaning: flagMeaning,
        range_status: rangeStatus,
        panel: optionalText(row.panel),
        observed_at: optionalText(row.observed_at),
        page: typeof row.page === "number" && Number.isFinite(row.page) ? row.page : null,
        // Anything not explicitly confirmed is shown as not yet reviewed.
        reviewed: row.reviewed === true,
    };
}

/** Test results and measurements read from one of the signed-in patient's documents. */
export async function fetchDocumentResults(
    documentId: string,
    token: string,
    signal?: AbortSignal,
): Promise<DocumentResult[]> {
    const payload = await api.get<unknown>(
        `/api/v1/documents/${encodeURIComponent(documentId)}/results`,
        { token, signal },
    );
    if (!Array.isArray(payload)) {
        return [];
    }
    return payload
        .map(toDocumentResult)
        .filter((result): result is DocumentResult => result !== null);
}
