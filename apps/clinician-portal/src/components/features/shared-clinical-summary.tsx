"use client";

import { useCallback, useEffect, useState } from "react";
import { Icon } from "@/components/ui/icons";
import { fetchSharedSummary } from "@/services/care-team-plans";
import type { RecordedBy, SharedClinicalSummary } from "@/types";
import { formatClinicianDate } from "@/utils/dates";

/**
 * The shared clinical summary (CLN-003): medications and allergies are always shared and say
 * which care team recorded them; conditions the patient keeps private are replaced by a neutral
 * line, with no count and no hint of what they are.
 */

export function useSharedSummary(patientId: string, enabled = true) {
    const [state, setState] = useState<{ status: "loading" | "ready" | "error"; summary: SharedClinicalSummary | null }>({ status: "loading", summary: null });
    const load = useCallback(async () => {
        try {
            const summary = await fetchSharedSummary(patientId);
            setState({ status: "ready", summary });
        } catch {
            setState({ status: "error", summary: null });
        }
    }, [patientId]);
    useEffect(() => {
        if (!enabled) return;
        let active = true;
        void (async () => {
            try {
                const summary = await fetchSharedSummary(patientId);
                if (active) setState({ status: "ready", summary });
            } catch {
                if (active) setState({ status: "error", summary: null });
            }
        })();
        return () => { active = false; };
    }, [patientId, enabled]);
    return { ...state, reload: load };
}

/** "Cardiology · Cedar Grove": who recorded it. Empty when the API names nothing. */
export function recordedByText(recorded: RecordedBy | undefined | null): string {
    if (!recorded) return "";
    return [recorded.specialty, recorded.clinic_name].filter((part): part is string => Boolean(part && part.trim())).join(" · ");
}

export function RecordedByCaption({ recorded, className = "" }: { recorded: RecordedBy | undefined | null; className?: string }) {
    const text = recordedByText(recorded);
    if (!text) return null;
    return <span className={`block break-words text-[11px] font-normal text-muted ${className}`}>Recorded by {text}</span>;
}

/** Shown only when it adds something: several care teams, or conditions the patient keeps private. */
export function sharedSummaryApplies(summary: SharedClinicalSummary | null): summary is SharedClinicalSummary {
    return Boolean(summary && (summary.care_teams.length >= 2 || summary.some_conditions_private));
}

export function SharedConditionsCard({ summary }: { summary: SharedClinicalSummary }) {
    return <section className="rounded-[14px] border border-line bg-surface p-5" aria-label="Active conditions across care teams">
        <h3 className="mb-3 ma-section-heading">Active Conditions</h3>
        {summary.conditions.length === 0 && !summary.some_conditions_private ? <p className="text-sm text-muted">None documented</p> : null}
        {summary.conditions.length > 0 ? <ul className="flex flex-wrap gap-2">
            {summary.conditions.map((condition) => <li className="inline-flex max-w-full flex-col rounded-[7px] border border-line bg-surface-2 px-2.5 py-1.5 text-[13px] font-medium text-ink" key={condition.id}>
                <span className="inline-flex items-center gap-1.5"><span aria-hidden="true" className="h-[7px] w-[7px] shrink-0 rounded-full bg-primary" /><span className="min-w-0 break-words">{condition.name}</span></span>
                <RecordedByCaption className="pl-[13px]" recorded={condition.recorded_by} />
            </li>)}
        </ul> : null}
        {summary.some_conditions_private ? <p className="mt-3 flex items-start gap-2 rounded-lg border border-line bg-surface-2 px-3 py-2 text-[13px] text-ink-2" data-testid="private-conditions-note">
            <Icon name="info" className="mt-0.5 h-4 w-4 shrink-0 text-muted" />Some conditions are kept private by the patient
        </p> : null}
    </section>;
}

export function SharedAllergiesCard({ summary }: { summary: SharedClinicalSummary }) {
    return <section className="rounded-[14px] border border-line bg-surface p-5" aria-label="Allergies across care teams">
        <h3 className="mb-3 ma-section-heading">Allergies</h3>
        {summary.allergies.length === 0 ? <p className="text-sm text-muted">Not documented</p> : <ul className="flex flex-wrap gap-2">
            {summary.allergies.map((allergy) => <li className="inline-flex max-w-full flex-col rounded-[7px] border border-risk-line bg-risk-soft px-2.5 py-1.5 text-[13px] font-medium text-risk-ink" key={allergy.id}>
                <span className="inline-flex flex-wrap items-center gap-1.5"><Icon name="alert" className="h-3.5 w-3.5 shrink-0" /><span className="min-w-0 break-words">{allergy.allergen}</span>
                    {allergy.severity ? <span className="rounded-[5px] bg-risk-tint px-1.5 py-0.5 text-[11px] font-medium capitalize text-risk-ink">{allergy.severity}</span> : null}</span>
                <RecordedByCaption className="pl-5 text-risk-ink/80" recorded={allergy.recorded_by} />
            </li>)}
        </ul>}
    </section>;
}

/** "Also cared for by …": the patient's other care teams, with plan status only. */
export function OtherCareTeams({ summary }: { summary: SharedClinicalSummary }) {
    const others = summary.care_teams.filter((team) => !team.is_mine);
    if (others.length === 0) return null;
    return <section className="rounded-[14px] border border-line bg-surface p-5 md:col-span-2" aria-labelledby="other-care-teams">
        <h3 className="mb-3 ma-section-heading" id="other-care-teams">Also cared for by</h3>
        <ul className="grid gap-2 md:grid-cols-2">
            {others.map((team, index) => <li className="rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm" key={team.care_team_id ?? index}>
                <span className="block break-words font-semibold text-ink">{[team.specialty, team.clinician_name].filter(Boolean).join(" · ") || "Care team"}</span>
                <span className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted">
                    {team.clinic_name ? <span>{team.clinic_name}</span> : null}
                    <span>{team.plan?.approved_at ? `Plan approved ${formatClinicianDate(team.plan.approved_at, { month: "short", day: "numeric", year: "numeric" })}` : "No approved plan"}</span>
                </span>
            </li>)}
        </ul>
    </section>;
}

/** The shared medication list with the care team that recorded each entry. */
export function SharedMedicationList({ summary }: { summary: SharedClinicalSummary }) {
    return <section aria-labelledby="shared-medications" className="space-y-2">
        <h3 className="ma-section-heading" id="shared-medications">Shared medication list</h3>
        {summary.medications.length === 0 ? <p className="text-sm text-muted">No active medications</p> : <ul className="divide-y divide-line rounded-xl border border-line bg-surface">
            {summary.medications.map((medication) => <li className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1 px-4 py-3" key={medication.id}>
                <span className="min-w-0 flex-1 basis-56">
                    <span className="block break-words text-sm font-semibold text-ink">{medication.name}</span>
                    <span className="block break-words text-[13px] text-ink-2">{[medication.dosage, medication.frequency, medication.route].filter(Boolean).join(" · ")}</span>
                </span>
                <span className="flex flex-col items-start gap-1 text-xs text-muted sm:items-end">
                    <span>Recorded by {recordedByText(medication.recorded_by) || "a care team"}</span>
                </span>
            </li>)}
        </ul>}
    </section>;
}
