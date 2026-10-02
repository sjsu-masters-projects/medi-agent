import { describe, expect, it } from "vitest";
import { carePlanChanges, carePlanOverlaps } from "@/components/features/care-plan-changes";
import type { CarePlanItem, CarePlanVersion } from "@/services/clinicians";

function item(id: string, factId: string, overrides: Partial<CarePlanItem> = {}): CarePlanItem {
    return {
        id, source_fact_id: factId, category: "movement", title: "Walk", instructions: "Walk 20 minutes",
        frequency: "daily", schedule: {}, medication: {}, uncertainty: [], conflict: {}, is_removed: false,
        ...overrides,
    };
}

describe("carePlanChanges", () => {
    it("does not call projection decision changes edited clinical wording", () => {
        const active: CarePlanVersion = {id: "v1", patient_id: "p", version_number: 1, status: "approved", items: [item("old", "fact", {medication: {name: "Metformin", decision: "create"}})]};
        expect(carePlanChanges([item("new", "fact", {medication: {name: "Metformin", decision: "update", target_id: "med"}})], active).get("new")).toBe("carried forward");
    });
    it("flags differing cadence on identical wording without combining schedules", () => {
        expect(carePlanOverlaps([item("one", "a"), item("two", "b", {frequency: "weekly"}), item("three", "c", {schedule: {event: "after dinner"}})]).get("one")).toEqual(["two"]);
    });
    it("keeps translated equivalent sources grouped until explicit removal", () => {
        const first = item("one", "a", {overlapping_item_ids: ["two"]});
        const second = item("two", "b", {instructions: "Caminar 20 minutos"});
        expect(carePlanOverlaps([first, second]).get("two")).toEqual(["one"]);
        expect(carePlanOverlaps([first, {...second, is_removed: true}]).size).toBe(0);
    });
    it("distinguishes carried, edited, new-source, and removed items", () => {
        const active: CarePlanVersion = {
            id: "plan-1", patient_id: "patient-1", version_number: 1, status: "approved",
            items: [item("old-1", "fact-1"), item("old-2", "fact-2"), item("old-3", "fact-3")],
        };
        const changes = carePlanChanges([
            item("new-1", "fact-1"),
            item("new-2", "fact-2", { instructions: "Walk 30 minutes" }),
            item("new-3", "fact-4"),
            item("new-4", "fact-3", { is_removed: true }),
        ], active);

        expect([...changes.values()]).toEqual(["carried forward", "edited", "new evidence", "removed"]);
    });
});
