import type { ClinicFilter } from "@/hooks/use-clinic-filter";

/**
 * The clinic scope a list page header names: "All clinics" for a multi-clinic clinician with no
 * filter, or the selected clinic when filtered. A single-clinic clinician gets nothing: there is
 * no choice to describe, and no stored or arbitrary clinic is ever shown in its place.
 */
export function clinicScopeLabel(filter: ClinicFilter): string | null {
    return filter.multi ? (filter.clinicName ?? "All clinics") : null;
}
