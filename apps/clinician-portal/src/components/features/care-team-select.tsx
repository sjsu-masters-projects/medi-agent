"use client";

import { useCallback, useEffect, useState } from "react";
import { errorCode, fetchCareTeamOptions } from "@/services/care-team-plans";
import type { ClinicianCareTeamOption } from "@/types";

/**
 * My exact care-team links to one patient. With several links, uploads, SOAP notes, ADR
 * reviews and MedWatch drafts need an explicit care team (`CARE_TEAM_REQUIRED` otherwise);
 * with one link nothing is asked and nothing is shown.
 */
export function useCareTeamChoice(patientId: string, enabled = true) {
    const [options, setOptions] = useState<ClinicianCareTeamOption[]>([]);
    const [value, setValue] = useState("");
    const [failed, setFailed] = useState(false);
    const [required, setRequired] = useState(false);

    const load = useCallback(async () => {
        setFailed(false);
        try {
            const next = await fetchCareTeamOptions(patientId);
            setOptions(Array.isArray(next) ? next : []);
        } catch {
            // Without the list the server still enforces its own rule (CARE_TEAM_REQUIRED).
            setOptions([]);
            setFailed(true);
        }
    }, [patientId]);

    useEffect(() => {
        if (!enabled) return;
        let active = true;
        void (async () => {
            try {
                const next = await fetchCareTeamOptions(patientId);
                if (active) setOptions(Array.isArray(next) ? next : []);
            } catch {
                if (active) { setOptions([]); setFailed(true); }
            }
        })();
        return () => { active = false; };
    }, [patientId, enabled]);

    const multiple = options.length >= 2;
    // A single link is sent implicitly by the server; with several, a choice is required first.
    const missing = (multiple || required) && !value;

    /** Call with a failed request's error: true when the server asked for a care team. */
    const handleError = useCallback((error: unknown): boolean => {
        if (errorCode(error) !== "CARE_TEAM_REQUIRED") return false;
        setRequired(true);
        void load();
        return true;
    }, [load]);

    /** The server asked for a care team: show the select (loading the options if needed). */
    const requireChoice = useCallback(() => { setRequired(true); void load(); }, [load]);

    return {
        requireChoice, options, value, setValue, multiple, required: multiple || required, missing, failed, handleError, reload: load,
        /** The `care_team_id` to send, or undefined when none was needed or chosen. */
        careTeamId: value || undefined,
    };
}

/** "Cardiology · Cedar Grove"; the clinic alone when the link has no specialty. */
export function careTeamOptionLabel(option: Pick<ClinicianCareTeamOption, "specialty" | "clinic_name">): string {
    return [option.specialty, option.clinic_name].filter((part): part is string => Boolean(part && part.trim())).join(" · ") || "Care team";
}

export function CareTeamSelect({ options, value, onChange, required, showRequired = false, className = "" }: {
    options: ClinicianCareTeamOption[]; value: string; onChange: (careTeamId: string) => void;
    required: boolean; showRequired?: boolean; className?: string;
}) {
    if (options.length < 2) return null;
    const invalid = showRequired && !value;
    return <div className={`rounded-xl border border-line bg-surface-2 px-4 py-3 ${className}`}>
        <label className="block">
            <span className="mb-1.5 block text-[13px] font-medium text-ink-2">Care team{required ? " (required)" : ""}</span>
            <select aria-invalid={invalid || undefined} aria-required={required || undefined} className="h-10 w-full max-w-sm rounded-lg border border-line-strong bg-surface px-3 text-sm text-ink"
                onChange={(event) => onChange(event.target.value)} value={value}>
                {value ? null : <option disabled value="">Choose a care team</option>}
                {options.map((option) => <option key={option.care_team_id} value={option.care_team_id}>{careTeamOptionLabel(option)}</option>)}
            </select>
        </label>
        <p className={`mt-1.5 text-xs ${invalid ? "font-medium text-risk-ink" : "text-muted"}`} role={invalid ? "alert" : undefined}>
            {invalid ? "Choose which care team this belongs to before continuing." : "You care for this patient through more than one clinic. This belongs to one care team and is visible to that team only."}
        </p>
    </div>;
}
