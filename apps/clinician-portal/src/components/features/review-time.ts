import { formatClinicianDateTime } from "@/utils/dates";

/**
 * Timestamp for clinician review surfaces (ADR review and MedWatch drafts), for example
 * "Oct 12, 2026, 3:00 PM". Delegates to the shared clinician date helper so the locale
 * stays fixed to en-US rather than following the browser.
 */
export function formatReviewTimestamp(value: string): string {
    return formatClinicianDateTime(value, { dateStyle: "medium", timeStyle: "short" });
}
