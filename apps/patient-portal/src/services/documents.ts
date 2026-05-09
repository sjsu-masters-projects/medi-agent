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
    file_size_bytes: number;
    parsed: boolean;
    ai_summary?: string | null;
    parse_status?: Document["parseStatus"];
    parse_error?: string | null;
    parse_attempts?: number;
    source_clinic?: string | null;
    visibility: Document["visibility"];
    created_at: string;
}

export function inferDocumentType(file: File): DocumentType {
    const normalizedName = file.name.toLowerCase();
    const normalizedType = file.type.toLowerCase();

    if (normalizedType.startsWith("image/")) {
        return DocumentType.DIAGNOSTIC_REPORT;
    }

    if (normalizedName.includes("discharge") || normalizedName.includes("summary")) {
        return DocumentType.DISCHARGE_SUMMARY;
    }
    if (normalizedName.includes("prescription") || normalizedName.includes("rx")) {
        return DocumentType.PRESCRIPTION;
    }
    if (normalizedName.includes("referral")) {
        return DocumentType.REFERRAL;
    }
    if (normalizedName.includes("insurance")) {
        return DocumentType.INSURANCE;
    }
    if (
        normalizedName.includes("lab")
        || normalizedName.includes("blood")
        || normalizedName.includes("result")
        || normalizedType === "text/csv"
        || normalizedName.endsWith(".csv")
    ) {
        return DocumentType.LAB_REPORT;
    }
    if (
        normalizedName.includes("diagnostic")
        || normalizedName.includes("xray")
        || normalizedName.includes("mri")
        || normalizedName.includes("ct")
        || normalizedName.includes("scan")
    ) {
        return DocumentType.DIAGNOSTIC_REPORT;
    }
    return DocumentType.OTHER;
}
