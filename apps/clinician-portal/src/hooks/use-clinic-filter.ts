"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useSelector } from "react-redux";
import { fetchMyClinics, type ClinicMembershipSummary } from "@/services/clinics";
import type { RootState } from "@/store/store";

/** The URL query parameter that carries the clinic filter (default: All clinics). */
export const CLINIC_PARAM = "clinic";

export interface ClinicFilter {
    /** Active clinics the clinician belongs to. */
    clinics: ClinicMembershipSummary[];
    /** The selected clinic, or null for All clinics. Only ever one of the active clinics. */
    clinicId: string | null;
    clinicName: string | null;
    /** True with two or more active clinics: the only case that shows chips and the filter. */
    multi: boolean;
    /** False until the clinic list has loaded, so a list does not fetch twice. */
    ready: boolean;
    setClinicId: (clinicId: string | null) => void;
}

/** The clinician's active clinics, loaded once per page. */
export function useClinicMemberships(): { clinics: ClinicMembershipSummary[]; ready: boolean } {
    const token = useSelector((state: RootState) => state.auth?.accessToken ?? null);
    const [clinics, setClinics] = useState<ClinicMembershipSummary[]>([]);
    const [loaded, setLoaded] = useState(false);

    useEffect(() => {
        if (!token) {
            return;
        }
        let cancelled = false;
        void (async () => {
            try {
                const result = await fetchMyClinics(token);
                if (!cancelled) {
                    setClinics(result.clinics.filter((clinic) => clinic.status === "active"));
                }
            } catch {
                // Without the list there is no filter; the lists still load clinician-wide.
                if (!cancelled) {
                    setClinics([]);
                }
            } finally {
                if (!cancelled) {
                    setLoaded(true);
                }
            }
        })();
        return () => {
            cancelled = true;
        };
    }, [token]);

    return { clinics, ready: !token || loaded };
}

/** Combine the clinician's clinics with the requested clinic (from the URL) into a filter. */
export function useResolvedClinicFilter(
    requested: string | null,
    setClinicId: (clinicId: string | null) => void,
): ClinicFilter {
    const { clinics, ready } = useClinicMemberships();
    const multi = clinics.length >= 2;
    const selected = useMemo(
        () => (multi && requested ? clinics.find((clinic) => clinic.clinic_id === requested) : undefined),
        [clinics, multi, requested],
    );
    return {
        clinics,
        clinicId: selected?.clinic_id ?? null,
        clinicName: selected?.clinic_name ?? null,
        multi,
        ready,
        setClinicId,
    };
}

/**
 * The clinic filter of a patient list, kept in the URL (`?clinic=<id>`) so it survives a reload
 * and back navigation. A clinician with one clinic gets `multi: false` and `clinicId: null`:
 * no chip, no filter and no request parameter. It is not a global switcher.
 */
export function useClinicFilter(): ClinicFilter {
    const router = useRouter();
    const pathname = usePathname();
    const searchParams = useSearchParams();

    const setClinicId = useCallback(
        (clinicId: string | null) => {
            const next = new URLSearchParams(searchParams?.toString() ?? "");
            if (clinicId) {
                next.set(CLINIC_PARAM, clinicId);
            } else {
                next.delete(CLINIC_PARAM);
            }
            const query = next.toString();
            router.replace(query ? `${pathname}?${query}` : (pathname ?? "/"), { scroll: false });
        },
        [pathname, router, searchParams],
    );

    return useResolvedClinicFilter(searchParams?.get(CLINIC_PARAM) ?? null, setClinicId);
}
