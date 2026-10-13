"use client";

import { Icon, type IconName } from "@/components/ui/icons";
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
            return { chip: "bg-ok-soft text-ok-ink", dot: "bg-ok" };
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

export function ParseStatusBadge({ parseStatus }: ParseStatusBadgeProps) {
    const tone = getParseStatusTone(parseStatus);
    return (
        <span className={`${CHIP_BASE} ${tone.chip}`}>
            {parseStatus === "processing" ? (
                <LiveDot color="#D97706" />
            ) : (
                <span aria-hidden="true" className={`h-[7px] w-[7px] shrink-0 rounded-full ${tone.dot}`} />
            )}
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
    const tone = getReviewStatusTone(reviewStatus);
    return (
        <span className={`${CHIP_BASE} ${tone.chip}`}>
            <span aria-hidden="true" className={`h-[7px] w-[7px] shrink-0 rounded-full ${tone.dot}`} />
            Review {reviewStatus}
        </span>
    );
}

const DOCUMENT_TYPE_TILES: Record<string, { icon: IconName; tone: string }> = {
    lab_report: { icon: "lab", tone: "bg-primary-tint text-primary" },
    diagnostic_report: { icon: "gauge", tone: "bg-primary-tint text-primary" },
    prescription: { icon: "rx", tone: "bg-warn-soft text-warn-ink" },
    discharge_summary: { icon: "note", tone: "bg-sunken text-ink-2" },
    referral: { icon: "building", tone: "bg-sunken text-ink-2" },
    insurance: { icon: "shield", tone: "bg-sunken text-ink-2" },
};

/** Decorative tinted tile that signals the document type at a glance. */
export function DocumentTypeTile({ documentType, size = "md" }: { documentType?: string | null; size?: "sm" | "md" }) {
    const tile = (documentType && DOCUMENT_TYPE_TILES[documentType]) || {
        icon: "file" as IconName,
        tone: "bg-sunken text-ink-2",
    };
    const box = size === "sm" ? "h-8 w-8" : "h-9 w-9";
    return (
        <span aria-hidden="true" className={`flex ${box} shrink-0 items-center justify-center rounded-[10px] ${tile.tone}`}>
            <Icon name={tile.icon} className="h-[18px] w-[18px]" />
        </span>
    );
}
