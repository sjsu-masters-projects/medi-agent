import type { CarePlanScope } from "@/types";

/** Query string for the optional plan scope (`care_team_id` / `care_plan_id`); empty when none. */
export function scopeQuery(scope?: CarePlanScope | null): string {
    const query = new URLSearchParams();
    if (scope?.careTeamId) query.set("care_team_id", scope.careTeamId);
    if (scope?.carePlanId) query.set("care_plan_id", scope.carePlanId);
    const text = query.toString();
    return text ? `?${text}` : "";
}
