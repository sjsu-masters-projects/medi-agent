import type { ClinicFilter } from "@/hooks/use-clinic-filter";

/**
 * The clinic scope a list page header names: "All clinics" for a multi-clinic clinician with no
 * filter, the selected clinic when filtered, and the only clinic for a single-clinic clinician.
 * The stored sign-in clinic is only a fallback until the clinic list has loaded; it is never
 * shown for a multi-clinic clinician, whose stored clinic may not be their default.
 */
export function clinicScopeLabel(filter: ClinicFilter, fallback: string | null): string | null {
    if (filter.multi) {
        return filter.clinicName ?? "All clinics";
    }
    if (filter.clinics.length === 1) {
        return filter.clinics[0].clinic_name;
    }
    return filter.ready ? null : fallback;
}
