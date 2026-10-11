"use client";

import { DocumentReviewStatus } from "@/types";

function getParseStatusBadgeClass(parseStatus: string): string {
    switch (parseStatus) {
        case "completed":
            return "bg-ok-tint text-ok-ink";
        case "failed":
            return "bg-risk-tint text-risk-ink";
        case "needs_ocr":
        case "needs_evidence_review":
        case "duplicate":
            return "bg-sunken text-ink-2";
        default:
            return "bg-warn-tint text-warn-ink";
    }
}

function getReviewStatusBadgeClass(reviewStatus: DocumentReviewStatus): string {
    switch (reviewStatus) {
        case DocumentReviewStatus.APPROVED:
            return "bg-ok-tint text-ok-ink";
        case DocumentReviewStatus.REJECTED:
            return "bg-risk-tint text-risk-ink";
        case DocumentReviewStatus.PENDING:
            return "bg-ai-tint text-primary";
        default:
            return "bg-sunken text-ink-2";
    }
}

interface ParseStatusBadgeProps {
    parseStatus: string;
}

export function ParseStatusBadge({ parseStatus }: ParseStatusBadgeProps) {
    return (
        <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${getParseStatusBadgeClass(parseStatus)}`}
        >
            {parseStatus === "duplicate"
                ? "Duplicate upload — extraction skipped"
                : parseStatus === "needs_ocr"
                ? "OCR review needed"
                : parseStatus === "needs_evidence_review"
                  ? "Evidence review needed"
                  : `Parse ${parseStatus}`}
        </span>
    );
}

interface ReviewStatusBadgeProps {
    reviewStatus: DocumentReviewStatus;
}

export function ReviewStatusBadge({ reviewStatus }: ReviewStatusBadgeProps) {
    return (
        <span
            className={`rounded-full px-2 py-0.5 text-xs font-medium ${getReviewStatusBadgeClass(reviewStatus)}`}
        >
            Review {reviewStatus}
        </span>
    );
}
