import { describe, expect, it } from "vitest";
import { carePlanChanges } from "@/components/features/care-plan-changes";
import type { CarePlanItem, CarePlanVersion } from "@/services/clinicians";

function item(id: string, factId: string, overrides: Partial<CarePlanItem> = {}): CarePlanItem {
    return {
        id, source_fact_id: factId, category: "movement", title: "Walk", instructions: "Walk 20 minutes",
        frequency: "daily", schedule: {}, medication: {}, uncertainty: [], conflict: {}, is_removed: false,
        ...overrides,
    };
}

describe("carePlanChanges", () => {
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
