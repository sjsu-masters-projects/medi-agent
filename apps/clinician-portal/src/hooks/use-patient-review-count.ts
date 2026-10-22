"use client";

import { useEffect, useState } from "react";
import { fetchReviewItems } from "@/services/care-team-plans";

/**
 * Open care plan review items for one patient, for the badge on the Care Plan tab. It stays 0
 * when the list cannot be read: a missing badge is never worse than the page failing.
 */
export function usePatientReviewCount(patientId: string, enabled = true): number {
    const [count, setCount] = useState(0);
    useEffect(() => {
        if (!enabled) return;
        let active = true;
        void (async () => {
            try {
                const list = await fetchReviewItems("open");
                if (active) setCount((list.items ?? []).filter((item) => item.patient_id === patientId).length);
            } catch {
                if (active) setCount(0);
            }
        })();
        return () => { active = false; };
    }, [patientId, enabled]);
    return count;
}
