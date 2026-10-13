/**
 * Clinician-facing date formatting.
 *
 * The clinician portal is English (US) only, so dates must not follow the
 * browser's region: an upload on October 12 reads "10/12/2026" everywhere.
 * The viewer's time zone is still used for wall-clock display.
 */
export const CLINICIAN_LOCALE = "en-US";

const MISSING = "—";

function toDate(value: string | number | Date | null | undefined): Date | null {
    if (value === null || value === undefined || value === "") {
        return null;
    }
    const date = value instanceof Date ? value : new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
}

/** Calendar date, e.g. "10/12/2026". */
export function formatClinicianDate(
    value: string | number | Date | null | undefined,
    options?: Intl.DateTimeFormatOptions,
): string {
    const date = toDate(value);
    return date ? date.toLocaleDateString(CLINICIAN_LOCALE, options) : MISSING;
}

/** Date and time, e.g. "10/12/2026, 3:00:00 PM". */
export function formatClinicianDateTime(
    value: string | number | Date | null | undefined,
    options?: Intl.DateTimeFormatOptions,
): string {
    const date = toDate(value);
    return date ? date.toLocaleString(CLINICIAN_LOCALE, options) : MISSING;
}
