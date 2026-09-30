import type { CarePlanItem, CarePlanVersion } from "@/services/clinicians";

export type CarePlanChange = "new evidence" | "edited" | "carried forward" | "removed";

function itemContents(item: CarePlanItem) {
    return JSON.stringify({
        title: item.title,
        instructions: item.instructions,
        frequency: item.frequency,
        schedule: item.schedule,
        medication: item.medication,
    });
}

/** Compare snapshots by source fact, not by clinical equivalence. */
export function carePlanChanges(
    proposed: CarePlanItem[],
    active: CarePlanVersion | null,
): Map<string, CarePlanChange> {
    const previous = new Map(
        (active?.items ?? []).filter((item) => !item.is_removed && item.source_fact_id)
            .map((item) => [item.source_fact_id, item]),
    );
    return new Map(proposed.map((item) => {
        const earlier = previous.get(item.source_fact_id);
        const change: CarePlanChange = item.is_removed
            ? "removed"
            : !earlier
                ? "new evidence"
                : itemContents(item) === itemContents(earlier)
                    ? "carried forward"
                    : "edited";
        return [item.id, change];
    }));
}
