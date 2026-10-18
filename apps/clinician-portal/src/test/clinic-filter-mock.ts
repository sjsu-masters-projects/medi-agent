import { vi } from "vitest";
import type { ClinicMembershipSummary } from "@/services/clinics";

/**
 * A stand-in for `@/hooks/use-clinic-filter` in page tests: single-clinic by default (no chip,
 * no filter), multi-clinic when a test sets `clinicFilterState.clinics`.
 */
export const clinicFilterState = {
    clinics: [] as ClinicMembershipSummary[],
    clinicId: null as string | null,
    setClinicId: vi.fn(),
};

export function resetClinicFilter() {
    clinicFilterState.clinics = [];
    clinicFilterState.clinicId = null;
    clinicFilterState.setClinicId.mockReset();
}

function build() {
    const clinics = clinicFilterState.clinics;
    const multi = clinics.length >= 2;
    const selected = multi ? clinics.find((clinic) => clinic.clinic_id === clinicFilterState.clinicId) : undefined;
    return {
        clinics,
        clinicId: selected?.clinic_id ?? null,
        clinicName: selected?.clinic_name ?? null,
        multi,
        ready: true,
        setClinicId: clinicFilterState.setClinicId,
    };
}

export const clinicFilterModule = {
    CLINIC_PARAM: "clinic",
    useClinicFilter: () => build(),
    useResolvedClinicFilter: () => build(),
    useClinicMemberships: () => ({ clinics: clinicFilterState.clinics, ready: true }),
};
