import type { CarePlanItem, CarePlanVersion } from "@/services/clinicians";

export type CarePlanChange = "new evidence" | "edited" | "carried forward" | "removed";

/** Exact wording or same medication name is a review group, not equivalence proof. */
export function carePlanOverlaps(items: CarePlanItem[]): Map<string, string[]> {
    const active = items.filter((item) => !item.is_removed);
    const text = (value: unknown) => typeof value === "string" ? value.trim().replace(/\s+/g, " ").toLowerCase() : "";
    const key = (item: CarePlanItem) => item.category === "medication"
        ? text(item.medication.name) ? `medication:${text(item.medication.name)}` : null
        : text(item.instructions)
            ? JSON.stringify([item.category, text(item.instructions), item.schedule]) : null;
    return new Map(active.map((item) => [item.id, active.filter((other) => other.id !== item.id && (
        item.overlapping_item_ids?.includes(other.id) || other.overlapping_item_ids?.includes(item.id) ||
        Boolean(key(item) && key(item) === key(other))
    )).map((other) => other.id)]).filter(([, peers]) => peers.length > 0) as [string, string[]][]);
}

function itemContents(item: CarePlanItem) {
    // A projection identity/decision is not a change in clinical wording.
    const medication = Object.fromEntries(Object.entries(item.medication).filter(([key]) => !["decision", "target_id"].includes(key)));
    return JSON.stringify({
        title: item.title,
        instructions: item.instructions,
        frequency: item.frequency,
        schedule: item.schedule,
        medication,
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
