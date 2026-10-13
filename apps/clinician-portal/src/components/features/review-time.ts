/**
 * Shared timestamp formatting for clinician review surfaces (ADR review and
 * MedWatch drafts). Clinician controls stay in English, so the locale is fixed
 * to `en-US` rather than following the browser.
 */
const reviewTimestampFormatter = new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
});

export function formatReviewTimestamp(value: string): string {
    return reviewTimestampFormatter.format(new Date(value));
}
