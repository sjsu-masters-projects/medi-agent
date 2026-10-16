import type { ADRReviewQueueItem } from "@/services/clinicians";

export type QueueTab = "awaiting" | "information" | "reviewed" | "dismissed";

/** Which work-queue tab a case belongs to. */
export function queueTabOf(item: ADRReviewQueueItem): QueueTab {
    if (item.status === "dismissed") return "dismissed";
    if (item.status === "reviewed" || item.status === "submitted") return "reviewed";
    return item.lastReviewAction === "request_information" ? "information" : "awaiting";
}

export const STATUS_LABELS: Record<QueueTab, string> = {
    awaiting: "Awaiting review",
    information: "Information requested",
    reviewed: "Reviewed",
    dismissed: "Dismissed",
};

export function missingCount(item: ADRReviewQueueItem): number {
    return item.naranjoAssessment.missing_questions?.length ?? 0;
}
