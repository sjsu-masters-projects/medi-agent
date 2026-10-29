import { DocumentType } from "../types";

/** Document shape identifies type only; uploader and review state have text labels. */
export function documentTypeIcon(documentType?: string | null) {
    switch (documentType) {
        case DocumentType.LAB_REPORT: return "lab";
        case DocumentType.DIAGNOSTIC_REPORT: return "gauge";
        case DocumentType.PRESCRIPTION: return "rx";
        case DocumentType.DISCHARGE_SUMMARY: return "note";
        case DocumentType.REFERRAL: return "building";
        case DocumentType.INSURANCE: return "shield";
        default: return "file";
    }
}
