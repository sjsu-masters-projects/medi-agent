"use client";

import { DocumentReviewStatus } from "@/types";

function getParseStatusBadgeClass(parseStatus: string): string {
    switch (parseStatus) {
        case "completed":
            return "bg-green-100 text-green-700";
        case "failed":
            return "bg-red-100 text-red-700";
        default:
            return "bg-amber-100 text-amber-700";
    }
}

function getReviewStatusBadgeClass(reviewStatus: DocumentReviewStatus): string {
    switch (reviewStatus) {
        case DocumentReviewStatus.APPROVED:
            return "bg-emerald-100 text-emerald-700";
        case DocumentReviewStatus.REJECTED:
            return "bg-rose-100 text-rose-700";
        case DocumentReviewStatus.PENDING:
            return "bg-blue-100 text-blue-700";
        default:
            return "bg-slate-100 text-slate-600";
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
            Parse {parseStatus}
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
