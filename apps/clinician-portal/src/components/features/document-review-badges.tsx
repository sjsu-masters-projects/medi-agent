"use client";

import { Icon } from "@/components/ui/icons";
import { documentTypeIcon } from "../../../../../packages/shared/src/utils/document-presentation";
import { LiveDot } from "@/components/ui/motion";
import { DocumentReviewStatus } from "@/types";

const CHIP_BASE =
    "inline-flex items-center gap-1.5 whitespace-nowrap rounded-[7px] px-2 py-1 text-xs font-medium";

interface ChipTone {
    chip: string;
    dot: string;
}

function getParseStatusTone(parseStatus: string): ChipTone {
    switch (parseStatus) {
        case "completed":
            return { chip: "bg-sunken text-ink-2", dot: "bg-[#94A3B8]" };
        case "failed":
            return { chip: "bg-risk-soft text-risk-ink", dot: "bg-risk" };
        case "needs_ocr":
        case "needs_evidence_review":
        case "duplicate":
            return { chip: "bg-sunken text-ink-2", dot: "bg-[#94A3B8]" };
        default:
            return { chip: "bg-warn-soft text-warn-ink", dot: "bg-warn" };
    }
}

function getReviewStatusTone(reviewStatus: DocumentReviewStatus): ChipTone {
    switch (reviewStatus) {
        case DocumentReviewStatus.APPROVED:
            return { chip: "bg-ok-soft text-ok-ink", dot: "bg-ok" };
        case DocumentReviewStatus.REJECTED:
            return { chip: "bg-risk-soft text-risk-ink", dot: "bg-risk" };
        case DocumentReviewStatus.PENDING:
            return { chip: "bg-primary-tint text-primary", dot: "bg-primary" };
        default:
            return { chip: "bg-sunken text-ink-2", dot: "bg-[#94A3B8]" };
    }
}

interface ParseStatusBadgeProps {
    parseStatus: string;
}

const PARSE_STATUS_LABELS: Record<string, string> = {
    none: "Not processed",
    pending: "Waiting to process",
    processing: "Processing",
    completed: "Processed",
    failed: "Processing failed",
    duplicate: "Duplicate — already on file",
    needs_ocr: "Scan not readable — review needed",
    needs_evidence_review: "Couldn't verify — check source",
};

/** Processing state in words; an unknown state is humanized, never shown as a code. */
export function parseStatusLabel(parseStatus: string): string {
    const known = PARSE_STATUS_LABELS[parseStatus];
    if (known) return known;
    const words = parseStatus.replaceAll("_", " ").trim();
    return words ? `Processing: ${words}` : "Processing status unavailable";
}

export function ParseStatusBadge({ parseStatus }: ParseStatusBadgeProps) {
    const tone = getParseStatusTone(parseStatus);
    return (
        <span className={`${CHIP_BASE} ${tone.chip}`}>
            {parseStatus === "processing" ? (
                <LiveDot color="#D97706" />
            ) : (
                <span aria-hidden="true" className={`h-[7px] w-[7px] shrink-0 rounded-full ${tone.dot}`} />
            )}
            {parseStatusLabel(parseStatus)}
        </span>
    );
}

interface ReviewStatusBadgeProps {
    reviewStatus: DocumentReviewStatus;
}

export function ReviewStatusBadge({ reviewStatus }: ReviewStatusBadgeProps) {
    const tone = getReviewStatusTone(reviewStatus);
    const label = reviewStatus === DocumentReviewStatus.APPROVED
        ? "Source approved"
        : reviewStatus === DocumentReviewStatus.REJECTED
          ? "Source not approved"
          : reviewStatus === DocumentReviewStatus.PENDING
            ? "Awaiting review"
            : "Review status unavailable";
    return (
        <span className={`${CHIP_BASE} ${tone.chip}`}>
            <span aria-hidden="true" className={`h-[7px] w-[7px] shrink-0 rounded-full ${tone.dot}`} />
            {label}
        </span>
    );
}

/** Decorative neutral tile; approval is conveyed separately in words. */
export function DocumentTypeTile({ documentType, size = "md" }: { documentType?: string | null; size?: "sm" | "md" }) {
    const box = size === "sm" ? "h-8 w-8" : "h-9 w-9";
    return (
        <span aria-hidden="true" className={`flex ${box} shrink-0 items-center justify-center rounded-[10px] bg-sunken text-ink-2`}>
            <Icon name={documentTypeIcon(documentType)} className="h-[18px] w-[18px]" />
        </span>
    );
}
